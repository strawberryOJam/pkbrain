"""对话通道：把一场问答交给同一条流水线。

采集本身在 `brain.session`（它要用 schema 里的维度话术），这里只做通道适配。
M1 的对话是终端里的一问一答；M2 会多一路从聊天记录导入。
"""

from __future__ import annotations

from ..brain.session import Pair, assemble
from ..schema import PkbsSubset


def collect(pairs: list[Pair], schema: PkbsSubset) -> str:
    return assemble(pairs, schema)
