from pathlib import Path

import pytest
import yaml
from sqlalchemy import select

from mhs.db.models import Entity
from mhs.entities import load_seed, resolve
from scripts.load_sources import upsert_entities

DATA = Path(__file__).resolve().parents[2] / "data"


async def test_resolver_alias_maps_case_insensitively(db_session):
    # Wrong: exact name match only.
    await upsert_entities(db_session, load_seed(DATA / "entities.yaml"))
    [e] = await resolve(db_session, ["sozialraumlotsen"], kind="programme")
    assert e.slug == "sozialraumlotsen"


async def test_unknown_place_is_not_created(db_session):
    # Wrong: create an entity for every string — the place set is closed.
    await upsert_entities(db_session, load_seed(DATA / "entities.yaml"))
    assert await resolve(db_session, ["Bad Tölz"], kind="place") == []
    ents = await resolve(db_session, ["Waakirchen", "Atlantis"], kind="place")
    assert [e.slug for e in ents] == ["waakirchen"]


async def test_unknown_forum_is_created_unseeded(db_session):
    [e] = await resolve(db_session, ["Runder Tisch Pflege Holzkirchen"], kind="forum")
    assert e.kind == "forum" and e.seeded is False
    [again] = await resolve(db_session, ["runder tisch pflege holzkirchen"], kind="forum")
    assert again.id == e.id


async def test_unknown_office_is_created_unseeded(db_session):
    [e] = await resolve(db_session, ["Seniorenbeauftragte Holzkirchen"], kind="office")
    assert e.kind == "office" and e.seeded is False


async def test_seed_carries_actor_kind(db_session):
    seeds = {s.slug: s for s in load_seed(DATA / "entities.yaml")}
    assert seeds["caritas-zentrum-miesbach"].actor_kind == "provider"
    assert seeds["landrat-miesbach"].kind == "office"
    await upsert_entities(db_session, list(seeds.values()))
    row = (await db_session.execute(select(Entity).where(Entity.slug == "sozialbeirat"))).scalar_one()
    assert row.kind == "forum" and row.actor_kind == "forum" and row.seeded


async def test_misfiled_kind_resolves_to_the_seeded_entity_instead_of_a_duplicate(db_session):
    # Wrong: per-kind lookup only — the extractor files "Pflegestützpunkt" under forums and
    # the resolver mints a second, unseeded "pflegestutzpunkt" beside the seeded organisation.
    await upsert_entities(db_session, load_seed(DATA / "entities.yaml"))
    [e] = await resolve(db_session, ["Pflegestützpunkt"], kind="forum")
    assert e.slug == "pflegestuetzpunkt-miesbach" and e.kind == "organisation"
    unseeded = (await db_session.execute(select(Entity).where(Entity.seeded.is_(False)))).scalars().all()
    assert unseeded == []


async def test_same_name_under_two_kinds_reuses_one_entity_instead_of_colliding(db_session):
    # Wrong: per-kind lookup, so a new name as organisation and then as programme tries to
    # insert the same slug twice and the whole cycle dies on a unique violation.
    first = await resolve(db_session, ["Familienstützpunkt Hausham"], kind="organisation")
    second = await resolve(db_session, ["Familienstützpunkt Hausham"], kind="programme")
    assert first[0].id == second[0].id and second[0].kind == "organisation"


def test_unknown_actor_kind_in_seed_is_rejected(tmp_path):
    bad = tmp_path / "entities.yaml"
    bad.write_text(yaml.safe_dump({"organisations": [{"slug": "x", "name": "X", "actor_kind": "company"}]}))
    with pytest.raises(ValueError):
        load_seed(bad)
