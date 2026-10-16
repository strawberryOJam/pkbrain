"""手动通道：把一个文本文件读成流水线的输入。"""

from __future__ import annotations

from pathlib import Path


def collect(path: Path | str) -> str:
    return Path(path).expanduser().read_text(encoding="utf-8")


def collect_text(text: str) -> str:
    """给测试与 REPL 用，把已有字符串当输入。"""
    return text
