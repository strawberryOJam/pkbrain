"""落盘与检索的集成测试：Markdown 正本、SQLite 索引、中文全文检索。"""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

from pkbrain.brain import pipeline
from pkbrain.store import markdown, sqlite

TS = datetime(2026, 10, 16, 21, 30, tzinfo=timezone.utc)


def build(schema, text: str, day: date, **kwargs):
    record, _ = pipeline.build_record(text, day=day, schema=schema, now=TS, **kwargs)
    return record


def test_writes_markdown_and_indexes_it(tmp_path, schema):
    record = build(
        schema,
        "## D1 身体\n\n昨晚睡眠 6.5 小时。\n\n## 自由记录\n\n下雨了，没去散步。",
        date(2026, 10, 16),
    )
    path = pipeline.write_snapshot(record, schema=schema, data_dir=tmp_path)

    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "## D1 身体" in text
    assert "## 自由记录" in text
    assert "| sleep_hours | 6.5 | h |" in text

    with sqlite.Store(sqlite.db_path(tmp_path, schema), schema) as db:
        hits = db.search("睡眠")
        assert [h.id for h in hits] == [record.id]
        assert hits[0].dims == ["D1"]
        assert "6.5" in hits[0].text


def test_search_matches_free_text_and_metrics(tmp_path, schema):
    record = build(schema, "## 自由记录\n\n和客户谈了合同。", date(2026, 10, 15))
    pipeline.write_snapshot(record, schema=schema, data_dir=tmp_path)

    with sqlite.Store(sqlite.db_path(tmp_path, schema), schema) as db:
        assert db.search("合同")
        assert db.search("客户 合同")
        assert db.search("合同 失眠") == []
        assert db.search("不存在的词") == []


def test_search_filters(tmp_path, schema):
    older = build(schema, "## D2 情绪\n\n有点低落。", date(2026, 10, 1), privacy="P2")
    newer = build(schema, "## D1 身体\n\n跑了 30 分钟。", date(2026, 10, 10))
    for record in (older, newer):
        pipeline.write_snapshot(record, schema=schema, data_dir=tmp_path)

    with sqlite.Store(sqlite.db_path(tmp_path, schema), schema) as db:
        assert len(db.search(None)) == 2
        assert [h.id for h in db.search(None, since="2026-10-05")] == [newer.id]
        assert [h.id for h in db.search(None, until="2026-10-05")] == [older.id]
        assert [h.id for h in db.search(None, privacy="P2")] == [older.id]
        assert [h.id for h in db.search(None, dim="D1")] == [newer.id]
        assert [h.id for h in db.search(None, dim="D2")] == [older.id]
        assert db.search(None, dim="D4") == []


def test_covering_the_same_day_twice_keeps_both_records(tmp_path, schema):
    first = build(schema, "## D1 身体\n\n跑了 30 分钟。", date(2026, 10, 16))
    second = build(schema, "## D2 情绪\n\n有点累。", date(2026, 10, 16))
    for record in (first, second):
        pipeline.write_snapshot(record, schema=schema, data_dir=tmp_path)

    with sqlite.Store(sqlite.db_path(tmp_path, schema), schema) as db:
        assert db.stats()["records"] == 2
        assert len(db.by_date("2026-10-16")) == 2


def test_put_is_idempotent(tmp_path, schema):
    record = build(schema, "## D1 身体\n\n跑了 30 分钟。", date(2026, 10, 16))
    path = pipeline.write_snapshot(record, schema=schema, data_dir=tmp_path)

    with sqlite.Store(sqlite.db_path(tmp_path, schema), schema) as db:
        db.put(record, path)
        assert db.stats()["records"] == 1
        assert len(db.search("跑")) == 1

    # 重建索引后仍只有一条，且能查到
    db_file = sqlite.db_path(tmp_path, schema)
    db_file.unlink()
    with sqlite.Store(db_file, schema) as db:
        db.put(record, path)
        assert len(db.search("跑")) == 1


def test_metric_series_respects_dates(tmp_path, schema):
    for day, text in ((date(2026, 9, 30), "跑了 30 分钟。"), (date(2026, 10, 2), "跑了 45 分钟。")):
        pipeline.write_snapshot(
            build(schema, text, day), schema=schema, data_dir=tmp_path
        )

    with sqlite.Store(sqlite.db_path(tmp_path, schema), schema) as db:
        rows = db.metric_series("exercise_min", since="2026-10-01")
        assert [row["value"] for row in rows] == [45]
        assert rows[0]["unit"] == "min"
        assert rows[0]["dim"] == "D1"


def test_frontmatter_round_trips(tmp_path, schema):
    record = build(
        schema,
        "## D1 身体\n\n跑了 30 分钟。",
        date(2026, 10, 16),
        tags=["晚间", "有 空格"],
        privacy="P2",
    )
    path = pipeline.write_snapshot(record, schema=schema, data_dir=tmp_path)
    loaded = markdown.load_frontmatter(path)

    assert loaded.id == record.id
    assert loaded.date == record.date
    assert loaded.tags == ["晚间", "有 空格"]
    assert loaded.privacy == "P2"
    assert loaded.dims == record.dims
    assert loaded.confidence == record.confidence
    assert loaded.version == record.version


def test_path_is_date_partitioned(tmp_path, schema):
    record = build(schema, "跑了 30 分钟。", date(2026, 10, 16))
    path = markdown.record_path(tmp_path, record)
    assert path == Path(tmp_path) / "records" / "2026" / "10" / f"2026-10-16-R1-{record.id.rsplit('-', 1)[-1]}.md"
