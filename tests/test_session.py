from datetime import date

import pytest

from pkbrain.brain import session
from pkbrain.brain.llm import PROMPT_VERSION, Reply, TemplateLLM
from pkbrain.brain.questions import Question

DAY = date(2026, 10, 16)


def question(kind="gap", text="昨天身体怎么样？", dim=None, sources=None):
    return Question(kind=kind, text=text, dim=dim, sources=sources or [])


def test_assemble_maps_answers_to_dimension_sections(schema):
    pairs = [
        session.Pair(question("gap", dim="D1"), "跑了 30 分钟。"),
        session.Pair(question("gap", dim="D2"), "心情还行。"),
    ]
    text = session.assemble(pairs, schema)
    assert "## D1 身体\n\n跑了 30 分钟。" in text
    assert "## D2 情绪\n\n心情还行。" in text


def test_assemble_sends_dimensionless_answers_to_free_text(schema):
    text = session.assemble([session.Pair(question("reflection"), "今年想少加点班。")], schema)
    assert text.startswith("## 自由记录")
    assert "今年想少加点班。" in text


def test_assemble_skips_unanswered_questions(schema):
    pairs = [
        session.Pair(question("gap", dim="D1"), "  "),
        session.Pair(question("gap", dim="D2"), "还行。"),
    ]
    text = session.assemble(pairs, schema)
    assert "D1" not in text
    assert "还行。" in text


def test_assemble_rejects_an_empty_session(schema):
    with pytest.raises(ValueError, match="一个回答都没有"):
        session.assemble([session.Pair(question(), "")], schema)


def test_transcript_keeps_questions_and_answers():
    pairs = [
        session.Pair(question("followup", "你上次记了「明天见客户」，后来怎么样了？", sources=["20261015-R1-abc123"]), "见了，签了。"),
        session.Pair(question("gap", "昨天心情如何？", dim="D2"), ""),
    ]
    text = session.transcript(pairs, day=DAY, model="template", session_id="session-1")
    assert "[followup]" in text
    assert "签了。" in text
    assert "（未回答）" in text
    assert "20261015-R1-abc123" in text


def test_run_session_writes_snapshot_and_transcript(schema, store):
    questions = [question("gap", "昨天身体怎么样？", dim="D1")]
    result = session.run_session(
        questions,
        schema=schema,
        data_dir=store.path.parent,
        store=store,
        day=DAY,
        llm=TemplateLLM(),
        ask=lambda _: "昨晚睡了 7 小时，跑了 30 分钟。",
    )

    assert result.snapshot_path.is_file()
    assert result.transcript_path.is_file()
    assert result.record.channel == "chat"
    assert result.record.metrics == {"sleep_hours": 7.0, "exercise_min": 30}
    assert result.record.dims == ["D1"]
    assert result.record.model == "template"
    assert result.record.prompt_used == PROMPT_VERSION
    assert result.record.source == str(result.transcript_path)

    transcript = result.transcript_path.read_text(encoding="utf-8")
    assert "昨天身体怎么样？" in transcript
    assert "昨晚睡了 7 小时" in transcript


def test_run_session_records_the_agent_session(schema, store):
    result = session.run_session(
        [question("reflection", "这周有什么值得的？")],
        schema=schema,
        data_dir=store.path.parent,
        store=store,
        day=DAY,
        llm=TemplateLLM(),
        ask=lambda _: "把检索调通了。",
    )
    assert result.record.agent_id.startswith("session-20261016-")
    assert result.record.dims == []


def test_ask_gets_the_polished_question(schema, store):
    """换模型后，用户看到的是模型改写过的问句。"""
    seen: list[str] = []

    class Shouty:
        name = "shouty"

        def ask(self, text, *, context=""):
            return Reply(text=f"{text}！！", model=self.name)

        def reflect(self, answered, metrics):
            return Reply(text="好。", model=self.name)

    session.run_session(
        [question("gap", "昨天身体怎么样？", dim="D1")],
        schema=schema,
        data_dir=store.path.parent,
        store=store,
        day=DAY,
        llm=Shouty(),
        ask=lambda text: seen.append(text) or "跑了 30 分钟。",
    )
    assert seen == ["昨天身体怎么样？！！"]


def test_no_polish_uses_the_raw_question(schema, store):
    seen = []
    session.run_session(
        [question("gap", "昨天身体怎么样？", dim="D1")],
        schema=schema,
        data_dir=store.path.parent,
        store=store,
        day=DAY,
        llm=TemplateLLM(),
        ask=lambda text: seen.append(text) or "跑了 30 分钟。",
        polish=False,
    )
    assert seen == ["昨天身体怎么样？"]


def test_finalize_needs_an_answer(schema, store):
    with pytest.raises(ValueError, match="至少要回答 1 个问题"):
        session.finalize(
            [session.Pair(question(), "   ")],
            schema=schema,
            data_dir=store.path.parent,
            store=store,
            day=DAY,
            llm=TemplateLLM(),
        )


def test_context_for_uses_the_source_record(schema, store, add):
    record, _ = add("## D1 身体\n\n明天要去见客户。", date(2026, 10, 15))
    assert "见客户" in session.context_for(question(sources=[record.id]), store)
    assert session.context_for(question(sources=["没有这个 id"]), store) == ""
