"""write_report — the weekly Lagebericht (spec §4.4): one Opus-class call (or the mock)
over the week's founding signals, the questions' movement and this week's judgements,
the next 30 days of the calendar, new edges, trend movers and source health. Validated
for provenance (one retry with the problems), then stored as a Digest row with the week
and the Freitagsnotiz."""
from __future__ import annotations

import importlib
import json
import logging
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, selectinload

from mhs import vocab
from mhs.analyse import trends
from mhs.calendar import overlaps
from mhs.config import settings
from mhs.db.models import Cycle, Digest, Edge, Entity, Event, Judgement, Question, Signal, Source
from mhs.report.mock import mock_report
from mhs.report.schema import REPORT_SCHEMA
from mhs.report.validate import ReportProvenanceError, input_numbers, validate_report

log = logging.getLogger(__name__)

MAX_SIGNALS = 80
MAX_JUDGEMENTS_PER_QUESTION = 6
MAX_EVENTS = 30
MAX_EDGES = 40
MAX_MOVERS = 10
HORIZON_DAYS = 30
BALANCE_WEEKS = 12
# Figures the system prompt itself gives the model (the project's horizon, the calendar
# window); anything else in the Friday note must come from the input.
PROMPT_FIGURES = {"2035", "2040", str(HORIZON_DAYS)}

SYSTEM = f"""You write the weekly Lagebericht of a horizon scanner for social provision in
Landkreis Miesbach (Upper Bavaria). It is read by Caritas-Zentrum Miesbach (its contact for the project)
and by a TUM foresight student team. The question the whole project serves: can an
inter-municipal coordination structure for social provision, the "Interkommunale
Sozialraumlotsen", be designed and anchored so that it still works in 2035 and 2040?
"Change" here means change in mandates, money, staffing, rules and legitimacy around
social provision, not general local news.

German is the primary language. Write each German field first, as German written for
German readers (not a translation), then its English counterpart saying the same thing.

The input (JSON) holds: the report day and its ISO week; this week's founding signals (one
per story, ranked by the scanner's score); the fifteen monitoring questions, each with its
computed movement and this week's judgements (a verbatim quote from a signal, read as
evidence for or against the question); the events, deadlines and watch windows of the next
30 days; new relations between actors; the topics whose volume moved most; and the health
of the source collection.

Write:
- lead_de, lead_en: three or four sentences on what moved this week for the question above.
  Concrete, no throat-clearing.
- questions: only questions with judgements this week. Copy the movement given in the
  input. One or two sentences on what this week's evidence shows; cite the judgement ids
  it rests on.
- sections: per layer ({", ".join(vocab.LAYERS)}), the signals worth the
  reader's minute, each with one or two sentences on why it matters, not a restatement of
  the headline. Omit layers with nothing worth saying.
- chains: links you can see across layers between signals in this batch (a Bezirksumlage
  rise, then a county budget, then a municipal grant cut; a state programme ending, then a
  provider's post left empty, then a service cutting its hours). Two or more signal ids
  each. An empty list is a fine answer.
- watch: the events, deadlines and windows from the input that deserve attention in the
  coming weeks, each with why.
- friday_de, friday_en: the team's weekly written update to the Caritas contact (rules below).
- friday_signal_ids: every signal the Friday note draws on.

The Friday note is the part a person will send. Write it as a careful member of a
foresight team reporting to a client:
- Two or three short paragraphs separated by a blank line. Plain prose only: no headings,
  no bullet or numbered lists, no bold, no greeting, no sign-off, no signature.
- Sober and concrete. Short sentences; cut every word that carries no weight. No marketing
  tone, no superlatives, no filler ("spannende Entwicklungen", "es bleibt abzuwarten").
- First, what the scanner saw this week: the two or three developments that matter most.
  Then what they may mean for the Sozialraumlotsen question; this is a reading, so write
  "may" or "could", not "will". Then, only if the evidence raises one that the Caritas contact is
  placed to answer, one open question, phrased without addressing them ("Offen ist, ob …",
  "Ist bekannt, ob …?"). Never more than one question.
- Every factual sentence must rest on a signal listed in friday_signal_ids. If the week
  was thin, say so plainly instead of stretching the evidence.

Provenance (checked by code; a violation rejects the report):
- Cite only ids that appear in the input.
- Never invent numbers, names or dates. Every figure and date you write must come from the
  input (2026-10-31 may be written as 31. Oktober). Name only organisations, bodies,
  places, programmes and offices that appear in the input, and never a private individual."""


def _iso_monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _truncate(text: str | None, n: int = 400) -> str:
    text = (text or "").strip()
    return text if len(text) <= n else text[:n] + "…"


def _iso(d: date | datetime | None) -> str | None:
    return d.isoformat() if d else None


def _shown() -> list:
    """With a key set, mock judgements are left out — the rule the questions API applies."""
    from mhs.questions.judge import MOCK_MODEL

    return [Judgement.model != MOCK_MODEL] if settings.llm_enabled else []


