from datetime import date, datetime

import pytest

from pkbrain.brain import pipeline
from pkbrain.schema import load_schema
from pkbrain.store.sqlite import Store, db_path

NOW = datetime(2026, 10, 16, 21, 0)


@pytest.fixture(scope="session")
def schema():
    return load_schema()


@pytest.fixture
def store(tmp_path, schema):
    """一个开好的数据目录 + 数据库连接。data_dir 是 store.path.parent。"""
    with Store(db_path(tmp_path, schema), schema) as database:
        yield database


@pytest.fixture
def add(store, schema):
    """往当前数据目录里塞一条已抽取好的记录。"""

    def _add(text: str, day: date, **kwargs):
        record, extraction = pipeline.build_record(
            text, day=day, schema=schema, now=NOW, **kwargs
        )
        pipeline.write_snapshot(
            record, schema=schema, data_dir=store.path.parent, database=store
        )
        return record, extraction

    return _add
