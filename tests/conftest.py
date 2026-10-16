import pytest

from pkbrain.schema import load_schema


@pytest.fixture(scope="session")
def schema():
    return load_schema()
