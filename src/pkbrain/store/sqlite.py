"""SQLite：程序可查的那一份。带全文索引（FTS5）与指标表。

汉字在入索引前按字符切开（见 text.segment），否则 unicode61 分词器会把一整句当一个词。
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from ..models import Record
from ..schema import PkbsSubset
from ..text import segment, to_match_query

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS records (
    id         TEXT PRIMARY KEY,
    type       TEXT NOT NULL,
    ts         TEXT NOT NULL,
    date       TEXT NOT NULL,
    dims       TEXT NOT NULL,
    privacy    TEXT NOT NULL,
    channel    TEXT NOT NULL,
    confidence REAL NOT NULL,
    version    TEXT NOT NULL,
    source     TEXT NOT NULL,
    tags       TEXT NOT NULL,
    entities   TEXT NOT NULL,
    path       TEXT NOT NULL,
    text       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_records_date ON records(date);
CREATE INDEX IF NOT EXISTS idx_records_privacy ON records(privacy);

CREATE VIRTUAL TABLE IF NOT EXISTS records_fts USING fts5(id UNINDEXED, body);

CREATE TABLE IF NOT EXISTS metrics (
    record_id TEXT NOT NULL,
    name      TEXT NOT NULL,
    dim       TEXT NOT NULL,
    value     REAL NOT NULL,
    unit      TEXT NOT NULL,
    PRIMARY KEY (record_id, name)
);
CREATE INDEX IF NOT EXISTS idx_metrics_name ON metrics(name);
CREATE INDEX IF NOT EXISTS idx_metrics_dim ON metrics(dim);
"""


def db_path(data_dir: Path, schema: PkbsSubset) -> Path:
    return Path(data_dir) / schema.paths["database"]


def compact_day(day: str) -> str:
    """2026-10-16 → 20261016。记录 id 的前 8 位就是日期。"""
    return day.replace("-", "")


