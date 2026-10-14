"""Seven days, then adoption — unless declined. Every adoption re-verifies live first."""
from datetime import timedelta

import httpx
import pytest
import respx
from sqlalchemy import select

from mhs.db.models import Source, SourceSuggestion, utcnow
from mhs.suggest import net
from mhs.suggest.adopt import SuggestionNotPending, adopt_due, adopt_now, decline

PAGE = "".join(
    f'<li class="news-item"><a href="https://weyarn.test/aktuelles/m-{i}">Gemeinderat Weyarn berät Meldung Nummer {i}</a></li>'
    for i in range(3)
).join(["<html><body><ul>", "</ul></body></html>"]).encode()


@pytest.fixture(autouse=True)
def public_dns(monkeypatch):
    monkeypatch.setattr(net, "_resolve", lambda host: ["93.184.216.34"])


@pytest.fixture
async def http():
    async with httpx.AsyncClient() as c:
        yield c


def suggestion(*, status="pending", age_days=8, url="https://weyarn.test/aktuelles",
               name="Gemeinde Weyarn – Aktuelles") -> SourceSuggestion:
    now = utcnow()
    return SourceSuggestion(url=url, name=name, layer="gemeinden", scope="gemeinde", places=["Weyarn"],
                            rationale_de="Weyarn hat noch keine Quelle.", rationale_en="r", model="mock",
                            status=status, suggested_at=now - timedelta(days=age_days),
                            adopt_after=now - timedelta(days=age_days - 7))


async def _sources(session) -> list[Source]:
    session.expire_all()
    return list((await session.execute(select(Source))).scalars())


@respx.mock
async def test_pending_older_than_seven_days_is_adopted(db_session, http):
    s = suggestion()
    db_session.add(s)
    await db_session.commit()
    respx.get("https://weyarn.test/aktuelles").respond(200, content=PAGE, headers={"content-type": "text/html"})
    respx.route().respond(404)

    counts = await adopt_due(db_session, http)

    assert counts == {"adopted": 1, "failed": 0}
    (src,) = await _sources(db_session)
    await db_session.refresh(s)
    assert s.status == "adopted" and s.source_id == src.id and s.resolved_at is not None
    assert (src.origin, src.collect, src.status, src.layer) == ("suggestion", True, "active", "gemeinden")
    assert src.slug == "vorschlag-gemeinde-weyarn-aktuelles"
    assert (src.method, src.url, src.homepage) == ("page", "https://weyarn.test/aktuelles", "https://weyarn.test/aktuelles")
    assert src.places == ["Weyarn"] and src.notes == "Weyarn hat noch keine Quelle."
    assert (src.priority, src.brief_ref, src.authority, src.items_at_check) == ("thematic", "vorschlag", "medium", 3)


@respx.mock
async def test_pending_younger_than_seven_days_is_not_adopted(db_session, http):
    s = suggestion(age_days=6)
    db_session.add(s)
    await db_session.commit()
    route = respx.get("https://weyarn.test/aktuelles").respond(200, content=PAGE)

    assert await adopt_due(db_session, http) == {"adopted": 0, "failed": 0}
    assert not route.called
    await db_session.refresh(s)
    assert s.status == "pending" and await _sources(db_session) == []


@respx.mock
async def test_adopt_after_is_the_clock_not_suggested_at(db_session, http):
    # `now` is injectable: the same row is due a day later.
    s = suggestion(age_days=6)
    db_session.add(s)
    await db_session.commit()
    respx.get("https://weyarn.test/aktuelles").respond(200, content=PAGE, headers={"content-type": "text/html"})
    respx.route().respond(404)
    counts = await adopt_due(db_session, http, now=utcnow() + timedelta(days=1, minutes=1))
    assert counts["adopted"] == 1


