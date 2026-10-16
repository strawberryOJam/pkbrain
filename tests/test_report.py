from datetime import date

from pkbrain.brain.report import coverage, Coverage


def test_empty_history():
    share = coverage([])
    assert share == Coverage(first=None, last=None, days_recorded=0, days_span=0, streak=0)
    assert share.rate == 0.0
    assert share.meets() is False


def test_a_single_day_is_full_coverage():
    share = coverage(["2026-10-16"], today=date(2026, 10, 16))
    assert share.days_recorded == 1
    assert share.days_span == 1
    assert share.rate == 1.0
    assert share.streak == 1


def test_a_missing_day_shows_up_in_the_rate():
    days = [f"2026-10-{d:02d}" for d in range(1, 11)]  # 十天
    days.remove("2026-10-05")  # 断了第 5 天
    share = coverage(days, today=date(2026, 10, 10))
    assert share.days_recorded == 9
    assert share.days_span == 10
    assert share.rate == 0.9
    assert share.meets(0.9) is True


def test_duplicate_days_are_counted_once():
    share = coverage(["2026-10-16", "2026-10-16", "2026-10-17"])
    assert share.days_recorded == 2


def test_streak_counts_back_from_the_last_record():
    share = coverage(
        ["2026-10-10", "2026-10-11", "2026-10-12"], today=date(2026, 10, 12)
    )
    assert share.streak == 3


def test_streak_is_broken_by_a_gap():
    share = coverage(["2026-10-01", "2026-10-11", "2026-10-12"], today=date(2026, 10, 12))
    assert share.streak == 2


def test_streak_is_zero_when_the_last_record_is_stale():
    share = coverage(["2026-10-01", "2026-10-02"], today=date(2026, 10, 16))
    assert share.streak == 0


def test_streak_survives_today_not_being_recorded_yet():
    """今晚还没记，昨天的连续不该被打断。"""
    share = coverage(["2026-10-14", "2026-10-15"], today=date(2026, 10, 16))
    assert share.streak == 2
