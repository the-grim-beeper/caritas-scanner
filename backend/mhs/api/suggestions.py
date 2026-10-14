"""/api/suggestions — the Vorschläge panel: what the weekly scout proposed, when each pending
suggestion will be adopted, and the reader's two buttons (Ablehnen / Jetzt aufnehmen).
Behind the session cookie like every other read route."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from mhs.api.auth import require_session
from mhs.db.engine import get_session, session_factory
from mhs.db.models import Source, SourceSuggestion
from mhs.llm.client import LLMAuthError, LLMEmptyCompletion, LLMRequestError
from mhs.suggest import adopt, run

log = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(require_session)])

StatusFilter = Literal["pending", "adopted", "declined", "rejected", "failed", "all"]


class SuggestionOut(BaseModel):
    id: UUID
    name: str
    url: str
    layer: str
    scope: str
    places: list[str]
    rationale_de: str
    rationale_en: str
    method: str | None
    feed_url: str | None
    items_at_check: int | None
    status: str
    reason: str | None
    suggested_at: datetime
    adopt_after: datetime
    resolved_at: datetime | None
    source_slug: str | None


class RunOut(BaseModel):
    proposed: int
    pending_new: int
    rejected: int
    known: int


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    return session_factory()


def _out(s: SourceSuggestion, source_slug: str | None) -> SuggestionOut:
    return SuggestionOut(
        id=s.id, name=s.name, url=s.url, layer=s.layer, scope=s.scope, places=list(s.places or []),
        rationale_de=s.rationale_de, rationale_en=s.rationale_en, method=s.method, feed_url=s.feed_url,
        items_at_check=s.items_at_check, status=s.status, reason=s.reason, suggested_at=s.suggested_at,
        adopt_after=s.adopt_after, resolved_at=s.resolved_at, source_slug=source_slug,
    )


async def _with_slug(session: AsyncSession, s: SourceSuggestion) -> SuggestionOut:
    slug = (await session.execute(select(Source.slug).where(Source.id == s.source_id))).scalar_one_or_none() \
        if s.source_id else None
    return _out(s, slug)


def _uuid(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="suggestion not found") from exc


@router.get("/suggestions", response_model=list[SuggestionOut])
async def list_suggestions(status: StatusFilter = Query("all"),
                           session: AsyncSession = Depends(get_session)) -> list[SuggestionOut]:
    stmt = (
        select(SourceSuggestion, Source.slug)
        .outerjoin(Source, Source.id == SourceSuggestion.source_id)
        .order_by(case((SourceSuggestion.status == "pending", 0), else_=1), SourceSuggestion.adopt_after)
    )
    if status != "all":
        stmt = stmt.where(SourceSuggestion.status == status)
    return [_out(s, slug) for s, slug in (await session.execute(stmt)).all()]


@router.post("/suggestions/run", response_model=RunOut)
async def run_suggestions(factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory)) -> dict:
    if run.is_running():
        raise HTTPException(status_code=409, detail="a suggestion run is already in progress")
    try:
        return await run.suggest_cycle(factory)
    except run.SuggestRunInProgress as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (LLMAuthError, LLMRequestError, LLMEmptyCompletion) as exc:
        log.warning("suggest run failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"source scout failed: {type(exc).__name__}") from exc


@router.post("/suggestions/{suggestion_id}/decline", response_model=SuggestionOut)
async def decline_suggestion(suggestion_id: str, session: AsyncSession = Depends(get_session)) -> SuggestionOut:
    try:
        s = await adopt.decline(session, _uuid(suggestion_id))
    except adopt.SuggestionNotFound as exc:
        raise HTTPException(status_code=404, detail="suggestion not found") from exc
    except adopt.SuggestionNotPending as exc:
        raise HTTPException(status_code=409, detail=f"suggestion already {exc.status}") from exc
    return await _with_slug(session, s)


@router.post("/suggestions/{suggestion_id}/adopt", response_model=SuggestionOut)
async def adopt_suggestion(suggestion_id: str, session: AsyncSession = Depends(get_session)) -> SuggestionOut:
    try:
        s = await adopt.adopt_now(session, None, _uuid(suggestion_id))
    except adopt.SuggestionNotFound as exc:
        raise HTTPException(status_code=404, detail="suggestion not found") from exc
    except adopt.SuggestionNotPending as exc:
        raise HTTPException(status_code=409, detail=f"suggestion already {exc.status}") from exc
    if s.status != "adopted":
        raise HTTPException(status_code=422, detail=s.reason or "verification failed")
    return await _with_slug(session, s)
