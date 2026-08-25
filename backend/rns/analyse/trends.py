"""The trend database: founder-signal counts by topic × layer × ISO week. Pure SQL,
rebuilt every cycle. Corroborations are not counted — three outlets covering one
investment is one investment."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from rns.db.models import Signal, SignalTopic, Source, TrendCell


def _monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


async def rebuild(session: AsyncSession, *, weeks: int = 26, today: date | None = None) -> int:
    today = today or datetime.now(timezone.utc).date()
    since = datetime.combine(_monday(today) - timedelta(weeks=weeks), datetime.min.time(), tzinfo=timezone.utc)
    week = func.date_trunc("week", Signal.published_at).label("week")
    rows = (
        await session.execute(
            select(week, SignalTopic.topic_code, Source.layer, func.count(Signal.id))
            .join(SignalTopic, SignalTopic.signal_id == Signal.id)
            .join(Source, Source.id == Signal.source_id)
            .where(Signal.is_founder.is_(True), Signal.published_at >= since)
            .group_by(week, SignalTopic.topic_code, Source.layer)
        )
    ).all()
    await session.execute(delete(TrendCell))
    for wk, topic, layer, count in rows:
        session.add(TrendCell(week=wk.date() if isinstance(wk, datetime) else wk, topic=topic, layer=layer, count=int(count)))
    await session.commit()
    return len(rows)


@dataclass(frozen=True)
class Mover:
    topic: str
    layer: str
    current: int
    previous: int
    delta: int


async def movers(session: AsyncSession, *, window_weeks: int = 4, today: date | None = None) -> list[Mover]:
    today = today or datetime.now(timezone.utc).date()
    cur_from = today - timedelta(weeks=window_weeks)
    prev_from = today - timedelta(weeks=2 * window_weeks)
    cells = (await session.execute(select(TrendCell).where(TrendCell.week >= prev_from))).scalars().all()
    agg: dict[tuple[str, str], list[int]] = {}
    for c in cells:
        slot = agg.setdefault((c.topic, c.layer), [0, 0])
        if c.week >= cur_from:
            slot[0] += c.count
        else:
            slot[1] += c.count
    out = [Mover(topic=t, layer=l, current=cu, previous=pr, delta=cu - pr) for (t, l), (cu, pr) in agg.items()]
    out.sort(key=lambda m: (-abs(m.delta), -m.current, m.topic))
    return out
