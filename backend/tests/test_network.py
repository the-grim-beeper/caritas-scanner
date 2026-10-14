"""The evidence graph (spec §4.3): seed loading, candidate resolution, the API.

Each test is written against a plausible wrong implementation:
- report edges: a loader that inserts instead of upserting would double on a second run.
- signal provenance: an edge writer that lets an `origin="signal"` row through without its
  signal is the one thing the database itself must refuse (ck_edge_signal_provenance).
- candidate resolution: calling `resolve(..., kind="organisation")` directly on every
  endpoint text would happily mint a brand-new organisation for a place name mentioned in
  a relation (a county or municipality is never an actor) instead of dropping it.
- the API: forgetting to filter a gap's `actor_slugs` down to entities that actually exist
  would leak dangling slugs into the frontend's node list.
"""
from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from mhs.config import settings
from mhs.db.engine import get_session
from mhs.db.models import (
    Edge, Entity, ForumProfile, NetworkGap, RelationCandidate, Signal, Source, utcnow,
)
from mhs.entities import load_seed
from mhs.network.load import load_network
from mhs.network.resolve import NetworkStats, resolve_candidates
from scripts.load_sources import upsert_entities

DATA = Path(__file__).resolve().parents[2] / "data"


# ---------------------------------------------------------------------------
# network/load.py
# ---------------------------------------------------------------------------
async def test_report_edges_load_with_report_origin(db_session):
    # Wrong: inserting unconditionally would double the row count on a second run.
    await upsert_entities(db_session, load_seed(DATA / "entities.yaml"))
    stats = await load_network(db_session, DATA / "network.yaml")
    edges = (await db_session.execute(select(Edge))).scalars().all()
    assert stats["edges"] == len(edges) == 18
    assert all(e.origin == "report" and e.signal_id is None for e in edges)
    assert (await load_network(db_session, DATA / "network.yaml"))["edges"] == 18  # idempotent: still 18 rows
    edges_again = (await db_session.execute(select(Edge))).scalars().all()
    assert len(edges_again) == 18


async def test_forums_and_gaps_load_with_sort_and_upsert(db_session):
    # Wrong: appending gaps on every load instead of replacing wholesale would double them.
    await upsert_entities(db_session, load_seed(DATA / "entities.yaml"))
    stats = await load_network(db_session, DATA / "network.yaml")
    assert stats["forums"] == 8 and stats["gaps"] == 12
    forums = (await db_session.execute(select(ForumProfile))).scalars().all()
    assert len(forums) == 8
    gaps = (await db_session.execute(select(NetworkGap).order_by(NetworkGap.sort))).scalars().all()
    assert len(gaps) == 12
    assert [g.sort for g in gaps] == list(range(12))
    assert gaps[0].kind == "missing_edge"
    assert gaps[0].actor_slugs == ["caritas-zentrum-miesbach", "sozialraumlotsen", "landratsamt-miesbach"]

    await load_network(db_session, DATA / "network.yaml")  # idempotent
    forums_again = (await db_session.execute(select(ForumProfile))).scalars().all()
    gaps_again = (await db_session.execute(select(NetworkGap))).scalars().all()
    assert len(forums_again) == 8 and len(gaps_again) == 12


async def test_load_network_rejects_an_endpoint_slug_missing_from_entities(db_session, tmp_path):
    await upsert_entities(db_session, load_seed(DATA / "entities.yaml"))
    bad = tmp_path / "network.yaml"
    bad.write_text(
        "edges:\n"
        "  - {a: landratsamt-miesbach, b: nonexistent-slug, relation: coordination}\n"
    )
    with pytest.raises(ValueError, match="nonexistent-slug"):
        await load_network(db_session, bad)


# ---------------------------------------------------------------------------
# Edge provenance (schema-level, ck_edge_signal_provenance)
# ---------------------------------------------------------------------------
async def test_signal_edge_without_signal_id_is_refused(db_session):
    a, b = Entity(slug="x", kind="organisation", name="X"), Entity(slug="y", kind="organisation", name="Y")
    db_session.add_all([a, b])
    await db_session.flush()
    db_session.add(Edge(a_entity_id=a.id, b_entity_id=b.id, relation="funding", origin="signal", signal_id=None))
    with pytest.raises(IntegrityError):
        await db_session.flush()


# ---------------------------------------------------------------------------
# network/resolve.py
# ---------------------------------------------------------------------------
async def _signal(session, **overrides) -> Signal:
    src = Source(slug="jhp-presse", name="Jugendhilfeplanung", layer="policy", authority="high",
                 scope="landkreis", method="page", url="https://jhp.test/")
    session.add(src)
    await session.flush()
    fields = dict(
        source_id=src.id, headline_en="X", headline_de="X", signal_type="decision",
        authority=1.0, regional_relevance=1.0, novelty=1.0, consequence=1.0, forward_lag=1.0,
        score=0.5, published_at=utcnow(), is_founder=True,
    )
    fields.update(overrides)
    sig = Signal(**fields)
    session.add(sig)
    await session.flush()
    return sig


