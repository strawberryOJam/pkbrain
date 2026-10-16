"""流水线：输入文本 → 抽取 → 组装记录 → Markdown 与 SQLite 双写。

M0 的入口是手动输入。后续的对话与录音采集器产出同样的文本，走的还是这条流水线。
"""

from __future__ import annotations

import secrets
from datetime import date as Date
from datetime import datetime
from pathlib import Path

from .. import store
from ..models import Record
from ..schema import PkbsSubset
from .extractor import Extraction, Extractor, RulesExtractor


def new_id(day: Date, record_type: str = "R1") -> str:
    return f"{day:%Y%m%d}-{record_type}-{secrets.token_hex(3)}"


def score_confidence(extraction: Extraction, schema: PkbsSubset) -> float:
    """M0 的固定公式，见 docs/PKBS-MIN.md 第 7 节。"""
    conf = schema.confidence
    if not extraction.metrics:
        return conf["base"]
    return round(min(conf["with_sections"] + conf["per_metric"] * len(extraction.metrics), conf["max"]), 2)


def build_record(
    text: str,
    *,
    day: Date,
    schema: PkbsSubset,
    channel: str = "manual",
    privacy: str | None = None,
    source: str = "manual",
    tags: list[str] | None = None,
    record_type: str = "R1",
    extractor: Extractor | None = None,
    now: datetime | None = None,
) -> tuple[Record, Extraction]:
    engine = extractor or RulesExtractor(schema)
    extraction = engine.extract(text)
    if extraction.is_empty():
        raise ValueError("没有抽到任何内容：正文为空，或所有指标都越界")

    record = Record(
        id=new_id(day, record_type),
        type=record_type,
        ts=now or datetime.now().astimezone(),
        date=day,
        dims=extraction.dims,
        source=source,
        confidence=score_confidence(extraction, schema),
        privacy=privacy or schema.default_privacy,
        version=schema.version,
        tags=list(tags or []),
        channel=channel,
        sections=dict(extraction.sections),
        free_text=extraction.free_text,
        metrics=dict(extraction.metrics),
    )
    return record, extraction


def write_snapshot(
    record: Record,
    *,
    schema: PkbsSubset,
    data_dir: Path,
    store_path: Path | None = None,
) -> Path:
    """Markdown 与 SQLite 双写。返回 Markdown 路径。"""
    path = store.markdown.record_path(data_dir, record)
    store.markdown.write(path, store.markdown.render(record, schema))

    db = store_path or store.sqlite.db_path(data_dir, schema)
    with store.sqlite.Store(db, schema) as database:
        database.put(record, path=path)
    return path
