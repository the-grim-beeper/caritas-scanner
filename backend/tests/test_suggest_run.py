"""The weekly suggestion cycle: propose → drop known → verify → store pending or rejected.
Nothing is stored as pending without a live verdict; a declined URL never comes back."""
from datetime import timedelta

import pytest
import respx
from sqlalchemy import select

from mhs.config import settings
from mhs.db.models import Source, SourceSuggestion, utcnow
from mhs.suggest import net, run
from mhs.suggest.discover import Candidate

RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>T</title>
<item><title>Eins</title><link>https://neu.test/1</link></item></channel></rss>"""


def cand(url: str, name: str = "Gemeinde Weyarn – Aktuelles") -> Candidate:
    return Candidate(name=name, url=url, layer="gemeinden", scope="gemeinde", places=["Weyarn"],
                     rationale_de="Weyarn fehlt.", rationale_en="Weyarn is missing.")


@pytest.fixture(autouse=True)
def public_dns(monkeypatch):
    monkeypatch.setattr(net, "_resolve", lambda host: ["93.184.216.34"])


@pytest.fixture
def proposer(monkeypatch):
    def install(candidates):
        async def fake(session):
            return list(candidates)

        monkeypatch.setattr(run, "propose", fake)

    return install


async def _all(session) -> list[SourceSuggestion]:
    session.expire_all()
    return list((await session.execute(select(SourceSuggestion).order_by(SourceSuggestion.url))).scalars())


@respx.mock
async def test_known_and_declined_urls_are_never_stored_again(db_session, session_factory, proposer):
    now = utcnow()
    db_session.add(SourceSuggestion(url="https://a.test/x", name="A", layer="gemeinden", scope="gemeinde",
                                    rationale_de="r", rationale_en="r", model="mock", status="declined",
                                    suggested_at=now - timedelta(days=3), adopt_after=now + timedelta(days=4)))
    db_session.add(Source(slug="lk", name="LK", layer="landkreis", authority="high", scope="landkreis",
                          method="rss", url="https://lk.test/rss"))
    await db_session.commit()
    # Trailing slash, www. and scheme variants of known URLs are the same URL.
    proposer([cand("https://a.test/x/"), cand("http://www.lk.test/rss")])
    counts = await run.suggest_cycle(session_factory)
    assert counts == {"proposed": 2, "pending_new": 0, "rejected": 0, "known": 2}
    rows = await _all(db_session)
    assert [(r.url, r.status) for r in rows] == [("https://a.test/x", "declined")]
    assert not respx.calls  # known URLs are not even fetched


@respx.mock
async def test_verified_candidate_is_stored_pending_for_seven_days(db_session, session_factory, proposer):
    respx.get("https://neu.test/rss").respond(200, content=RSS, headers={"content-type": "application/rss+xml"})
    proposer([cand("https://neu.test/rss?utm_source=x")])
    before = utcnow()
    counts = await run.suggest_cycle(session_factory)
    assert counts == {"proposed": 1, "pending_new": 1, "rejected": 0, "known": 0}
    (row,) = await _all(db_session)
    assert row.status == "pending" and row.url == "https://neu.test/rss"  # stored canonical
    assert (row.method, row.feed_url, row.items_at_check) == ("rss", "https://neu.test/rss", 1)
    assert row.places == ["Weyarn"] and row.rationale_de == "Weyarn fehlt." and row.reason is None
    assert row.adopt_after - row.suggested_at == timedelta(days=settings.suggest_adopt_after_days)
    assert row.suggested_at >= before
    assert row.model == "mock"


@respx.mock
async def test_dead_candidate_is_rejected_with_reason(db_session, session_factory, proposer):
    respx.get("https://tot.test/aktuelles").respond(404)
    proposer([cand("https://tot.test/aktuelles")])
    counts = await run.suggest_cycle(session_factory)
    assert counts["rejected"] == 1 and counts["pending_new"] == 0
    (row,) = await _all(db_session)
    assert row.status == "rejected" and "404" in row.reason and row.resolved_at is not None


@respx.mock
async def test_duplicate_within_one_batch_is_counted_once(db_session, session_factory, proposer):
    respx.get("https://neu.test/rss").respond(200, content=RSS, headers={"content-type": "application/rss+xml"})
    proposer([cand("https://neu.test/rss"), cand("https://www.neu.test/rss/")])
    counts = await run.suggest_cycle(session_factory)
    assert counts == {"proposed": 2, "pending_new": 1, "rejected": 0, "known": 1}


@respx.mock
async def test_candidate_resolving_to_a_known_feed_is_rejected(db_session, session_factory, proposer):
    # A homepage whose autodiscovered feed the scanner already collects adds nothing.
    db_session.add(Source(slug="w", name="W", layer="gemeinden", authority="high", scope="gemeinde",
                          method="rss", url="https://neu.test/feed"))
    await db_session.commit()
    page = b'<html><head><link rel="alternate" type="application/rss+xml" href="/feed"></head></html>'
    respx.get("https://neu.test/start").respond(200, content=page, headers={"content-type": "text/html"})
    respx.get("https://neu.test/feed").respond(200, content=RSS, headers={"content-type": "application/rss+xml"})
    proposer([cand("https://neu.test/start")])
    counts = await run.suggest_cycle(session_factory)
    assert counts["rejected"] == 1 and counts["pending_new"] == 0
    (row,) = await _all(db_session)
    assert row.status == "rejected" and "https://neu.test/feed" in row.reason


async def test_mock_proposer_returns_nothing_and_cycle_is_a_noop(db_session, session_factory):
    assert settings.llm_enabled is False
    counts = await run.suggest_cycle(session_factory)
    assert counts == {"proposed": 0, "pending_new": 0, "rejected": 0, "known": 0}
    assert await _all(db_session) == []


async def test_a_second_run_while_one_is_running_is_refused(session_factory):
    async with run.running():
        assert run.is_running()
        with pytest.raises(run.SuggestRunInProgress):
            await run.suggest_cycle(session_factory)
    assert not run.is_running()