async def test_candidate_resolves_to_edge_with_provenance(db_session):
    # Wrong: dropping provenance (not carrying signal_id/quote onto the Edge) would pass the
    # IntegrityError check above yet still leave the graph unable to show its evidence.
    await upsert_entities(db_session, load_seed(DATA / "entities.yaml"))
    sig = await _signal(db_session)
    db_session.add(RelationCandidate(
        signal_id=sig.id, a_text="Jugendamt", b_text="Diakonie Kinder- und Jugendhilfe Miesbach",
        relation="commissioning", quote="im Auftrag des Jugendamts",
    ))
    await db_session.flush()

    stats = await resolve_candidates(db_session)
    assert stats == NetworkStats(candidates=1, edges_new=1, dropped=0)

    edges = (await db_session.execute(select(Edge).where(Edge.origin == "signal"))).scalars().all()
    assert len(edges) == 1
    [edge] = edges
    assert edge.signal_id == sig.id
    assert edge.quote == "im Auftrag des Jugendamts"
    assert edge.relation == "commissioning"
    assert edge.confidence == "medium"

    a = await db_session.get(Entity, edge.a_entity_id)
    b = await db_session.get(Entity, edge.b_entity_id)
    assert a.slug == "jugendamt-miesbach"
    assert b.slug == "diakonie-jugendhilfe-miesbach"

    cand = (await db_session.execute(select(RelationCandidate))).scalar_one()
    assert cand.processed is True


async def test_unresolvable_place_endpoint_drops(db_session):
    # Wrong: calling resolve(..., kind="organisation") on every endpoint text would mint a
    # brand-new organisation called "Bad Tölz" instead of recognising it names a place —
    # a place can fund nothing and commission nothing, so the edge must drop, not be created.
    await upsert_entities(db_session, load_seed(DATA / "entities.yaml"))
    # A seeded place the extractor nonetheless named as a relation endpoint.
    place = Entity(slug="bad-toelz", kind="place", name="Bad Tölz", seeded=True)
    db_session.add(place)
    await db_session.flush()
    sig = await _signal(db_session)
    db_session.add(RelationCandidate(
        signal_id=sig.id, a_text="Bad Tölz", b_text="Caritas-Zentrum Miesbach",
        relation="cooperation", quote="Bad Tölz arbeitet mit dem Caritas-Zentrum zusammen",
    ))
    await db_session.flush()

    stats = await resolve_candidates(db_session)
    assert stats == NetworkStats(candidates=1, edges_new=0, dropped=1)
    assert (await db_session.execute(select(Edge).where(Edge.origin == "signal"))).scalars().all() == []

    # No shadow organisation was created for the place text.
    orgs = (await db_session.execute(select(Entity).where(Entity.kind == "organisation", Entity.name == "Bad Tölz"))).scalars().all()
    assert orgs == []
    cand = (await db_session.execute(select(RelationCandidate))).scalar_one()
    assert cand.processed is True


async def test_unresolved_endpoint_creates_the_open_kind_but_still_drops_on_a_equals_b(db_session):
    sig = await _signal(db_session)
    db_session.add(RelationCandidate(
        signal_id=sig.id, a_text="Runder Tisch Pflege", b_text="runder tisch pflege",
        relation="membership", quote="Mitgliedschaft im Runden Tisch",
    ))
    await db_session.flush()

    stats = await resolve_candidates(db_session)
    assert stats == NetworkStats(candidates=1, edges_new=0, dropped=1)
    created = (await db_session.execute(select(Entity).where(Entity.kind == "organisation"))).scalars().all()
    assert len(created) == 1  # the unknown name was still created, just not linked to itself


async def test_duplicate_candidate_for_the_same_signal_and_relation_does_not_double_the_edge(db_session):
    await upsert_entities(db_session, load_seed(DATA / "entities.yaml"))
    sig = await _signal(db_session)
    db_session.add_all([
        RelationCandidate(signal_id=sig.id, a_text="Jugendamt",
                          b_text="Diakonie Kinder- und Jugendhilfe Miesbach",
                          relation="commissioning", quote="im Auftrag des Jugendamts"),
        RelationCandidate(signal_id=sig.id, a_text="Kreisjugendamt Miesbach", b_text="Kinder- und Jugendhilfe Miesbach",
                          relation="commissioning", quote="im Auftrag des Jugendamts (zweite Fundstelle)"),
    ])
    await db_session.flush()

    stats = await resolve_candidates(db_session)
    assert stats.candidates == 2 and stats.edges_new == 1 and stats.dropped == 1
    edges = (await db_session.execute(select(Edge).where(Edge.origin == "signal"))).scalars().all()
    assert len(edges) == 1


