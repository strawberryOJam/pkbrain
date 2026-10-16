"""提问引擎：按记忆挑今晚问什么。

四级优先级（产品文档《个性化回环》）：

1. 昨日快照的缺口与悬而未决项
2. 目标追踪
3. 精神层反思轮换（每周至少一次）
4. 随机回顾旧记忆

优先级 1 最多占两个名额，把第三个留给 2–4，免得每晚都只问缺口。
第 3 级带「每周至少一次」的硬约束，所以它到期时插在目标前面，不会被挤掉。见 ADR-0005。
"""

from __future__ import annotations

import json
import random
import re
from dataclasses import asdict, dataclass, field
from datetime import date as Date
from datetime import timedelta
from pathlib import Path

from .. import goals as goals_module
from ..schema import PkbsSubset
from ..store.sqlite import Hit, Store

SENTENCE_SPLIT = re.compile(r"[。！？!?\n]+")
QUOTE_LIMIT = 28
REFLECTION_INTERVAL_DAYS = 7
GOAL_HORIZON_DAYS = 7


@dataclass(frozen=True)
class Question:
    kind: str  # followup | gap | goal | reflection | revisit
    text: str
    dim: str | None = None
    sources: list[str] = field(default_factory=list)


@dataclass
class State:
    """提问引擎的轮换状态，存在 `<data_dir>/state.json`。"""

    reflection_index: int = 0
    last_reflection_date: str | None = None

    def days_since_reflection(self, today: Date) -> int | None:
        if not self.last_reflection_date:
            return None
        return (today - Date.fromisoformat(self.last_reflection_date)).days

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> State:
        return cls(
            reflection_index=int(data.get("reflection_index", 0)),
            last_reflection_date=data.get("last_reflection_date"),
        )


def state_path(data_dir: Path, schema: PkbsSubset) -> Path:
    return Path(data_dir) / schema.paths["state"]


def load_state(data_dir: Path, schema: PkbsSubset) -> State:
    path = state_path(data_dir, schema)
    if not path.is_file():
        return State()
    try:
        return State.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, ValueError):
        return State()


def save_state(data_dir: Path, schema: PkbsSubset, state: State) -> None:
    path = state_path(data_dir, schema)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _quote(text: str, limit: int = QUOTE_LIMIT) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


class QuestionEngine:
    def __init__(
        self,
        schema: PkbsSubset,
        store: Store,
        *,
        data_dir: Path,
        today: Date,
        state: State | None = None,
        rng: random.Random | None = None,
    ) -> None:
        self.schema = schema
        self.store = store
        self.data_dir = Path(data_dir)
        self.today = today
        self.state = state if state is not None else load_state(self.data_dir, schema)
        self.rng = rng or random.Random(today.toordinal())

    # ---- 对外 ---------------------------------------------------------

    def plan(self, limit: int | None = None) -> list[Question]:
        """挑出今晚要问的问题。不写状态。"""
        budget = limit or self.schema.session_limit("max_questions", 3)
        questions: list[Question] = []

        questions += self._open_loops()[:1]
        questions += self._gaps()[:1]
        if self._reflection_due():
            questions += self._reflection()[:1]
        questions += self._goal()[:1]
        questions += self._revisit()[:1]

        return questions[:budget]

    def commit(self, questions: list[Question]) -> State:
        """把这一轮问过的记进状态：反思轮换只在这里推进。"""
        for question in questions:
            if question.kind == "reflection":
                pool = self.schema.reflections()
                self.state.reflection_index = (self.state.reflection_index + 1) % max(len(pool), 1)
                self.state.last_reflection_date = self.today.isoformat()
                break
        save_state(self.data_dir, self.schema, self.state)
        return self.state

    # ---- 优先级 1：缺口与悬而未决项 -----------------------------------

    def _last_record(self) -> Hit | None:
        yesterday = (self.today - timedelta(days=1)).isoformat()
        hits = self.store.by_date(yesterday)
        if hits:
            return hits[-1]
        recent = self.store.latest_before(self.today.isoformat())
        if recent and (self.today - Date.fromisoformat(recent.date)).days <= REFLECTION_INTERVAL_DAYS:
            return recent
        return None

    def _open_loops(self) -> list[Question]:
        """昨天写着「明天要…」的事，今天追问进展。"""
        record = self._last_record()
        if record is None:
            return []
        markers = self.schema.open_markers()
        if not markers:
            return []
        for sentence in SENTENCE_SPLIT.split(record.text):
            sentence = sentence.strip()
            if not sentence or not any(marker in sentence for marker in markers):
                continue
            return [
                Question(
                    kind="followup",
                    text=f"你上次记了「{_quote(sentence)}」，后来怎么样了？",
                    sources=[record.id],
                )
            ]
        return []

    def _gaps(self) -> list[Question]:
        """昨天的快照缺哪个维度，就补问哪个。"""
        record = self._last_record()
        if record is None:
            return []
        expected = self.schema.record_types.get("R1", {}).get("dims", [])
        missing = [d for d in expected if d not in record.dims]
        if not missing:
            return []
        dim = missing[0]
        probe = self.schema.probe(dim)
        if not probe:
            return []
        return [Question(kind="gap", text=probe, dim=dim, sources=[record.id])]

    # ---- 优先级 2：目标 ------------------------------------------------

    def _goal(self) -> list[Question]:
        goal = goals_module.most_urgent(
            goals_module.load(self.data_dir, self.schema),
            self.today,
            within_days=GOAL_HORIZON_DAYS,
        )
        if goal is None:
            return []
        if goal.due is not None:
            days = (goal.due - self.today).days
            when = f"还有 {days} 天到期" if days >= 0 else f"已经过期 {abs(days)} 天"
            text = f"目标「{goal.text}」{when}，现在到哪一步了？"
        else:
            text = f"目标「{goal.text}」最近推进了吗？"
        return [Question(kind="goal", text=text, dim=goal.dim, sources=[f"goals.md:{goal.line}"])]

    # ---- 优先级 3：精神层反思 ------------------------------------------

    def _reflection_due(self) -> bool:
        pool = self.schema.reflections()
        if not pool:
            return False
        days = self.state.days_since_reflection(self.today)
        return days is None or days >= REFLECTION_INTERVAL_DAYS

    def _reflection(self) -> list[Question]:
        pool = self.schema.reflections()
        if not pool:
            return []
        text = pool[self.state.reflection_index % len(pool)]
        return [Question(kind="reflection", text=text, dim=None)]

    # ---- 优先级 4：回顾旧记忆 ------------------------------------------

    def _revisit(self) -> list[Question]:
        for offset in self.schema.revisit_days():
            target = self.today - timedelta(days=offset)
            window = self.store.between(
                (target - timedelta(days=3)).isoformat(), (target + timedelta(days=3)).isoformat()
            )
            if not window:
                continue
            record = self.rng.choice(window)
            return [
                Question(
                    kind="revisit",
                    text=f"{offset} 天前的今天，你记了「{_quote(record.text, 20)}」，现在回头看是什么感觉？",
                    sources=[record.id],
                )
            ]
        return []
