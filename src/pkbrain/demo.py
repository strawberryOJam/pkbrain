"""演示数据：生成连续 N 天的快照，每天覆盖全部维度。

两种用途：想看一眼「用了一阵子的 PKBrain」长什么样，或开发时需要一份稳定的数据集。

生成的记录带 `tags: [演示数据]` 与 `source: seed_demo`，和真人记录一眼分得开。
它解决的是「没数据时看不到样子」，不代替 M1 的 14 天验收——那条说的是你自己连续用了 14 天。
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date as Date
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

from .models import Record
from .schema import PkbsSubset
from .store.sqlite import Store, db_path

DEFAULT_DAYS = 40
DEFAULT_SEED = 20261016
TAG = "演示数据"
SOURCE = "seed_demo"
TZ = timezone(timedelta(hours=8))

MOOD_LINES = [
    "没什么大事，比较平静。",
    "赶进度，有点烦。",
    "聊完轻松了不少。",
    "效率高，心情跟着好。",
    "一整天提不起劲。",
    "被一件小事逗乐了。",
]
WORK_LINES = [
    "把检索的排序调通了。",
    "写完了两份 ADR。",
    "修了三个 bug，都是自己挖的坑。",
    "开会占掉半天，没写出什么。",
    "把录音采集的方案定下来了。",
    "又推翻了自己昨天的方案。",
]
RELATION_LINES = [
    "和 L 通了电话，聊了半小时。",
    "见了老朋友，吃了顿长的。",
    "一天没和谁说话。",
    "和同事一起吃了饭。",
    "陪家人散步，走了很远。",
    "给爸妈打了电话。",
]
FREE_LINES = [
    "晚上去散步了。",
    "想到周报模板可以按维度分段。",
    "明天要把合同发过去。",
    "睡前没看手机，感觉不错。",
    "下周打算把体检约了。",
    "翻出去年的照片看了一会儿。",
    "把桌面收拾干净了，人也松快些。",
]

GOALS_TEMPLATE = """\
# 目标