async def _question_movements(session: AsyncSession, today: date) -> dict[str, str]:
    """Movement per question from mhs.questions.balance (imported here, not at module load,
    so this module does not depend on it at import time; tests replace this function).
    A signal read again by a newer judge model counts once: its newest judgement."""
    balance = importlib.import_module("mhs.questions.balance")
    qids = (await session.execute(select(Question.id).order_by(Question.sort))).scalars().all()
    rows = (
        await session.execute(
            select(Judgement.question_id, Judgement.direction, Judgement.weight, Signal.published_at)
            .join(Signal, Signal.id == Judgement.signal_id)
            .where(*_shown())
            .distinct(Judgement.question_id, Judgement.signal_id)
            .order_by(Judgement.question_id, Judgement.signal_id, desc(Judgement.created_at))
        )
    ).all()
    per_q: dict[str, list[tuple[date, str, int]]] = {qid: [] for qid in qids}
    for qid, direction, weight, published in rows:
        per_q.setdefault(qid, []).append((published.date(), direction, weight))
    return {
        qid: balance.movement(balance.balance_series(js, weeks=BALANCE_WEEKS, today=today))
        for qid, js in per_q.items()
    }


async def _signals(session: AsyncSession, since: datetime, until: datetime) -> list[dict]:
    rows = (
        await session.execute(
            select(Signal, Source)
            .join(Source, Source.id == Signal.source_id)
            .options(selectinload(Signal.topics))
            .where(Signal.is_founder.is_(True), Signal.created_at > since, Signal.created_at <= until)
            .order_by(desc(Signal.score), desc(Signal.published_at))
            .limit(MAX_SIGNALS)
        )
    ).all()
    return [
        {
            "id": str(s.id),
            "layer": src.layer,
            "source": src.name,
            "type": s.signal_type,
            "score": round(s.score, 4),
            "topics": [t.topic_code for t in s.topics],
            "published": _iso(s.published_at.date()) if s.published_at else None,
            "headline_de": s.headline_de,
            "headline_en": s.headline_en,
            "summary_de": _truncate(s.summary_de),
            "summary_en": _truncate(s.summary_en),
        }
        for s, src in rows
    ]


async def _questions(session: AsyncSession, since: datetime, until: datetime, movements: dict[str, str]) -> list[dict]:
    questions = (await session.execute(select(Question).order_by(Question.sort))).scalars().all()
    rows = (
        await session.execute(
            select(Judgement, Signal.headline_de)
            .join(Signal, Signal.id == Judgement.signal_id)
            .where(Judgement.created_at > since, Judgement.created_at <= until, *_shown())
            .order_by(Judgement.question_id, desc(Judgement.weight), desc(Judgement.created_at))
        )
    ).all()
    per_q: dict[str, list[dict]] = {}
    for j, headline in rows:
        bucket = per_q.setdefault(j.question_id, [])
        if len(bucket) >= MAX_JUDGEMENTS_PER_QUESTION or any(b["signal_id"] == str(j.signal_id) for b in bucket):
            continue
        bucket.append({"id": str(j.id), "signal_id": str(j.signal_id), "direction": j.direction,
                       "strength": j.strength, "quote": j.quote, "headline_de": headline})
    return [
        {"id": q.id, "title_de": q.title_de, "title_en": q.title_en,
         "for_label_de": q.for_label_de, "for_label_en": q.for_label_en,
         "against_label_de": q.against_label_de, "against_label_en": q.against_label_en,
         "movement": movements.get(q.id, "quiet"), "judgements": per_q.get(q.id, [])}
        for q in questions
    ]


async def _events(session: AsyncSession, today: date) -> list[dict]:
    rows = (
        await session.execute(
            select(Event)
            .where(overlaps(today, today + timedelta(days=HORIZON_DAYS)))
            .order_by(func.coalesce(Event.deadline, Event.start_date), Event.name)
            .limit(MAX_EVENTS)
        )
    ).scalars().all()
    return [
        {"id": str(e.id), "kind": e.kind, "origin": e.origin, "name_de": e.name, "name_en": e.name_en,
         "start_date": _iso(e.start_date), "end_date": _iso(e.end_date), "deadline": _iso(e.deadline),
         "place": e.place, "programme": e.programme, "organizer": e.organizer,
         "note_de": e.note_de, "note_en": e.note_en, "signal_id": str(e.signal_id) if e.signal_id else None}
        for e in rows
    ]


async def _edges(session: AsyncSession, since: datetime, until: datetime) -> list[dict]:
    a, b = aliased(Entity), aliased(Entity)
    rows = (
        await session.execute(
            select(Edge, a.name, b.name)
            .join(a, a.id == Edge.a_entity_id)
            .join(b, b.id == Edge.b_entity_id)
            .where(Edge.created_at > since, Edge.created_at <= until)
            .order_by(desc(Edge.created_at))
            .limit(MAX_EDGES)
        )
    ).all()
    return [
        {"a": a_name, "relation": e.relation, "b": b_name, "origin": e.origin,
         "signal_id": str(e.signal_id) if e.signal_id else None, "quote": e.quote, "evidence_de": e.evidence_de}
        for e, a_name, b_name in rows
    ]


