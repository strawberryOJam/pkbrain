from datetime import date

from pkbrain.brain import scheduler
from pkbrain.brain.questions import Question, load_state
from pkbrain.config import Config, NotifyConfig, ScheduleConfig

TODAY = date(2026, 10, 16)


def test_pending_file_is_per_day(tmp_path, schema):
    assert scheduler.pending_file(tmp_path, schema, TODAY).name == "2026-10-16-pending.json"


def test_pending_round_trips(tmp_path):
    questions = [
        Question(kind="followup", text="后来呢？", sources=["20261015-R1-abc123"]),
        Question(kind="gap", text="身体怎么样？", dim="D1"),
    ]
    path = scheduler.save_pending(tmp_path / "sessions" / "x.json", questions)
    assert scheduler.load_pending(path) == questions


def test_missing_or_broken_pending_is_none(tmp_path):
    assert scheduler.load_pending(tmp_path / "nope.json") is None
    broken = tmp_path / "broken.json"
    broken.write_text("{ 不是 json", encoding="utf-8")
    assert scheduler.load_pending(broken) is None


def test_open_nightly_queues_questions_and_advances_state(tmp_path, schema):
    config = Config(schedule=ScheduleConfig(notify=False))
    questions = scheduler.open_nightly(config, schema, tmp_path, today=TODAY)

    assert [q.kind for q in questions] == ["reflection"]
    queued = scheduler.load_pending(scheduler.pending_file(tmp_path, schema, TODAY))
    assert queued == questions
    assert load_state(tmp_path, schema).last_reflection_date == "2026-10-16"


def test_open_nightly_notifies(tmp_path, schema, monkeypatch):
    sent = []
    monkeypatch.setattr(
        scheduler, "notify", lambda message, **kwargs: sent.append(message) or True
    )
    config = Config(schedule=ScheduleConfig(notify=True))
    scheduler.open_nightly(config, schema, tmp_path, today=TODAY)

    assert len(sent) == 1
    assert "pkbrain talk" in sent[0]


def test_open_nightly_stays_quiet_when_notify_is_off(tmp_path, schema, monkeypatch):
    sent = []
    monkeypatch.setattr(scheduler, "notify", lambda message, **kwargs: sent.append(message))
    scheduler.open_nightly(
        Config(schedule=ScheduleConfig(notify=False)), schema, tmp_path, today=TODAY
    )
    assert sent == []


def test_notify_shells_out_through_the_configured_hook(tmp_path, schema):
    """通知的去处在 config.toml 里：这里配一条 hook，看提醒真的落到它手上。"""
    log = tmp_path / "hook.log"
    script = tmp_path / "hook.sh"
    script.write_text(f'#!/bin/sh\nprintf "%s\\n" "$PKBRAIN_MESSAGE" >> {log}\n', encoding="utf-8")

    config = Config(
        schedule=ScheduleConfig(notify=True),
        notify=NotifyConfig(backend="command", command=f"sh {script}"),
    )
    scheduler.open_nightly(config, schema, tmp_path, today=TODAY)

    assert "pkbrain talk" in log.read_text(encoding="utf-8")


def test_scheduler_uses_the_configured_time(tmp_path, schema):
    scheduler_instance = scheduler.build_scheduler(
        Config(schedule=ScheduleConfig(time="23:45")), schema, tmp_path
    )
    job = scheduler_instance.get_job("nightly")
    assert job is not None
    fields = {field.name: str(field) for field in job.trigger.fields}
    assert fields["hour"] == "23"
    assert fields["minute"] == "45"
