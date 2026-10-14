"""Balance per question (spec §4.2). Per ISO week, net_w = Σ sign × weight, clipped to ±3
and scaled by n/(n+2), so a week's flood cannot outweigh a strong single signal by volume
alone. The running balance b_w = 0.85·b_{w−1} + net_w drifts back toward zero when no new
evidence arrives. "for" is the report's evidence for the concern or transition, "against"
its evidence against / stabilising."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

DECAY = 0.85
NET_CAP = 3
MOVEMENT_WEEKS = 4
MIXED_BELOW = 1.0
_SIGN = {"for": 1, "against": -1}


@dataclass
class WeekPoint:
    week: date  # ISO week Monday
    net: float
    balance: float
    n: int
    # How many of the week's n pointed each way; "mixed" needs the signs, not just the net.
    n_for: int = 0
    n_against: int = 0


def week_monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def weekly_net(weights_signs: list[int]) -> float:
    n = len(weights_signs)
    if n == 0:
        return 0.0
    clipped = max(-NET_CAP, min(NET_CAP, sum(weights_signs)))
    return clipped * n / (n + 2)


def balance_series(judgements: list[tuple[date, str, int]], *, weeks: int, today: date) -> list[WeekPoint]:
    """`judgements` are (published date of the signal, direction, weight). Returns `weeks`
    points, oldest first, ending with today's ISO week. Evidence older than the window still
    seeds the running balance (decayed); evidence dated after today's week counts in it."""
    current = week_monday(today)
    first = current - timedelta(weeks=weeks - 1)
    by_week: dict[date, list[int]] = defaultdict(list)
    for published, direction, weight in judgements:
        sign = _SIGN.get(direction)
        if sign is None:
            continue
        by_week[min(week_monday(published), current)].append(sign * int(weight))

    start = min([first, *by_week])
    out: list[WeekPoint] = []
    b = 0.0
    week = start
    while week <= current:
        vals = by_week.get(week, [])
        net = weekly_net(vals)
        b = DECAY * b + net
        if week >= first:
            out.append(WeekPoint(week=week, net=net, balance=b, n=len(vals),
                                 n_for=sum(1 for v in vals if v > 0), n_against=sum(1 for v in vals if v < 0)))
        week += timedelta(weeks=1)
    return out


def movement(series: list[WeekPoint]) -> str:
    """"for" | "against" | "mixed" | "quiet", read over the last four weeks: quiet without
    evidence; mixed when both directions arrived and the balance is still under 1; otherwise
    the sign of the latest balance."""
    recent = series[-MOVEMENT_WEEKS:]
    if not recent or sum(p.n for p in recent) == 0:
        return "quiet"
    b = recent[-1].balance
    both = sum(p.n_for for p in recent) > 0 and sum(p.n_against for p in recent) > 0
    if (both and abs(b) < MIXED_BELOW) or b == 0:
        return "mixed"
    return "for" if b > 0 else "against"
