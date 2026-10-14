from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from mhs.analyse import trends
from mhs.db.models import Signal, SignalTopic, Source, TrendCell


async def _sig(db_session, src, when, topics):
    s = Signal(source_id=src.id, headline_en="h", headline_de="h", signal_type="announcement",
               published_at=when, is_founder=True)
    db_session.add(s)
    await db_session.flush()
    for t in topics:
        db_session.add(SignalTopic(signal_id=s.id, topic_code=t))


async def test_trend_cells_group_by_iso_week_topic_and_layer_and_count_founders_only(db_session):
    # Wrong: counting corroborations too (three outlets → three trend hits for one story).
    src = Source(slug="s", name="s", layer="corporate", authority="high", scope="region", method="rss",
                 url="https://s.test/f", collect=True)
    db_session.add(src)
    await db_session.flush()
    monday = datetime(2026, 8, 17, 12, tzinfo=timezone.utc)  # ISO week starting 2026-08-17
    await _sig(db_session, src, monday, ["CAPEX", "chemicals"])
    await _sig(db_session, src, monday + timedelta(days=3), ["CAPEX"])
    dup = Signal(source_id=src.id, headline_en="h", headline_de="h", signal_type="announcement",
                 published_at=monday, is_founder=False)
    db_session.add(dup)
    await db_session.flush()
    db_session.add(SignalTopic(signal_id=dup.id, topic_code="CAPEX"))
    await db_session.commit()

    await trends.rebuild(db_session, weeks=52, today=date(2026, 8, 25))
    cells = {(c.week, c.topic, c.layer): c.count for c in (await db_session.execute(select(TrendCell))).scalars()}
    assert cells[(date(2026, 8, 17), "CAPEX", "corporate")] == 2
    assert cells[(date(2026, 8, 17), "chemicals", "corporate")] == 1


async def test_movers_compare_last_window_to_previous(db_session):
    src = Source(slug="s", name="s", layer="funding", authority="high", scope="region", method="rss",
                 url="https://s.test/f", collect=True)
    db_session.add(src)
    await db_session.flush()
    today = date(2026, 8, 25)
    for d in (2, 5, 9, 12):  # last 4 weeks: 4 grant signals
        await _sig(db_session, src, datetime(2026, 8, 25 - d, tzinfo=timezone.utc), ["grant"])
    await _sig(db_session, src, datetime(2026, 7, 10, tzinfo=timezone.utc), ["grant"])  # previous window: 1
    await db_session.commit()
    await trends.rebuild(db_session, weeks=26, today=today)
    movers = await trends.movers(db_session, window_weeks=4, today=today)
    top = movers[0]
    assert top.topic == "grant" and top.current == 4 and top.previous == 1 and top.delta == 3
