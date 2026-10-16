"""schema/ 的三个文件必须互相自洽，且 record.json 与数据模型一致。"""

import csv

from pkbrain.models import Record
from pkbrain.schema import load_metrics, load_schema
from pkbrain.store import record_json


def test_checked_in_record_json_matches_the_model(schema):
    checked_in = (schema.source_dir / "record.json").read_text(encoding="utf-8")
    assert checked_in == record_json.dumps(), "跑了 `pkbrain schema export` 之后要提交 schema/record.json"


def test_record_json_lists_every_field(schema):
    props = record_json.build()["properties"]
    assert set(props) == set(Record.model_fields)


def test_metrics_csv_is_well_formed(schema):
    metrics = load_metrics(schema.source_dir / "metrics.csv")
    assert metrics, "指标字典不能为空"
    for metric in metrics.values():
        assert metric.dim in schema.dimensions
        assert metric.type in {"int", "float"}
        assert metric.min is None or metric.max is None or metric.min <= metric.max
        assert metric.regex().groups == 1


def test_metrics_csv_has_no_duplicate_names(schema):
    with (schema.source_dir / "metrics.csv").open(encoding="utf-8", newline="") as fh:
        names = [row["name"] for row in csv.DictReader(fh)]
    assert len(names) == len(set(names))


def test_every_dimension_resolves_by_code_and_by_name(schema):
    for code, dim in schema.dimensions.items():
        assert schema.dimension_of(code).code == code
        assert schema.dimension_of(f"{code} {dim.name}").code == code
        assert schema.dimension_of(dim.name).code == code


def test_unknown_heading_is_not_a_dimension(schema):
    assert schema.dimension_of("今日总结") is None
