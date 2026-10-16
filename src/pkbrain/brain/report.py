"""快照完整率：M1 的验收指标。

产品文档的验收标准是「连续 14 天对话，快照完整率 ≥ 90%」。不写个能算的东西出来，
这句话就只是个愿望。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as Date
from datetime import timedelta


@dataclass(frozen=True)
class Coverage:
    first: Date | None
    last: Date | None
    days_recorded: int
    days_span: int
    streak: int

    @property
    def rate(self) -> float:
        """有记录的天数 / 首条到最后一条之间的天数。没有记录时为 0。"""
        if not self.days_span:
            return 0.0
        return self.days_recorded / self.days_span

    def meets(self, target: float = 0.9) -> bool:
        return self.rate >= target


def coverage(dates: list[str], *, today: Date | None = None) -> Coverage:
    """dates 是升序的 YYYY-MM-DD 列表（`Store.dates()` 的产出）。"""
    days = sorted({Date.fromisoformat(d) for d in dates})
    if not days:
        return Coverage(first=None, last=None, days_recorded=0, days_span=0, streak=0)

    first, last = days[0], days[-1]
    span = (last - first).days + 1

    # 连续天数：从最后一条往前数，中间断一天就停。今天没记也算断。
    anchor = today or last
    if (anchor - last).days > 1:
        streak = 0
    else:
        streak = 1
        cursor = last
        known = set(days)
        while (cursor - timedelta(days=1)) in known:
            cursor -= timedelta(days=1)
            streak += 1

    return Coverage(
        first=first, last=last, days_recorded=len(days), days_span=span, streak=streak
    )


def describe(info: dict, share: Coverage, *, target: float = 0.9) -> str:
    """把 `Store.stats()` 与 `coverage()` 的产出写成几行给人（或 agent）看的话。

    CLI 的 `pkbrain stats` 与 MCP 的 `brain_stats` 都用它，免得两处口径走岔。
    """
    if not info.get("records"):
        return "还没有记录。先跑 pkbrain talk，或 pkbrain snapshot --from-file <文件>。"

    lines = [
        f"记录 {info['records']} 条，覆盖 {info['days']} 天（{info['first']} → {info['last']}）",
        (
            f"完整率 {share.rate:.1%}（{share.days_recorded}/{share.days_span} 天），"
            f"连续 {share.streak} 天，目标 {target:.0%} {'达标' if share.meets(target) else '未达标'}"
        ),
    ]
    channels = info.get("channels") or {}
    lines.append("通道 " + ("，".join(f"{k} {v}" for k, v in channels.items()) or "无"))
    metrics = info.get("metrics") or {}
    lines.append("指标 " + ("，".join(f"{k} {v}" for k, v in metrics.items()) or "无"))
    return "\n".join(lines)
