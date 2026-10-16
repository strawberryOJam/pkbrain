"""中文检索用的文本切分。

SQLite 的 unicode61 分词器不切中文：一整串汉字会成为一个 token。
所以在入索引前把汉字逐个用空格隔开，查询时再把关键词做成同样的短语。
"""

from __future__ import annotations

import re

_CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\U00020000-\U0002ffff]")


def segment(text: str) -> str:
    """在 CJK 字符两侧插空格，其余字符原样保留。连续空格会被压成一个。"""
    spaced = "".join(f" {ch} " if _CJK.match(ch) else ch for ch in text)
    return re.sub(r" {2,}", " ", spaced)


def to_match_query(query: str) -> str:
    """把用户输入变成一个 FTS5 MATCH 表达式。

    每个词做成一个短语，词之间取 AND：「睡眠 心情」→ `"睡 眠" AND "心 情"`。
    """
    terms = [t for t in re.split(r"\s+", query.strip()) if t]
    phrases = []
    for term in terms:
        cleaned = term.replace('"', "")
        parts = segment(cleaned).split()
        if not parts:
            continue
        phrases.append('"' + " ".join(parts) + '"')
    return " AND ".join(phrases)
