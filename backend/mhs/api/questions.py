"""The fifteen monitoring questions (spec §4.2, §6): a ledger with each question's balance,
movement, 12-week series and latest evidence, and a detail view with every quote.
Mounted under /api by the orchestrator, behind the session cookie."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from mhs.api.auth import require_session
from mhs.config import settings
from mhs.db.engine import get_session
from mhs.db.models import Judgement, Question, Signal
from mhs.questions.balance import WeekPoint, balance_series, movement

router = APIRouter(dependencies=[Depends(require_session)])

SERIES_WEEKS = 12
LATEST_PER_QUESTION = 3
EVIDENCE_MAX = 100

_NEWEST_FIRST = (Signal.published_at.desc(), Judgement.created_at.desc(), Judgement.id)


def _tz() -> ZoneInfo:
    # Weeks are the readers' weeks (the Lagebericht is written Thursday evening, Berlin time).
    return ZoneInfo(settings.report_timezone)


def _local_date(dt: datetime) -> date:
    return dt.astimezone(_tz()).date()


def _today() -> date:
    return datetime.now(_tz()).date()


def judgement_out(j: Judgement, s: Signal) -> dict:
    """JudgementOut — one shape wherever a judgement is shown (needs s.source and s.feed_item loaded)."""
    return {
        "id": str(j.id),
        "question_id": j.question_id,
        "direction": j.direction,
        "strength": j.strength,
        "weight": j.weight,
        "quote": j.quote,
        "rationale_de": j.rationale_de,
        "rationale_en": j.rationale_en,
        "model": j.model,
        "created_at": j.created_at.isoformat() if j.created_at else None,
        "signal": {
            "id": str(s.id),
            "headline_de": s.headline_de,
            "headline_en": s.headline_en,
            "layer": s.source.layer if s.source else None,
            "source_name": s.source.name if s.source else None,
            "url": s.feed_item.url if s.feed_item else None,
            "published_at": s.published_at.isoformat() if s.published_at else None,
        },
    }


def _question_head(q: Question) -> dict:
    return {
        "id": q.id, "sort": q.sort,
        "title_de": q.title_de, "title_en": q.title_en,
        "driver_de": q.driver_de, "driver_en": q.driver_en,
        "for_label_de": q.for_label_de, "for_label_en": q.for_label_en,
        "against_label_de": q.against_label_de, "against_label_en": q.against_label_en,
    }


def _tilt(series: list[WeekPoint]) -> dict:
    return {
        "balance": round(series[-1].balance, 3) if series else 0.0,
        "movement": movement(series),
        "series": [{"week": p.week.isoformat(), "net": round(p.net, 3), "balance": round(p.balance, 3), "n": p.n}
                   for p in series],
        # Over the series window, so the counts read with the sparkline.
        "counts": {"for": sum(p.n_for for p in series), "against": sum(p.n_against for p in series)},
    }


async def _series_by_question(session: AsyncSession, question_id: str | None = None) -> dict[str, list[WeekPoint]]:
    stmt = (select(Judgement.question_id, Signal.published_at, Judgement.direction, Judgement.weight)
            .join(Signal, Signal.id == Judgement.signal_id))
    if question_id is not None:
        stmt = stmt.where(Judgement.question_id == question_id)
    rows: dict[str, list[tuple[date, str, int]]] = defaultdict(list)
    for qid, published, direction, weight in (await session.execute(stmt)).all():
        rows[qid].append((_local_date(published), direction, weight))
    today = _today()
    return {qid: balance_series(js, weeks=SERIES_WEEKS, today=today) for qid, js in rows.items()}


def _empty_series() -> list[WeekPoint]:
    return balance_series([], weeks=SERIES_WEEKS, today=_today())


def _with_signal():
    return (selectinload(Signal.source), selectinload(Signal.feed_item))


async def _latest(session: AsyncSession) -> dict[str, list[dict]]:
    rank = func.row_number().over(partition_by=Judgement.question_id, order_by=_NEWEST_FIRST).label("rk")
    ranked = (select(Judgement.id.label("jid"), rank)
              .join(Signal, Signal.id == Judgement.signal_id)
              .subquery())
    stmt = (select(Judgement, Signal)
            .join(Signal, Signal.id == Judgement.signal_id)
            .join(ranked, ranked.c.jid == Judgement.id)
            .where(ranked.c.rk <= LATEST_PER_QUESTION)
            .options(*_with_signal())
            .order_by(Judgement.question_id, *_NEWEST_FIRST))
    out: dict[str, list[dict]] = defaultdict(list)
    for j, s in (await session.execute(stmt)).all():
        out[j.question_id].append(judgement_out(j, s))
    return out


@router.get("/questions")
async def list_questions(session: AsyncSession = Depends(get_session)) -> list[dict]:
    questions = (await session.execute(select(Question).order_by(Question.sort))).scalars().all()
    if not questions:
        return []
    series = await _series_by_question(session)
    latest = await _latest(session)
    return [
        {**_question_head(q), **_tilt(series.get(q.id) or _empty_series()), "latest": latest.get(q.id, [])}
        for q in questions
    ]


@router.get("/questions/{question_id}")
async def get_question(question_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    q = await session.get(Question, question_id)
    if q is None:
        raise HTTPException(status_code=404, detail="not found")
    series = (await _series_by_question(session, q.id)).get(q.id) or _empty_series()
    rows = (await session.execute(
        select(Judgement, Signal)
        .join(Signal, Signal.id == Judgement.signal_id)
        .where(Judgement.question_id == q.id)
        .options(*_with_signal())
        .order_by(*_NEWEST_FIRST)
        .limit(EVIDENCE_MAX)
    )).all()
    evidence = [judgement_out(j, s) for j, s in rows]
    return {
        **_question_head(q), **_tilt(series),
        "latest": evidence[:LATEST_PER_QUESTION],
        "for_de": q.for_de, "for_en": q.for_en,
        "against_de": q.against_de, "against_en": q.against_en,
        "sources_de": q.sources_de,
        "evidence": evidence,
    }
