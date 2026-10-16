from datetime import date

from pkbrain.brain import scheduler
from pkbrain.brain.questions import Question, load_state
from pkbrain.config import Config, ScheduleConfig

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


def test_notify_prints_on_other_platforms(capsys):
    assert scheduler.notify("准备好了", platform="linux") is False
    assert "准备好了" in capsys.readouterr().out


def test_notify_shells_out_on_macos():
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        return None

    assert scheduler.notify("准备好了", platform="darwin", run=fake_run) is True
    assert calls[0][0] == "osascript"
    assert 'display notification "准备好了"' in calls[0][2]


def test_notify_escapes_quotes():
    calls = []
    scheduler.notify('他说"好"', platform="darwin", run=lambda args, **kw: calls.append(args))
    assert '\\"好\\"' in calls[0][2]


def test_notify_swallows_failures():
    def boom(*args, **kwargs):
        raise OSError("没有 osascript")

    assert scheduler.notify("准备好了", platform="darwin", run=boom) is False


def test_scheduler_uses_the_configured_time(tmp_path, schema):
    scheduler_instance = scheduler.build_scheduler(
        Config(schedule=ScheduleConfig(time="23:45")), schema, tmp_path
    )
    job = scheduler_instance.get_job("nightly")
    assert job is not None
    fields = {field.name: str(field) for field in job.trigger.fields}
    assert fields["hour"] == "23"
    assert fields["minute"] == "45"
