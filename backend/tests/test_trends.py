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
    src = Source(slug="s", name="s", layer="landkreis", authority="high", scope="landkreis", method="rss",
                 url="https://s.test/f", collect=True)
    db_session.add(src)
    await db_session.flush()
    monday = datetime(2026, 8, 17, 12, tzinfo=timezone.utc)  # ISO week starting 2026-08-17
    await _sig(db_session, src, monday, ["umlagen", "haushalt"])
    await _sig(db_session, src, monday + timedelta(days=3), ["umlagen"])
    dup = Signal(source_id=src.id, headline_en="h", headline_de="h", signal_type="announcement",
                 published_at=monday, is_founder=False)
    db_session.add(dup)
    await db_session.flush()
    db_session.add(SignalTopic(signal_id=dup.id, topic_code="umlagen"))
    await db_session.commit()

    await trends.rebuild(db_session, weeks=52, today=date(2026, 8, 25))
    cells = {(c.week, c.topic, c.layer): c.count for c in (await db_session.execute(select(TrendCell))).scalars()}
    assert cells[(date(2026, 8, 17), "umlagen", "landkreis")] == 2
    assert cells[(date(2026, 8, 17), "haushalt", "landkreis")] == 1


async def test_movers_compare_last_window_to_previous(db_session):
    src = Source(slug="s", name="s", layer="freistaat", authority="high", scope="land", method="rss",
                 url="https://s.test/f", collect=True)
    db_session.add(src)
    await db_session.flush()
    today = date(2026, 8, 25)
    for d in (2, 5, 9, 12):  # last 4 weeks: 4 funding signals
        await _sig(db_session, src, datetime(2026, 8, 25 - d, tzinfo=timezone.utc), ["foerderung"])
    await _sig(db_session, src, datetime(2026, 7, 10, tzinfo=timezone.utc), ["foerderung"])  # previous window: 1
    await db_session.commit()
    await trends.rebuild(db_session, weeks=26, today=today)
    movers = await trends.movers(db_session, window_weeks=4, today=today)
    top = movers[0]
    assert top.topic == "foerderung" and top.current == 4 and top.previous == 1 and top.delta == 3
