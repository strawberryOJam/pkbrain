"""目标清单（贯穿维 X2）。

存在 `<data_dir>/goals.md`，一个复选框一条。提问引擎按到期日挑最急的一条来问。

    - [ ] 联系客户确认合同 (2026-10-20) #D3
    - [ ] 每周跑三次 #D1
    - [x] 换掉那把椅子 (2026-10-01)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date as Date
from pathlib import Path

LINE_RE = re.compile(r"^\s*[-*]\s*\[(?P<mark>[ xX])\]\s*(?P<body>.+?)\s*$")
DUE_RE = re.compile(r"\((?P<due>\d{4}-\d{2}-\d{2})\)\s*$")
DIM_RE = re.compile(r"#(?P<dim>[DX]\d)\s*$")

TEMPLATE = """\
# 目标

一行一条。括号里写到期日，`#维度` 标记归属。下面两行是例子，去掉行首的 `<!--` 就能用：

<!-- - [ ] 联系客户确认合同 (2026-10-20) #D3 -->
<!-- - [ ] 每周跑三次 #D1 -->
"""


@dataclass(frozen=True)
class Goal:
    text: str
    done: bool = False
    due: Date | None = None
    dim: str | None = None
    line: int = 0

    def is_open(self) -> bool:
        return not self.done


def parse(text: str) -> list[Goal]:
    goals: list[Goal] = []
    for number, raw in enumerate(text.splitlines(), start=1):
        match = LINE_RE.match(raw)
        if not match:
            continue
        body = match.group("body")
        dim = None
        dim_match = DIM_RE.search(body)
        if dim_match:
            dim = dim_match.group("dim")
            body = body[: dim_match.start()].strip()
        due = None
        due_match = DUE_RE.search(body)
        if due_match:
            due = Date.fromisoformat(due_match.group("due"))
            body = body[: due_match.start()].strip()
        goals.append(
            Goal(text=body, done=match.group("mark").lower() == "x", due=due, dim=dim, line=number)
        )
    return goals


def load(data_dir: Path, schema) -> list[Goal]:
    path = Path(data_dir) / schema.paths["goals"]
    if not path.is_file():
        return []
    return parse(path.read_text(encoding="utf-8"))


def write_default(data_dir: Path, schema, *, force: bool = False) -> Path:
    path = Path(data_dir) / schema.paths["goals"]
    if path.exists() and not force:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(TEMPLATE, encoding="utf-8")
    return path


def most_urgent(goals: list[Goal], today: Date, *, within_days: int | None = None) -> Goal | None:
    """未完成的目标里，最该被问的一条：先看到期的，再看没有到期日的。"""
    pending = [g for g in goals if g.is_open()]
    if not pending:
        return None

    dated = [g for g in pending if g.due is not None]
    if dated:
        due_soon = [g for g in dated if within_days is None or (g.due - today).days <= within_days]
        if due_soon:
            return min(due_soon, key=lambda g: g.due)
    undated = [g for g in pending if g.due is None]
    return undated[0] if undated else None
