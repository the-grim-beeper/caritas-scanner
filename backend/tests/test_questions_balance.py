"""Balance per question: weekly net clipped and damped by volume, a decaying running balance,
and a movement word that says "ruhig" when there is no recent evidence."""
from datetime import date, timedelta

import pytest

from mhs.questions.balance import WeekPoint, balance_series, movement, weekly_net

TODAY = date(2026, 10, 14)  # a Wednesday; its ISO week starts Monday 2026-10-12


def test_weekly_net_is_capped():
    assert weekly_net([1]*10) == pytest.approx(3 * 10/12)
    assert weekly_net([3]) == pytest.approx(3 * 1/3)
    assert weekly_net([]) == 0.0


def test_ten_weak_concern_judgements_cannot_outweigh_the_cap():
    # Wrong: an unclipped sum lets one noisy week (ten weak items) swamp everything else.
    assert weekly_net([1] * 10) < 3
    assert weekly_net([-1] * 50) > -3
    assert weekly_net([3, -3]) == 0.0


def test_balance_decays_without_evidence():
    s = balance_series([(date(2026,8,24), "for", 3)], weeks=8, today=date(2026,10,14))
    peak = max(p.balance for p in s)
    assert peak > 0 and s[-1].balance < peak and s[-1].balance > 0
    assert movement(s) == "quiet"


def test_against_is_negative():
    s = balance_series([(date(2026,10,12), "against", 2)], weeks=4, today=date(2026,10,14))
    assert s[-1].balance < 0 and movement(s) == "against"


def test_series_is_iso_mondays_oldest_first_ending_in_this_week():
    s = balance_series([], weeks=12, today=TODAY)
    assert len(s) == 12
    assert s[-1].week == date(2026, 10, 12) and s[0].week == date(2026, 10, 12) - timedelta(weeks=11)
    assert all(p.week.weekday() == 0 for p in s)
    assert [p.week for p in s] == sorted(p.week for p in s)
    assert all(p.n == 0 and p.net == 0.0 and p.balance == 0.0 for p in s)
    assert movement(s) == "quiet"


def test_judgement_counts_in_the_iso_week_of_its_published_date():
    # Sunday 2026-10-11 belongs to the week of Monday 2026-10-05, not to "this week".
    s = balance_series([(date(2026, 10, 11), "for", 2)], weeks=3, today=TODAY)
    by_week = {p.week: p for p in s}
    assert by_week[date(2026, 10, 5)].n == 1 and by_week[date(2026, 10, 12)].n == 0


def test_running_balance_follows_the_formula():
    js = [(date(2026, 9, 28), "for", 3), (date(2026, 10, 12), "for", 1), (date(2026, 10, 13), "against", 2)]
    s = balance_series(js, weeks=3, today=TODAY)
    n0 = 3 * 1 / 3
    n2 = -1 * 2 / 4
    assert [p.net for p in s] == pytest.approx([n0, 0.0, n2])
    assert [p.balance for p in s] == pytest.approx([n0, 0.85 * n0, 0.85 * 0.85 * n0 + n2])
    assert [p.n for p in s] == [1, 0, 2]


def test_evidence_before_the_window_still_carries_into_it():
    # Wrong: starting the running balance at zero on the window's first week, so a strong
    # decision 13 weeks ago vanishes from a 12-week view instead of having decayed.
    s = balance_series([(TODAY - timedelta(weeks=13), "for", 3)], weeks=12, today=TODAY)
    assert s[0].n == 0 and s[0].balance > 0


def test_future_dated_evidence_counts_in_the_current_week():
    s = balance_series([(TODAY + timedelta(days=9), "against", 3)], weeks=2, today=TODAY)
    assert s[-1].n == 1 and s[-1].balance < 0


def test_mixed_when_both_directions_recent_and_balance_small():
    s = balance_series([(date(2026, 10, 5), "for", 2), (date(2026, 10, 12), "against", 2)], weeks=6, today=TODAY)
    assert abs(s[-1].balance) < 1
    assert movement(s) == "mixed"


def test_one_sided_recent_evidence_is_not_mixed():
    s = balance_series([(date(2026, 10, 5), "for", 1), (date(2026, 10, 12), "for", 1)], weeks=6, today=TODAY)
    assert movement(s) == "for"


def test_decisive_balance_beats_a_stray_counter_signal():
    js = [(date(2026, 9, 21), "for", 3), (date(2026, 9, 28), "for", 3), (date(2026, 10, 5), "for", 3),
          (date(2026, 10, 12), "against", 1)]
    s = balance_series(js, weeks=6, today=TODAY)
    assert s[-1].balance >= 1 and movement(s) == "for"


def test_recent_evidence_all_one_way_sets_the_movement_despite_an_old_balance():
    # Review fix 2 (the probe): strong "for" weeks -9..-5, then only "against" in weeks -1 and 0.
    # The balance is still positive from the old evidence, but everything the last four weeks
    # brought points against — the movement must not contradict its own window.
    js = [(TODAY - timedelta(weeks=k), "for", 3) for k in range(5, 10)]
    js += [(TODAY - timedelta(weeks=1), "against", 2), (TODAY, "against", 2)]
    s = balance_series(js, weeks=12, today=TODAY)
    assert s[-1].balance > 0
    assert movement(s) == "against"


def test_movement_looks_at_the_last_four_weeks_only():
    s = balance_series([(TODAY - timedelta(weeks=4), "for", 3)], weeks=8, today=TODAY)
    assert s[-1].balance > 0
    assert movement(s) == "quiet"
    s = balance_series([(TODAY - timedelta(weeks=3), "for", 3)], weeks=8, today=TODAY)
    assert movement(s) == "for"


def test_movement_of_empty_series_is_quiet():
    assert movement([]) == "quiet"
    assert movement([WeekPoint(week=date(2026, 10, 12), net=0.0, balance=0.4, n=0)]) == "quiet"
