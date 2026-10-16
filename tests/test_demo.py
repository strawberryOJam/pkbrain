"""演示数据：每天必须覆盖全部维度，指标必须全部落在区间内。"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from pkbrain import demo
from pkbrain.brain.questions import QuestionEngine
from pkbrain.brain.report import coverage
from pkbrain.demo import day_text
from pkbrain.store.sqlite import Store, db_path

END = date(2026, 10, 16)


def test_seed_writes_consecutive_days(tmp_path, schema):
    report = demo.seed(schema, tmp_path, end=END, days=14)

    assert report.records == 14
    assert report.first == END - timedelta(days=13)
    assert report.last == END
    assert (tmp_path / "records" / "2026" / "10").is_dir()


def test_every_day_covers_all_dimensions(tmp_path, schema):
    report = demo.seed(schema, tmp_path, end=END, days=10)
    assert report.dims == sorted(schema.record_types["R1"]["dims"])
    assert report.dims == ["D1", "D2", "D3", "D4"]

    with Store(db_path(tmp_path, schema), schema) as store:
        for day in ("2026-10-07", "2026-10-11", "2026-10-16"):
            records = store.by_date(day)
            assert len(records) == 1
            assert records[0].dims == ["D1", "D2", "D3", "D4"]


def test_every_day_has_all_metrics(tmp_path, schema):
    report = demo.seed(schema, tmp_path, end=END, days=8)
    # 没运动的那天少一个 exercise_min，其余七个每天都有
    assert report.metrics_min >= len(schema.metrics) - 1
    assert report.metrics_max == len(schema.metrics)

    with Store(db_path(tmp_path, schema), schema) as store:
        names: set[str] = set()
        for day in store.dates():
            rows = [
                row
                for row in store.metric_series()
                if row["record_id"].startswith(day.replace("-", ""))
            ]
            assert {row["name"] for row in rows} >= set(schema.metrics) - {"exercise_min"}
            for row in rows:
                metric = schema.metrics[row["name"]]
                assert metric.min <= row["value"] <= metric.max, f"{day} 的 {row['name']} 越界"
                assert row["unit"] == metric.unit
                names.add(row["name"])
        assert names == set(schema.metrics)


def test_seeded_records_are_marked_as_demo(tmp_path, schema):
    demo.seed(schema, tmp_path, end=END, days=3)
    with Store(db_path(tmp_path, schema), schema) as store:
        hits = store.search(None)
    assert hits
    for hit in hits:
        assert hit.tags == [demo.TAG]
        assert hit.source == demo.SOURCE
        assert hit.channel == "manual"


def test_coverage_is_complete(tmp_path, schema):
    demo.seed(schema, tmp_path, end=END, days=14)
    with Store(db_path(tmp_path, schema), schema) as store:
        share = coverage(store.dates(), today=END)
    assert share.days_recorded == 14
    assert share.rate == 1.0
    assert share.streak == 14
    assert share.meets(0.9)


def test_no_gap_questions_when_every_dimension_is_covered(tmp_path, schema):
    demo.seed(schema, tmp_path, end=END, days=3)
    with Store(db_path(tmp_path, schema), schema) as store:
        # 最后一条是当天，提问引擎看的是「今天之前最近的一条」
        engine = QuestionEngine(schema, store, data_dir=tmp_path, today=END + timedelta(days=1))
        kinds = [q.kind for q in engine.plan(limit=4)]
    assert "gap" not in kinds


def test_refuses_to_overwrite_existing_records(tmp_path, schema):
    demo.seed(schema, tmp_path, end=END, days=2)
    with pytest.raises(FileExistsError, match="已经有"):
        demo.seed(schema, tmp_path, end=END, days=2)

    report = demo.seed(schema, tmp_path, end=END, days=2, force=True)
    assert report.records == 2


def test_same_seed_gives_the_same_data(tmp_path, schema):
    import random

    first = day_text(date(2026, 10, 1), random.Random(7), 0)
    second = day_text(date(2026, 10, 1), random.Random(7), 0)
    assert first == second

    other = day_text(date(2026, 10, 1), random.Random(8), 0)
    assert other != first


def test_days_must_be_positive(tmp_path, schema):
    with pytest.raises(ValueError, match="至少是 1"):
        demo.seed(schema, tmp_path, days=0)


def test_seed_writes_demo_goals_once(tmp_path, schema):
    report = demo.seed(schema, tmp_path, end=END, days=2)
    assert report.goals_written is True
    assert (tmp_path / schema.paths["goals"]).is_file()

    goals = (tmp_path / schema.paths["goals"]).read_text(encoding="utf-8")
    assert "演示：把 PKBrain 用到第 14 天" in goals


def test_day_text_has_four_dimension_headings():
    import random

    text = day_text(date(2026, 10, 1), random.Random(1), 0)
    for heading in ("## D1 身体", "## D2 情绪", "## D3 事业", "## D4 关系"):
        assert heading in text