<!-- - [ ] 每周跑三次 #D1 -->
- [ ] 演示：把 PKBrain 用到第 14 天 (2026-10-30) #D3
- [ ] 演示：每周跑三次 #D1
"""


@dataclass(frozen=True)
class SeedReport:
    days: int
    first: Date
    last: Date
    records: int
    metrics_min: int
    metrics_max: int
    dims: list[str]
    data_dir: Path
    goals_written: bool


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _sentence(pool: list[str], rng: random.Random) -> str:
    return pool[rng.randrange(len(pool))]


def day_text(day: Date, rng: random.Random, offset: int) -> str:
    """一天的四段正文。四段都写满，指标全部落在 schema 的区间里。

    `offset` 是从第一天起的第几天，用来让睡眠和体重有个缓慢的趋势，别像白噪声。
    """
    sleep = round(_clamp(rng.gauss(7.0, 0.8) - offset / 40, 4.5, 9.0) * 2) / 2
    quality = int(_clamp(round(1 + (sleep - 4) / 1.2), 1, 5))
    exercise = 0 if rng.random() < 0.4 else rng.choice([20, 30, 40, 45, 60])
    weight = round(72.5 - 0.02 * offset + rng.uniform(-0.4, 0.4), 1)
    energy = int(_clamp(round(1 + (sleep - 4) / 1.3), 1, 5))
    mood = int(_clamp(round((sleep - 3.5) / 0.9 + rng.uniform(-0.6, 0.6)), 1, 5))
    anxiety = int(_clamp(round(4 - mood + rng.uniform(-0.5, 0.8)), 1, 5))
    weekend = day.weekday() >= 5
    focus = round(rng.uniform(1.0, 3.0) if weekend else rng.uniform(2.5, 7.0), 1)

    exercise_line = f"跑了 {exercise} 分钟。" if exercise else "没运动。"
    return "\n".join(
        [
            f"# {day} 晚间快照",
            "",
            "## D1 身体",
            "",
            f"睡眠 {sleep:g} 小时，质量 {quality}。{exercise_line}体重 {weight:g} 公斤，精力 {energy}。",
            "",
            "## D2 情绪",
            "",
            f"心情 {mood}，焦虑 {anxiety}。{_sentence(MOOD_LINES, rng)}",
            "",
            "## D3 事业",
            "",
            f"专注 {focus:g} 小时。{_sentence(WORK_LINES, rng)}",
            "",
            "## D4 关系",
            "",
            _sentence(RELATION_LINES, rng),
            "",
            "## 自由记录",
            "",
            _sentence(FREE_LINES, rng),
            "",
        ]
    )


def existing_records(data_dir: Path, schema: PkbsSubset) -> list[Path]:
    root = Path(data_dir) / schema.paths["records"]
    return sorted(root.rglob("*.md")) if root.is_dir() else []


def seed(
    schema: PkbsSubset,
    data_dir: Path,
    *,
    end: Date | None = None,
    days: int = DEFAULT_DAYS,
    seed_value: int = DEFAULT_SEED,
    force: bool = False,
) -> SeedReport:
    """往 data_dir 写入连续 days 天的快照。已有记录时拒绝，除非 force。"""
    from .brain import pipeline  # 放这里，免得 store 反向依赖 brain

    data_dir = Path(data_dir)
    if days < 1:
        raise ValueError("days 至少是 1")
    already = existing_records(data_dir, schema)
    if already and not force:
        raise FileExistsError(
            f"{data_dir} 里已经有 {len(already)} 条记录。"
            "演示数据要写进空目录，或者加 force 硬写。"
        )

    last = end or Date.today()
    first = last - timedelta(days=days - 1)
    rng = random.Random(seed_value)

    records: list[Record] = []
    metric_counts: list[int] = []
    with Store(db_path(data_dir, schema), schema) as store:
        for offset in range(days):
            day = first + timedelta(days=offset)
            text = day_text(day, rng, offset)
            record, extraction = pipeline.build_record(
                text,
                day=day,
                schema=schema,
                channel="manual",
                source=SOURCE,
                tags=[TAG],
                now=datetime.combine(day, time(21, 30), tzinfo=TZ),
            )
            expected = schema.record_types["R1"]["dims"]
            if extraction.dims != sorted(expected):
                raise AssertionError(f"{day} 的维度不全：{extraction.dims} != {sorted(expected)}")
            if extraction.warnings:
                raise AssertionError(f"{day} 的抽取有告警：{extraction.warnings}")
            metric_counts.append(len(extraction.metrics))
            pipeline.write_snapshot(record, schema=schema, data_dir=data_dir, database=store)
            records.append(record)

    goals_written = False
    goals_path = data_dir / schema.paths["goals"]
    if not goals_path.exists():
        goals_path.parent.mkdir(parents=True, exist_ok=True)
        goals_path.write_text(GOALS_TEMPLATE, encoding="utf-8")
        goals_written = True

    return SeedReport(
        days=days,
        first=first,
        last=last,
        records=len(records),
        metrics_min=min(metric_counts),
        metrics_max=max(metric_counts),
        dims=records[-1].dims,
        data_dir=data_dir,
        goals_written=goals_written,
    )


def latest_record_path(data_dir: Path, schema: PkbsSubset) -> Path | None:
    paths = existing_records(data_dir, schema)
    return paths[-1] if paths else None


def describe(report: SeedReport, schema: PkbsSubset) -> str:
    dims = ", ".join(report.dims)
    spread = (
        f"{report.metrics_min} 个指标"
        if report.metrics_min == report.metrics_max
        else f"{report.metrics_min}–{report.metrics_max} 个指标"
    )
    lines = [
        f"写入 {report.records} 天（{report.first} → {report.last}）",
        f"每天覆盖 {dims}，{spread}",
        f"标记 tags=[{TAG}] source={SOURCE}",
    ]
    if report.goals_written:
        lines.append("另外写了 goals.md（演示目标）")
    lines.append(f"看结果：pkbrain stats --data-dir {report.data_dir}")
    return "\n".join(lines)
