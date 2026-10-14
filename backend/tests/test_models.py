"""Schema invariants the later stages rely on: provenance is enforced by the
database, not trusted from the caller."""
from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from mhs.db.models import Edge, Entity, Event, Judgement, Question, Signal, Source


async def _two_entities(db_session):
    a = Entity(slug="jugendamt-miesbach", kind="organisation", name="Jugendamt", seeded=True)
    b = Entity(slug="diakonie-rosenheim", kind="organisation", name="Diakonie Rosenheim", seeded=True)
    db_session.add_all([a, b])
    await db_session.flush()
    return a, b


async def _signal(db_session):
    src = Source(slug="s", name="s", layer="landkreis", authority="high", scope="landkreis", method="rss",
                 url="https://s.test/f", collect=True)
    db_session.add(src)
    await db_session.flush()
    sig = Signal(source_id=src.id, headline_en="h", headline_de="h", signal_type="decision")
    db_session.add(sig)
    await db_session.flush()
    return sig


async def test_signal_edge_without_signal_id_is_refused(db_session):
    # Wrong: provenance left to the caller, so a model-proposed edge can be stored unsourced.
    a, b = await _two_entities(db_session)
    db_session.add(Edge(a_entity_id=a.id, b_entity_id=b.id, relation="commissioning", origin="signal",
                        signal_id=None, quote="im Auftrag des Jugendamts"))
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_report_edge_needs_no_signal_and_signal_edge_with_signal_is_stored(db_session):
    a, b = await _two_entities(db_session)
    sig = await _signal(db_session)
    db_session.add_all([
        Edge(a_entity_id=a.id, b_entity_id=b.id, relation="commissioning", origin="report", brief_ref="56",
             evidence_de="Träger arbeitet im Auftrag des Jugendamts."),
        Edge(a_entity_id=a.id, b_entity_id=b.id, relation="commissioning", origin="signal", signal_id=sig.id,
             quote="im Auftrag des Jugendamts"),
    ])
    await db_session.flush()
    edges = (await db_session.execute(Edge.__table__.select())).all()
    assert len(edges) == 2 and {e.confidence for e in edges} == {"medium"}


async def test_seeded_calendar_window_needs_no_signal(db_session):
    db_session.add(Event(slug="haushalte-2027", origin="report", kind="window", name="Haushalte 2027",
                         name_en="2027 budgets", start_date=date(2026, 11, 1), end_date=date(2027, 3, 31)))
    await db_session.flush()
    ev = (await db_session.execute(Event.__table__.select())).one()
    assert ev.signal_id is None and ev.kind == "window" and ev.origin == "report"


async def test_one_judgement_per_signal_question_and_model(db_session):
    # Wrong: no unique key, so re-running the judge doubles every question's evidence.
    sig = await _signal(db_session)
    db_session.add(Question(id="q02", sort=2, title_de="t", title_en="t", driver_de="d", driver_en="d",
                            sources_de="s", for_label_de="f", for_label_en="f", for_de="f", for_en="f",
                            against_label_de="a", against_label_en="a", against_de="a", against_en="a"))
    await db_session.flush()

    def judgement(model):
        return Judgement(signal_id=sig.id, question_id="q02", direction="for", strength="moderate", weight=2,
                         quote="Kreisumlage", rationale_de="r", rationale_en="r", model=model)

    db_session.add_all([judgement("claude-sonnet-5-5"), judgement("mock")])
    await db_session.flush()
    db_session.add(judgement("mock"))
    with pytest.raises(IntegrityError):
        await db_session.flush()
