"""由数据模型生成 `schema/record.json`。

运行 `pkbrain schema export` 重新生成。tests/test_schema.py 会核对仓库里的文件与生成结果一致，
所以这里不会和模型漂移。
"""

from __future__ import annotations

import json

from ..models import Record

SCHEMA_URI = "https://json-schema.org/draft/2020-12/schema"
SCHEMA_ID = "https://pkbrain.dev/schema/record.json"


def build() -> dict:
    schema = Record.model_json_schema()
    schema["$schema"] = SCHEMA_URI
    schema["$id"] = SCHEMA_ID
    schema["title"] = "PKBrain Record（PKBS 最小子集）"
    schema["description"] = "schema/record.json 由 pkbrain.models.Record 生成，请勿手改。"
    return schema


def dumps() -> str:
    return json.dumps(build(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
