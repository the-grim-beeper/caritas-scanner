"""write_digest — one Claude call (or the mock) over the cycle's founding
signals, upcoming deadlines and trend movers; validated before it is stored."""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from mhs import vocab
from mhs.analyse import trends
from mhs.config import settings
from mhs.db.models import Cycle, Digest, Event, Signal, Source, Story
from mhs.digest.schema import DIGEST_SCHEMA
from mhs.digest.validate import DigestProvenanceError, validate_digest
from mhs.llm.mock import mock_digest

log = logging.getLogger(__name__)

MAX_SIGNALS = 60
MAX_EVENTS = 20

SYSTEM = f"""You write the daily digest of a horizon scanner for social provision in
Landkreis Miesbach (Upper Bavaria), read by Caritas-Zentrum Miesbach and a foresight team
asking whether an inter-municipal coordination structure ("Interkommunale Sozialraumlotsen")
can be anchored so that it still works in 2035 and 2040.

You receive this cycle's founding signals (one per story, ranked by the scanner's
score), the upcoming events and deadlines, and the topics whose volume moved most over
the last four weeks. Write, in English AND German:

- lead: 3–4 sentences on what moved this cycle and why it matters for social provision
  in the county. Concrete, no throat-clearing.
- sections: per layer ({", ".join(vocab.LAYERS)}), the signals worth the reader's
  minute, each with a one- or two-sentence note on why it matters — not a restatement
  of the headline. Omit layers with nothing worth saying. Cite signals by their id.
- chains: cross-layer links you can see between signals in this batch — changes cascade
  across levels (a Bezirksumlage rise → a county budget → a municipal grant cut; a state
  programme ending → a provider's post left empty → a service cutting its hours). Only
  cite ids you were given; two or more per chain.
- watch: the events and deadlines that deserve attention, with why. Cite event ids.

Cite only ids that appear in the input. Do not invent signals, events or numbers."""


def _truncate(text: str | None, n: int = 400) -> str:
    text = (text or "").strip()
    return text if len(text) <= n else text[:n] + "…"


async def _inputs(session: AsyncSession, since: datetime, signal_ids: list[UUID] | None):
    q = (
        select(Signal, Source)
        .join(Source, Source.id == Signal.source_id)
        .options(selectinload(Signal.topics))
        .where(Signal.is_founder.is_(True))
        .order_by(Signal.score.desc())
    )
    q = q.where(Signal.id.in_(signal_ids)) if signal_ids is not None else q.where(Signal.created_at > since)
    rows = (await session.execute(q.limit(MAX_SIGNALS))).all()
    story_ids = [s.story_id for s, _ in rows if s.story_id]
    stories = {st.id: st for st in (await session.execute(select(Story).where(Story.id.in_(story_ids)))).scalars()} if story_ids else {}
    signals = [
        {
            "id": str(s.id),
            "layer": src.layer,
            "source": src.name,
            "type": s.signal_type,
            "score": round(s.score, 4),
            "corroborations": stories[s.story_id].corroboration_count if s.story_id in stories else 0,
            "topics": [t.topic_code for t in s.topics],
            "headline_en": s.headline_en,
            "headline_de": s.headline_de,
            "summary_en": _truncate(s.summary_en),
            "summary_de": _truncate(s.summary_de),
        }
        for s, src in rows
    ]
    today = datetime.now(timezone.utc).date()
    horizon = today + timedelta(days=30)
    ev_rows = (
        await session.execute(
            select(Event)
            .where(
                ((Event.deadline >= today) & (Event.deadline <= horizon))
                | ((Event.start_date >= today) & (Event.start_date <= horizon))
            )
            .order_by(func.coalesce(Event.deadline, Event.start_date))
            .limit(MAX_EVENTS)
        )
    ).scalars().all()
    events = [
        {"id": str(e.id), "name": e.name, "start_date": e.start_date.isoformat() if e.start_date else None,
         "deadline": e.deadline.isoformat() if e.deadline else None, "organizer": e.organizer,
         "funding_program": e.funding_program, "signal_id": str(e.signal_id) if e.signal_id else None}
        for e in ev_rows
    ]
    movers = [m.__dict__ for m in (await trends.movers(session))[:10]]
    return signals, events, movers


async def _live(signals, events, movers, errors: list[str] | None = None) -> dict:
    from mhs.llm.client import complete_json

    user = json.dumps({"signals": signals, "events": events, "movers": movers}, ensure_ascii=False)
    if errors:
        user += "\n\nYour previous attempt was rejected by the provenance check:\n- " + "\n- ".join(errors) + \
                "\nReturn a corrected digest citing only the ids above."
    return await complete_json(
        model=settings.digest_model,
        system=SYSTEM,
        user=user,
        schema=DIGEST_SCHEMA,
        max_tokens=12000,
        fallback_model=settings.digest_fallback_model,
    )


async def write_digest(
    session: AsyncSession,
    cycle: Cycle | None = None,
    *,
    signal_ids: list[UUID] | None = None,
) -> Digest | None:
    last = (await session.execute(select(func.max(Digest.created_at)))).scalar_one()
    since = last or (datetime.now(timezone.utc) - timedelta(days=1))
    signals, events, movers = await _inputs(session, since, signal_ids)
    if not signals:
        log.info("no founding signals since %s — no digest", since)
        if cycle is not None:
            cycle.digest_ok = None
        return None

    sig_ids = {s["id"] for s in signals}
    ev_ids = {e["id"] for e in events}
    model = "mock"
    errors: list[str] | None = None
    payload: dict | None = None
    for attempt in range(2):
        try:
            if settings.llm_enabled:
                model = settings.digest_model
                raw = await _live(signals, events, movers, errors)
            else:
                raw = mock_digest(signals, events, movers)
            validated = validate_digest(raw, signal_ids=sig_ids, event_ids=ev_ids)
            payload = validated.model_dump()
            break
        except DigestProvenanceError as exc:
            errors = exc.problems
            log.warning("digest rejected (attempt %d): %s", attempt + 1, exc)
        except Exception as exc:  # noqa: BLE001
            log.error("digest generation failed: %s", exc)
            break
    if payload is None:
        if cycle is not None:
            cycle.digest_ok = False
        return None
    digest = Digest(cycle_id=cycle.id if cycle else None, lead_en=payload["lead_en"], lead_de=payload["lead_de"],
                    payload=payload, model=model)
    session.add(digest)
    if cycle is not None:
        cycle.digest_ok = True
    await session.commit()
    return digest
