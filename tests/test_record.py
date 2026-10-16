from datetime import date, datetime

import pytest

from pkbrain.brain import pipeline
from pkbrain.models import Record
from pkbrain.schema import load_schema


def make_record(schema, **overrides) -> Record:
    defaults = dict(
        id="20261016-R1-a1b2c3",
        ts=datetime(2026, 10, 16, 21, 30),
        date=date(2026, 10, 16),
        dims=["D1", "D2"],
        source="examples/today.md",
        confidence=0.7,
        privacy="P1",
        version=schema.version,
        tags=["晚间"],
        channel="manual",
        sections={"D1": "跑了 30 分钟。", "D2": "还行。"},
        free_text="下雨了。",
        metrics={"exercise_min": 30},
    )
    defaults.update(overrides)
    return Record(**defaults)


def test_frontmatter_field_order_is_stable(schema):
    record = make_record(schema)
    assert Record.frontmatter_fields()[:4] == ["id", "type", "ts", "date"]
    assert "sections" not in Record.frontmatter_fields()
    assert "free_text" not in Record.frontmatter_fields()
    assert "metrics" not in Record.frontmatter_fields()


def test_confidence_scoring(schema):
    record, extraction = pipeline.build_record(
        "跑了 30 分钟。", day=date(2026, 10, 16), schema=schema, now=datetime(2026, 10, 16, 21, 0)
    )
    assert extraction.metrics == {"exercise_min": 30}
    # 0.5 + 0.1 × 1 个指标
    assert record.confidence == pytest.approx(0.6)

    free_only, _ = pipeline.build_record(
        "今天很累。", day=date(2026, 10, 16), schema=schema, now=datetime(2026, 10, 16, 21, 0)
    )
    assert free_only.confidence == schema.confidence["base"]


def test_confidence_is_capped(schema):
    text = "睡眠 6 小时，质量 3，跑了 30 分钟，体重 71 公斤，精力 3，心情 3，焦虑 4，专注 4 小时。"
    record, _ = pipeline.build_record(
        text, day=date(2026, 10, 16), schema=schema, now=datetime(2026, 10, 16, 21, 0)
    )
    assert len(record.metrics) == 8
    assert record.confidence == schema.confidence["max"]


def test_rejects_empty_input(schema):
    with pytest.raises(ValueError, match="没有抽到任何内容"):
        pipeline.build_record(
            "   \n\n", day=date(2026, 10, 16), schema=schema, now=datetime(2026, 10, 16, 21, 0)
        )


def test_record_id_shape(schema):
    record, _ = pipeline.build_record(
        "跑了 30 分钟。", day=date(2026, 10, 16), schema=schema, now=datetime(2026, 10, 16, 21, 0)
    )
    assert record.id.startswith("20261016-R1-")
    assert len(record.id.rsplit("-", 1)[-1]) == 6


def test_model_rejects_bad_dimension():
    with pytest.raises(ValueError):
        Record(
            id="20261016-R1-a1b2c3",
            ts=datetime(2026, 10, 16),
            date=date(2026, 10, 16),
            dims=["身体"],
        )


def test_schema_is_loaded_from_the_repo(schema):
    assert schema.version == "0.2.0-min"
    assert load_schema() is schema  # 带缓存，同一个对象
    assert (schema.source_dir / "metrics.csv").is_file()