async def _source_health(session: AsyncSession) -> dict:
    collected = Source.collect.is_(True)
    last_start = (await session.execute(select(func.max(Cycle.started_at)))).scalar_one()
    ok = 0
    if last_start is not None:
        ok = (await session.execute(
            select(func.count(Source.id)).where(collected, Source.last_ok_at >= last_start))).scalar_one()
    failing = (await session.execute(
        select(func.count(Source.id)).where(
            collected, (Source.consecutive_failures > 0) | (Source.status == "quarantined")))).scalar_one()
    total = (await session.execute(select(func.count(Source.id)).where(collected))).scalar_one()
    return {"collected": int(total), "ok_last_cycle": int(ok), "failing": int(failing)}


async def _live(inputs: dict, errors: list[str] | None) -> tuple[dict, str]:
    """Primary model, then the fallback on an empty or refused completion. Returns the
    payload and the model that actually wrote it."""
    from mhs.llm import client as llm

    user = json.dumps(inputs, ensure_ascii=False)
    if errors:
        user += ("\n\nYour previous attempt was rejected by the provenance check:\n- " + "\n- ".join(errors)
                 + "\nReturn a corrected report citing only ids, figures and names from the input above.")
    kw = {"system": SYSTEM, "user": user, "schema": REPORT_SCHEMA, "max_tokens": 16000}
    try:
        return await llm.complete_json(model=settings.digest_model, **kw), settings.digest_model
    except llm.LLMEmptyCompletion as exc:
        log.warning("report: %s gave no usable completion (%s); trying %s",
                    settings.digest_model, exc, settings.digest_fallback_model)
        return await llm.complete_json(model=settings.digest_fallback_model, **kw), settings.digest_fallback_model


def _window(today: date | None) -> tuple[date, datetime, datetime]:
    """The report day, and the seven days up to its end (or up to now, when it is today)."""
    now = datetime.now(timezone.utc)
    if today is None or today == now.date():
        until = now
        today = now.date()
    else:
        until = datetime.combine(today, time.max, tzinfo=timezone.utc)
    return today, until - timedelta(days=7), until


async def founders_in_window(session: AsyncSession, *, today: date | None = None) -> int:
    _, since, until = _window(today)
    return int((await session.execute(
        select(func.count(Signal.id)).where(Signal.is_founder.is_(True), Signal.created_at > since,
                                            Signal.created_at <= until))).scalar_one())


async def write_report(session: AsyncSession, *, today: date | None = None) -> Digest | None:
    today, since, until = _window(today)
    signals = await _signals(session, since, until)
    if not signals:
        log.info("report: no founding signals between %s and %s — no report", since, until)
        return None

    movements = await _question_movements(session, today)
    inputs = {
        "week": {"today": today.isoformat(), "monday": _iso_monday(today).isoformat(),
                 "iso_week": today.isocalendar().week, "horizon_end": (today + timedelta(days=HORIZON_DAYS)).isoformat()},
        "signals": signals,
        "questions": await _questions(session, since, until, movements),
        "events": await _events(session, today),
        "edges": await _edges(session, since, until),
        "movers": [m.__dict__ for m in (await trends.movers(session, today=today))[:MAX_MOVERS]],
        "source_health": await _source_health(session),
    }
    ids = {
        # A judgement's signal is in the input even when it is not among this week's founders.
        "signal_ids": {s["id"] for s in signals}
        | {j["signal_id"] for q in inputs["questions"] for j in q["judgements"]},
        "event_ids": {e["id"] for e in inputs["events"]},
        "judgement_ids": {j["id"] for q in inputs["questions"] for j in q["judgements"]},
        "question_ids": {q["id"] for q in inputs["questions"]},
    }
    numbers = input_numbers(inputs) | PROMPT_FIGURES

    model = "mock"
    errors: list[str] | None = None
    payload: dict | None = None
    for attempt in range(2):
        try:
            if settings.llm_enabled:
                raw, model = await _live(inputs, errors)
            else:
                raw, model = mock_report(inputs), "mock"
            payload = validate_report(raw, **ids, numbers=numbers)
            break
        except ReportProvenanceError as exc:
            errors = exc.problems
            log.warning("report rejected (attempt %d): %s", attempt + 1, exc)
        except Exception:  # noqa: BLE001 — the stage fails, the cycle does not
            log.exception("report generation failed")
            break
    if payload is None:
        return None

    # The movement is computed from the judgements, not the model's to choose.
    for q in payload["questions"]:
        q["movement"] = movements.get(q["question_id"], "quiet")

    digest = Digest(week=_iso_monday(today), lead_de=payload["lead_de"], lead_en=payload["lead_en"],
                    friday_de=payload["friday_de"], friday_en=payload["friday_en"], payload=payload, model=model)
    session.add(digest)
    await session.commit()
    log.info("report written for week %s by %s (%d signals)", digest.week, model, len(signals))
    return digest