async def test_resolve_candidates_is_a_noop_with_nothing_pending(db_session):
    assert await resolve_candidates(db_session) == NetworkStats()


# ---------------------------------------------------------------------------
# API: GET /api/network
# ---------------------------------------------------------------------------
@pytest.fixture
async def net_client(db_session):
    from fastapi import FastAPI

    from mhs.api import auth
    from mhs.api import network as network_api

    app = FastAPI()
    app.include_router(auth.router, prefix="/api")
    app.include_router(network_api.router, prefix="/api")

    async def _override():
        yield db_session

    app.dependency_overrides[get_session] = _override
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c
    app.dependency_overrides.clear()


async def _login(client):
    r = await client.post("/api/login", json={"password": settings.app_password})
    assert r.status_code == 200


async def test_network_api_needs_a_session(net_client):
    assert (await net_client.get("/api/network")).status_code == 401


async def test_network_api_shape_from_the_seed(db_session, net_client):
    # Wrong: nodes built only from entities table instead of edge/forum/gap membership would
    # bloat the graph with every unrelated seeded entity.
    await upsert_entities(db_session, load_seed(DATA / "entities.yaml"))
    await load_network(db_session, DATA / "network.yaml")

    await _login(net_client)
    r = await net_client.get("/api/network")
    assert r.status_code == 200
    body = r.json()
    assert len(body["edges"]) == 18
    assert len(body["forums"]) == 8
    assert len(body["gaps"]) == 12
    assert all(e.get("origin") == "report" for e in body["edges"])

    by_slug = {n["slug"]: n for n in body["nodes"]}
    assert "landratsamt-miesbach" in by_slug
    node = by_slug["landratsamt-miesbach"]
    assert set(node) >= {"id", "slug", "name", "kind", "actor_kind", "seeded", "degree", "signals_30d"}
    assert node["degree"] == 4  # bergbus, jugendhilfeausschuss, gesundheitsregionplus, fachstelle

    # Entities named only in a gap (not an edge endpoint, not a forum) are still nodes.
    assert "sozialraumlotsen" in by_slug
    assert "caritas-zentrum-miesbach" in by_slug

    forum = next(f for f in body["forums"] if f["slug"] == "sozialbeirat")
    assert forum["convener_de"] == "Landkreis / Fachstelle für Soziales und Senioren"
    assert forum["attendance_visible"] is False

    gap = next(g for g in body["gaps"] if g["kind"] == "missing_edge")
    assert gap["actor_slugs"] == ["caritas-zentrum-miesbach", "sozialraumlotsen", "landratsamt-miesbach"]


async def test_network_api_drops_a_gap_actor_slug_that_is_not_an_entity(db_session, net_client):
    ent = Entity(slug="real-one", kind="organisation", name="Real One", actor_kind="other", seeded=True)
    db_session.add(ent)
    await db_session.flush()
    db_session.add(NetworkGap(
        sort=0, kind="interview", title_de="t", title_en="t", detail_de="d", detail_en="d",
        actor_slugs=["real-one", "ghost-slug-does-not-exist"],
    ))
    await db_session.commit()

    await _login(net_client)
    body = (await net_client.get("/api/network")).json()
    [gap] = body["gaps"]
    assert gap["actor_slugs"] == ["real-one"]
    assert {n["slug"] for n in body["nodes"]} == {"real-one"}


async def test_network_api_signal_edge_carries_its_signal_and_signals_30d_counts_distinct_signals(db_session, net_client):
    from mhs.db.models import SignalEntity

    a = Entity(slug="a-org", kind="organisation", name="A", actor_kind="other", seeded=True)
    b = Entity(slug="b-org", kind="organisation", name="B", actor_kind="other", seeded=True)
    db_session.add_all([a, b])
    await db_session.flush()
    sig = await _signal(db_session, headline_de="Beschluss", headline_en="Decision")
    db_session.add(Edge(a_entity_id=a.id, b_entity_id=b.id, relation="funding", origin="signal",
                        signal_id=sig.id, quote="Q", confidence="medium"))
    db_session.add(SignalEntity(signal_id=sig.id, entity_id=a.id))
    await db_session.commit()

    await _login(net_client)
    body = (await net_client.get("/api/network")).json()
    [edge] = body["edges"]
    assert edge["origin"] == "signal" and edge["a"] == "a-org" and edge["b"] == "b-org"
    assert edge["signal"]["headline_de"] == "Beschluss"
    by_slug = {n["slug"]: n for n in body["nodes"]}
    assert by_slug["a-org"]["signals_30d"] == 1
    assert by_slug["b-org"]["signals_30d"] == 0
