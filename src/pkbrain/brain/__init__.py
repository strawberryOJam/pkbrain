"""大脑：抽取、快照组装、检索问答。

M0 只有规则抽取与快照组装。提问引擎（每晚按记忆选问题）是 M1 的事。
"""

from . import extractor, pipeline

__all__ = ["extractor", "pipeline"]