@dataclass
class Hit:
    id: str
    type: str
    ts: str
    date: str
    dims: list[str]
    privacy: str
    channel: str
    confidence: float
    version: str
    source: str
    tags: list[str]
    path: str
    text: str
    rank: float | None = None

    def excerpt(self, terms: list[str], width: int = 60) -> str:
        flat = " ".join(self.text.split())
        for term in terms:
            index = flat.find(term)
            if index >= 0:
                start = max(0, index - width // 2)
                end = min(len(flat), index + len(term) + width)
                head = "…" if start else ""
                tail = "…" if end < len(flat) else ""
                return f"{head}{flat[start:end]}{tail}"
        return flat[: width * 2] + ("…" if len(flat) > width * 2 else "")


def _hit(row: sqlite3.Row) -> Hit:
    keys = row.keys()
    return Hit(
        id=row["id"],
        type=row["type"],
        ts=row["ts"],
        date=row["date"],
        dims=[d for d in row["dims"].split(",") if d],
        privacy=row["privacy"],
        channel=row["channel"],
        confidence=row["confidence"],
        version=row["version"],
        source=row["source"],
        tags=[t for t in row["tags"].split(",") if t],
        path=row["path"],
        text=row["text"],
        rank=row["rank"] if "rank" in keys else None,
    )


class Store:
    """一条记录两处写入：recods 表存元数据与正文，records_fts 存切分后的索引。"""

    def __init__(self, path: Path, schema: PkbsSubset) -> None:
        self.path = Path(path)
        self.schema = schema
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA_SQL)
        self.conn.commit()

    def __enter__(self) -> Store:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self.conn.close()

    # ---- 写入 ---------------------------------------------------------

    def put(self, record: Record, path: Path | str) -> None:
        """写入一条记录。同一个 id 重复写入是覆盖，不产生第二条。"""
        dims = "," + ",".join(record.dims) + "," if record.dims else ""
        text = record.plain_text()
        metric_rows = []
        for name, value in record.metrics.items():
            metric = self.schema.metrics.get(name)
            dim = metric.dim if metric else (record.dims[0] if record.dims else "")
            metric_rows.append((record.id, name, dim, float(value), metric.unit if metric else ""))

        with self.conn:
            self.conn.execute(
                """
                INSERT INTO records (id, type, ts, date, dims, privacy, channel, confidence,
                                     version, source, tags, entities, path, text)
                VALUES (:id, :type, :ts, :date, :dims, :privacy, :channel, :confidence,
                        :version, :source, :tags, :entities, :path, :text)
                ON CONFLICT(id) DO UPDATE SET
                    type = excluded.type, ts = excluded.ts, date = excluded.date, dims = excluded.dims,
                    privacy = excluded.privacy, channel = excluded.channel,
                    confidence = excluded.confidence, version = excluded.version,
                    source = excluded.source, tags = excluded.tags, entities = excluded.entities,
                    path = excluded.path, text = excluded.text
                """,
                {
                    "id": record.id,
                    "type": record.type,
                    "ts": record.ts.isoformat(),
                    "date": record.date.isoformat(),
                    "dims": dims,
                    "privacy": record.privacy,
                    "channel": record.channel,
                    "confidence": record.confidence,
                    "version": record.version,
                    "source": record.source,
                    "tags": ",".join(record.tags),
                    "entities": ",".join(record.entities),
                    "path": str(path),
                    "text": text,
                },
            )
            self.conn.execute("DELETE FROM records_fts WHERE id = ?", (record.id,))
            self.conn.execute(
                "INSERT INTO records_fts (id, body) VALUES (?, ?)",
                (record.id, segment(f"{text} {' '.join(record.tags)}")),
            )
            self.conn.execute("DELETE FROM metrics WHERE record_id = ?", (record.id,))
            self.conn.executemany(
                "INSERT INTO metrics (record_id, name, dim, value, unit) VALUES (?, ?, ?, ?, ?)",
                metric_rows,
            )

    # ---- 读取 ---------------------------------------------------------

    def search(
        self,
        query: str | None = None,
        *,
        dim: str | None = None,
        since: str | None = None,
        until: str | None = None,
        privacy: str | None = None,
        limit: int = 20,
    ) -> list[Hit]:
        filters: list[str] = []
        params: list[object] = []
        if dim:
            filters.append("r.dims LIKE ?")
            params.append(f"%,{dim},%")
        if since:
            filters.append("r.date >= ?")
            params.append(since)
        if until:
            filters.append("r.date <= ?")
            params.append(until)
        if privacy:
            filters.append("r.privacy = ?")
            params.append(privacy)
        where = (" AND " + " AND ".join(filters)) if filters else ""

        if query:
            match = to_match_query(query)
            if not match:
                raise ValueError("查询里没有可检索的词")
            sql = (
                "SELECT r.*, bm25(records_fts) AS rank FROM records_fts "
                "JOIN records r ON r.id = records_fts.id "
                f"WHERE records_fts MATCH ?{where} ORDER BY rank LIMIT ?"
            )
            params = [match, *params, limit]
        else:
            sql = f"SELECT r.* FROM records r WHERE 1=1{where} ORDER BY r.date DESC, r.ts DESC LIMIT ?"
            params = [*params, limit]

        rows = self.conn.execute(sql, params).fetchall()
        return [_hit(row) for row in rows]

    def by_date(self, day: str) -> list[Hit]:
        rows = self.conn.execute("SELECT * FROM records WHERE date = ? ORDER BY ts", (day,)).fetchall()
        return [_hit(row) for row in rows]

    def by_id(self, record_id: str) -> Hit | None:
        row = self.conn.execute("SELECT * FROM records WHERE id = ?", (record_id,)).fetchone()
        return _hit(row) if row else None

    def latest_before(self, day: str) -> Hit | None:
        """今天之前最近的一条记录。提问引擎靠它找昨日缺口。"""
        row = self.conn.execute(
            "SELECT * FROM records WHERE date < ? ORDER BY date DESC, ts DESC LIMIT 1", (day,)
        ).fetchone()
        return _hit(row) if row else None

    def between(self, start: str, end: str, *, limit: int = 10) -> list[Hit]:
        rows = self.conn.execute(
            "SELECT * FROM records WHERE date BETWEEN ? AND ? ORDER BY date LIMIT ?",
            (start, end, limit),
        ).fetchall()
        return [_hit(row) for row in rows]

    def dates(self) -> list[str]:
        rows = self.conn.execute("SELECT DISTINCT date FROM records ORDER BY date").fetchall()
        return [row["date"] for row in rows]

    def metric_series(
        self, name: str | None = None, *, since: str | None = None, until: str | None = None
    ) -> list[sqlite3.Row]:
        clauses: list[str] = []
        params: list[object] = []
        if name:
            clauses.append("name = ?")
            params.append(name)
        if since:
            clauses.append("substr(record_id, 1, 8) >= ?")
            params.append(compact_day(since))
        if until:
            clauses.append("substr(record_id, 1, 8) <= ?")
            params.append(compact_day(until))
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        return self.conn.execute(
            f"SELECT * FROM metrics{where} ORDER BY record_id, name", params
        ).fetchall()

    def stats(self) -> dict[str, object]:
        total = self.conn.execute("SELECT COUNT(*) AS n FROM records").fetchone()["n"]
        span = self.conn.execute("SELECT MIN(date) AS a, MAX(date) AS b FROM records").fetchone()
        channels = self.conn.execute(
            "SELECT channel, COUNT(*) AS n FROM records GROUP BY channel ORDER BY n DESC"
        ).fetchall()
        metric_rows = self.conn.execute(
            "SELECT name, COUNT(*) AS n FROM metrics GROUP BY name ORDER BY n DESC"
        ).fetchall()
        days = self.conn.execute("SELECT COUNT(DISTINCT date) AS n FROM records").fetchone()["n"]
        return {
            "records": total,
            "days": days,
            "first": span["a"],
            "last": span["b"],
            "channels": {row["channel"]: row["n"] for row in channels},
            "metrics": {row["name"]: row["n"] for row in metric_rows},
        }