@respx.mock
async def test_declined_is_never_adopted(db_session, http):
    s = suggestion(status="declined", age_days=30)
    db_session.add(s)
    await db_session.commit()
    route = respx.get("https://weyarn.test/aktuelles").respond(200, content=PAGE)
    assert await adopt_due(db_session, http) == {"adopted": 0, "failed": 0}
    assert not route.called
    await db_session.refresh(s)
    assert s.status == "declined" and await _sources(db_session) == []


@respx.mock
async def test_adoption_reverify_failure_marks_failed(db_session, http):
    s = suggestion()
    db_session.add(s)
    await db_session.commit()
    respx.get("https://weyarn.test/aktuelles").respond(500)

    assert await adopt_due(db_session, http) == {"adopted": 0, "failed": 1}
    await db_session.refresh(s)
    assert s.status == "failed" and "500" in s.reason and s.resolved_at is not None and s.source_id is None
    assert await _sources(db_session) == []


@respx.mock
async def test_adoption_does_not_duplicate_a_source_the_catalogue_added_meanwhile(db_session, http):
    db_session.add(Source(slug="weyarn-aktuelles", name="Weyarn", layer="gemeinden", authority="high",
                          scope="gemeinde", method="page", url="https://www.weyarn.test/aktuelles/"))
    s = suggestion()
    db_session.add(s)
    await db_session.commit()
    respx.get("https://weyarn.test/aktuelles").respond(200, content=PAGE, headers={"content-type": "text/html"})
    respx.route().respond(404)
    assert await adopt_due(db_session, http) == {"adopted": 0, "failed": 1}
    await db_session.refresh(s)
    assert s.status == "failed" and "weyarn-aktuelles" in s.reason
    assert [x.slug for x in await _sources(db_session)] == ["weyarn-aktuelles"]


@respx.mock
async def test_slug_is_made_unique(db_session, http):
    db_session.add(Source(slug="vorschlag-gemeinde-weyarn-aktuelles", name="X", layer="gemeinden",
                          authority="medium", scope="gemeinde", method="rss", url="https://other.test/rss"))
    s = suggestion()
    db_session.add(s)
    await db_session.commit()
    respx.get("https://weyarn.test/aktuelles").respond(200, content=PAGE, headers={"content-type": "text/html"})
    respx.route().respond(404)
    await adopt_due(db_session, http)
    slugs = sorted(x.slug for x in await _sources(db_session))
    assert slugs == ["vorschlag-gemeinde-weyarn-aktuelles", "vorschlag-gemeinde-weyarn-aktuelles-2"]


@respx.mock
async def test_long_names_give_slugs_within_120_characters(db_session, http):
    s = suggestion(name="Sehr langer Name " * 15)  # 255 characters, slugified ~250
    db_session.add(s)
    await db_session.commit()
    respx.get("https://weyarn.test/aktuelles").respond(200, content=PAGE, headers={"content-type": "text/html"})
    respx.route().respond(404)
    await adopt_due(db_session, http)
    (src,) = await _sources(db_session)
    assert src.slug.startswith("vorschlag-sehr-langer-name") and len(src.slug) <= 120


@respx.mock
async def test_adopt_now_ignores_the_clock_and_decline_is_final(db_session, http):
    young = suggestion(age_days=1)
    other = suggestion(age_days=1, url="https://zwei.test/x", name="Zwei")
    db_session.add_all([young, other])
    await db_session.commit()
    respx.get("https://weyarn.test/aktuelles").respond(200, content=PAGE, headers={"content-type": "text/html"})
    respx.route().respond(404)

    adopted = await adopt_now(db_session, http, young.id)
    assert adopted.status == "adopted" and adopted.source_id is not None
    with pytest.raises(SuggestionNotPending):
        await adopt_now(db_session, http, young.id)

    declined = await decline(db_session, other.id)
    assert declined.status == "declined" and declined.resolved_at is not None
    with pytest.raises(SuggestionNotPending):
        await decline(db_session, other.id)
    with pytest.raises(SuggestionNotPending):
        await adopt_now(db_session, http, other.id)
