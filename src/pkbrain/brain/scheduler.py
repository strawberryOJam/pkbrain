"""定时：每晚到点把今晚的问题备好，并提醒人来答。

`pkbrain serve` 会一直挂着跑（APScheduler 进程内定时）。不挂也没关系：
`pkbrain talk` 本来就会现挑问题。这个守护进程只是让「每晚 10 点被提醒」成立。
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date as Date
from datetime import datetime
from pathlib import Path
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from ..config import Config, NotifyConfig
from ..notify import send as _send
from ..schema import PkbsSubset
from ..store.sqlite import Store, db_path
from .questions import Question, QuestionEngine

TITLE = "PKBrain"


def pending_file(data_dir: Path, schema: PkbsSubset, day: Date) -> Path:
    return Path(data_dir) / schema.paths["sessions"] / f"{day.isoformat()}-pending.json"


def save_pending(path: Path, questions: list[Question]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([asdict(q) for q in questions], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def load_pending(path: Path) -> list[Question] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError):
        return None
    return [Question(**item) for item in data]


def notify(
    message: str,
    *,
    title: str = TITLE,
    settings: NotifyConfig | None = None,
    **kwargs,
) -> bool:
    """发一条通知：系统通知或你在 config.toml 里配的 hook。发不出去不算失败。

    真正的投递在 `pkbrain.notify`，这里只留一个 scheduler 侧的入口，方便替换与测试。
    """
    return _send(message, title=title, settings=settings, **kwargs).delivered


def open_nightly(
    config: Config,
    schema: PkbsSubset,
    data_dir: Path,
    *,
    today: Date | None = None,
    now: datetime | None = None,
) -> list[Question]:
    """挑问题、推进状态、排队等答、提醒人。返回这一轮的问题。"""
    day = today or Date.today()
    with Store(db_path(data_dir, schema), schema) as store:
        engine = QuestionEngine(schema, store, data_dir=data_dir, today=day)
        questions = engine.plan()
        engine.commit(questions)

    if questions:
        save_pending(pending_file(data_dir, schema, day), questions)
        head = questions[0].text
        extra = f"，还有 {len(questions) - 1} 个" if len(questions) > 1 else ""
        if config.schedule.notify:
            notify(
                f"今晚的问题：{head}{extra}　跑 pkbrain talk 回答。",
                settings=config.notify,
            )
    return questions


def build_scheduler(config: Config, schema: PkbsSubset, data_dir: Path) -> BlockingScheduler:
    """按 config 的 schedule.time 建一个每晚触发的调度器。"""
    hour, minute = config.schedule.hour_minute
    scheduler = BlockingScheduler()
    scheduler.add_job(
        open_nightly,
        CronTrigger(hour=hour, minute=minute),
        args=[config, schema, data_dir],
        id="nightly",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    return scheduler
