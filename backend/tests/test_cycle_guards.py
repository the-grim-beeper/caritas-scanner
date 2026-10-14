"""run_cycle's guards around the stages: repairs future-dated signals first, never runs
twice at once across processes, and always closes its cycle row. Stages are stubbed, so
these tests are about the frame, not about what the stages do."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from mhs import cycle as cycle_mod
from mhs.db.models import Cycle, Signal, Source, Story


@pytest.fixture
def stub_stages(monkeypatch):
    """Every stage a no-op that records it ran; collect is the one tests watch."""
    calls: list[str] = []

    def stage(name, result):
        async def run(*args, **kwargs):
            calls.append(name)
            return result
        return run

    monkeypatch.setattr(cycle_mod, "adopt_due", stage("adopt", {}))
    monkeypatch.setattr(cycle_mod, "collect_all", stage("collect", SimpleNamespace(fetched=0, new_items=0, failed_sources=0)))
    monkeypatch.setattr(cycle_mod, "extract_pending", stage("extract", SimpleNamespace(processed=0, signals=0, aborted=None)))
    monkeypatch.setattr(cycle_mod, "analyse_pending", stage("analyse", SimpleNamespace(stories_new=0, corroborations=0)))
    monkeypatch.setattr(cycle_mod, "judge_pending", stage("judge", SimpleNamespace(judged=0, judgements=0, aborted=None)))
    monkeypatch.setattr(cycle_mod, "resolve_candidates", stage("network", SimpleNamespace(edges_new=0)))
    monkeypatch.setattr(cycle_mod.trends, "rebuild", stage("trends", 0))
    return calls


async def _published(session, signal_id):
    return await session.scalar(select(Signal.published_at).where(Signal.id == signal_id))


async def test_next_cycle_repairs_a_signal_written_with_a_future_date(db_session, session_factory, stub_stages):
    # Wrong: the clamp only guards new signals; rows written before it stay "next month"
    # at the top of every newest-first list until someone edits the database by hand.
    src = Source(slug="s", name="s", layer="gemeinden", authority="high", scope="gemeinde", method="page",
                 url="https://s.test/", collect=True)
    db_session.add(src)
    await db_session.flush()
    created = datetime.now(timezone.utc) - timedelta(days=2)
    future = datetime.now(timezone.utc) + timedelta(days=29)
    sig = Signal(source_id=src.id, headline_de="Bürgerversammlung am 12. November", headline_en="h",
                 signal_type="event", published_at=future, created_at=created)
    past = Signal(source_id=src.id, headline_de="Kreistag tagte", headline_en="h", signal_type="decision",
                  published_at=created - timedelta(days=3), created_at=created)
    db_session.add_all([sig, past])
    await db_session.flush()
    story = Story(founding_signal_id=sig.id, first_seen=future, last_seen=future)
    db_session.add(story)
    await db_session.flush()
    sig.story_id = story.id
    await db_session.commit()

    c = await cycle_mod.run_cycle(session_factory)
    assert c.error is None and "collect" in stub_stages

    assert await _published(db_session, sig.id) == created
    assert await _published(db_session, past.id) == created - timedelta(days=3)  # untouched
    first, last = (await db_session.execute(select(Story.first_seen, Story.last_seen).where(Story.id == story.id))).one()
    assert first == created and last == created  # the story follows its repaired signal

    # Idempotent: a second run changes nothing further.
    await cycle_mod.run_cycle(session_factory)
    assert await _published(db_session, sig.id) == created
    assert len((await db_session.execute(select(Cycle))).scalars().all()) == 2
