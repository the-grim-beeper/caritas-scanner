from pathlib import Path

from mhs.entities import load_seed, resolve

DATA = Path(__file__).resolve().parents[2] / "data"


async def _seed(db_session):
    from scripts.load_sources import upsert_entities
    await upsert_entities(db_session, load_seed(DATA / "entities.yaml"))


async def test_resolver_alias_phv_maps_to_patrick_henry_village_case_insensitively(db_session):
    # Wrong: exact name match only.
    await _seed(db_session)
    ents = await resolve(db_session, ["phv", "Patrick Henry Village"], kind="project")
    assert {e.slug for e in ents} == {"patrick-henry-village"}


async def test_resolver_unknown_place_is_not_created(db_session):
    # Wrong: create an entity for every string — the place set is closed.
    await _seed(db_session)
    ents = await resolve(db_session, ["Mannheim", "Atlantis"], kind="place")
    assert [e.slug for e in ents] == ["mannheim"]


async def test_resolver_unknown_organisation_is_created_unseeded(db_session):
    await _seed(db_session)
    ents = await resolve(db_session, ["Cytion GmbH"], kind="organisation")
    assert len(ents) == 1 and ents[0].seeded is False and ents[0].kind == "organisation"
    again = await resolve(db_session, ["cytion gmbh"], kind="organisation")
    assert again[0].id == ents[0].id


async def test_same_name_under_two_kinds_reuses_one_entity_instead_of_colliding(db_session):
    # Wrong: per-kind lookup, so "VRNnextbike" as organisation and then as project tries
    # to insert the same slug twice and the whole cycle dies on a unique violation.
    first = await resolve(db_session, ["VRNnextbike"], kind="organisation")
    second = await resolve(db_session, ["VRNnextbike"], kind="project")
    assert first[0].id == second[0].id and second[0].kind == "organisation"
