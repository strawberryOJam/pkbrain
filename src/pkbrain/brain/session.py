"""一场会话：问题 + 回答 → 一份 R1 快照。

回答按问题的目标维度组装成 Markdown，交给和手动输入完全同一条流水线。
所以回答里的「睡了 7 小时」照样会被抽成指标，不需要另写一套。
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import date as Date
from datetime import datetime
from pathlib import Path
from typing import Callable

from ..models import Record
from ..schema import PkbsSubset
from ..store.sqlite import Store
from . import pipeline
from .extractor import Extraction, RulesExtractor
from .llm import PROMPT_VERSION, LLM, Reply
from .questions import Question

FREE_HEADING = "自由记录"


@dataclass(frozen=True)
class Pair:
    question: Question
    answer: str


@dataclass
class SessionResult:
    record: Record
    extraction: Extraction
    snapshot_path: Path
    transcript_path: Path
    reply: Reply


def new_session_id(day: Date) -> str:
    return f"session-{day:%Y%m%d}-{secrets.token_hex(3)}"


def heading_for(question: Question, schema: PkbsSubset) -> str:
    dim = question.dim
    if dim and dim in schema.dimensions:
        return f"## {dim} {schema.dimensions[dim].name}"
    return f"## {FREE_HEADING}"


def assemble(pairs: list[Pair], schema: PkbsSubset) -> str:
    """把问答拼成流水线的输入。没回答的问题不占位置。"""
    blocks: list[str] = []
    for pair in pairs:
        answer = pair.answer.strip()
        if not answer:
            continue
        blocks.append(f"{heading_for(pair.question, schema)}\n\n{answer}")
    if not blocks:
        raise ValueError("一个回答都没有")
    return "\n\n".join(blocks)


def transcript(pairs: list[Pair], *, day: Date, model: str, session_id: str) -> str:
    lines = [f"# {day} 会话 {session_id}", "", f"模型 {model}，模板 {PROMPT_VERSION}", ""]
    for index, pair in enumerate(pairs, start=1):
        answer = pair.answer.strip() or "（未回答）"
        lines += [f"## {index}. [{pair.question.kind}] {pair.question.text}", "", answer, ""]
        if pair.question.sources:
            lines += [f"依据 {'、'.join(pair.question.sources)}", ""]
    return "\n".join(lines).rstrip() + "\n"


def transcript_path(data_dir: Path, schema: PkbsSubset, record: Record) -> Path:
    short = record.id.rsplit("-", 1)[-1]
    return Path(data_dir) / schema.paths["sessions"] / f"{record.date}-{short}.md"


def context_for(question: Question, store: Store, *, limit: int = 300) -> str:
    """给模型润色问句时看的背景：这条问题所依据的那条记录。"""
    for source in question.sources:
        hit = store.by_id(source)
        if hit is not None:
            return hit.text[:limit]
    return ""


def run_session(
    questions: list[Question],
    *,
    schema: PkbsSubset,
    data_dir: Path,
    store: Store,
    day: Date,
    llm: LLM,
    ask: Callable[[str], str],
    session_id: str | None = None,
    privacy: str | None = None,
    polish: bool = True,
    now: datetime | None = None,
) -> SessionResult:
    """一场完整的会话：逐题问、收答案、落库。

    `ask` 收到要显示给用户的问句，返回答案。换行符与空行会被丢掉。
    """
    pairs: list[Pair] = []
    replies: list[Reply] = []
    for question in questions:
        prompt_text = question.text
        reply = Reply(text=prompt_text, model=getattr(llm, "model_name", llm.name))
        if polish:
            reply = llm.ask(question.text, context=context_for(question, store))
            prompt_text = reply.text
        answer = ask(prompt_text)
        replies.append(reply)
        pairs.append(Pair(question=question, answer=answer))

    return finalize(
        pairs,
        schema=schema,
        data_dir=data_dir,
        store=store,
        day=day,
        llm=llm,
        session_id=session_id,
        privacy=privacy,
        ask_replies=replies,
        now=now,
    )


def finalize(
    pairs: list[Pair],
    *,
    schema: PkbsSubset,
    data_dir: Path,
    store: Store,
    day: Date,
    llm: LLM,
    session_id: str | None = None,
    record_type: str = "R1",
    privacy: str | None = None,
    ask_replies: list[Reply] | None = None,
    now: datetime | None = None,
) -> SessionResult:
    """问答 → 记录 → Markdown 与 SQLite 双写，并留一份转写。"""
    answered = [pair for pair in pairs if pair.answer.strip()]
    floor = schema.session_limit("min_answers", 1)
    if len(answered) < floor:
        raise ValueError(f"至少要回答 {floor} 个问题，收到 {len(answered)} 个")

    text = assemble(pairs, schema)
    session_id = session_id or new_session_id(day)
    record, extraction = pipeline.build_record(
        text,
        day=day,
        schema=schema,
        channel="chat",
        privacy=privacy,
        source=session_id,
        record_type=record_type,
        extractor=RulesExtractor(schema),
        now=now,
    )

    model_name = getattr(llm, "model_name", llm.name)
    token_usage = [reply.tokens for reply in (ask_replies or []) if reply.tokens]
    record.agent_id = session_id
    record.model = model_name
    record.prompt_used = PROMPT_VERSION
    record.tokens = sum(token_usage) if token_usage else None

    path = transcript_path(data_dir, schema, record)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(transcript(pairs, day=day, model=model_name, session_id=session_id), encoding="utf-8")
    record.source = str(path)

    snapshot = pipeline.write_snapshot(record, schema=schema, data_dir=data_dir, database=store)
    return SessionResult(
        record=record,
        extraction=extraction,
        snapshot_path=snapshot,
        transcript_path=path,
        reply=llm.reflect(len(answered), len(extraction.metrics)),
    )

