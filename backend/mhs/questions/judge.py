"""judge_pending — read founding signals against the fifteen monitoring questions.

Founders above the relevance floor (Bund, Freistaat and peer cases excepted) that the
current judge model has not read go to the model in batches; every judgement it returns
passes the provenance validator before it is written. A batch whose payload came back in
shape marks all its signals judged, even with zero judgements; a batch that failed leaves
them for the next cycle. Live (Claude) or mock, same shape."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from mhs import vocab
from mhs.config import settings
from mhs.db.models import Judgement, Question, Signal, Source, utcnow
from mhs.llm.client import LLMAuthError, LLMRequestError
from mhs.questions import prompt
from mhs.questions.mock import mock_judge
from mhs.questions.schema import JUDGE_SCHEMA
from mhs.questions.validate import JudgementDraft, JudgementShapeError, validate_judgements

log = logging.getLogger(__name__)

# Layers judged regardless of regional relevance: their relevance score is low by
# construction, but they carry the upstream (q02, q12) and peer-model (q15) evidence.
ALWAYS_JUDGED_LAYERS: tuple[str, ...] = ("vergleich", "bund", "freistaat")
JUDGE_CONCURRENCY = 4
SHAPE_ATTEMPTS = 2  # a wrong-shape payload is retried once
MOCK_MODEL = "mock"


@dataclass
class JudgeStats:
    judged: int = 0
    judgements: int = 0
    dropped: int = 0
    # Set when the run was stopped early (a rejected key, a rejected request shape, no questions).
    aborted: str | None = None


def current_model() -> str:
    return settings.judge_model if settings.llm_enabled else MOCK_MODEL


def signal_fields(s: Signal) -> list[str]:
    """Every text a quote may come from, each on its own: a quote must lie wholly within one.
    The source item's own title and text first, so the stored span is the source's wherever
    it says the same thing; then the scanner's headline and summary in both languages.
    Needs `feed_item` loaded."""
    item = s.feed_item
    parts = (item.title if item else None, item.summary if item else None,
             s.headline_de, s.summary_de, s.headline_en, s.summary_en)
    return [p for p in parts if p]


def signal_text(s: Signal) -> str:
    """The fields joined with newlines — what the mock reads, sentence by sentence."""
    return "\n".join(signal_fields(s))


async def _judge_live(system: list[dict], user: str) -> dict:
    from mhs.llm.client import complete_json

    return await complete_json(
        model=settings.judge_model,
        system=system,
        user=user,
        schema=JUDGE_SCHEMA,
        max_tokens=8000,
        fallback_model=settings.digest_fallback_model,
    )


class _Abort:
    """Shared across one run: the first authentication or request-shape error stops every later call."""

    def __init__(self) -> None:
        self.reason: str | None = None


@dataclass
class _Outcome:
    batch: list[tuple[str, Signal]]
    kept: list[JudgementDraft] | None = None  # None: no usable payload, signals stay pending
    problems: list[str] = field(default_factory=list)


async def _run_batch(
    batch: list[tuple[str, Signal]], fields: dict[str, list[str]], system: list[dict], question_ids: set[str],
    sem: asyncio.Semaphore, abort: _Abort,
) -> _Outcome:
    user = prompt.user_message(batch)
    async with sem:
        for attempt in range(1, SHAPE_ATTEMPTS + 1):
            if abort.reason:
                return _Outcome(batch)
            try:
                if settings.llm_enabled:
                    raw = await _judge_live(system, user)
                else:
                    raw = mock_judge({lid: "\n".join(f) for lid, f in fields.items()})
            except (LLMAuthError, LLMRequestError) as exc:
                abort.reason = f"{type(exc).__name__}: {exc}"
                log.error("judge aborted: %s", exc)
                return _Outcome(batch)
            except Exception as exc:  # noqa: BLE001 — one failed batch must not sink the run
                log.warning("judge batch failed: %s", exc)
                return _Outcome(batch)
            try:
                kept, problems = validate_judgements(raw, signal_texts=fields, question_ids=question_ids)
            except JudgementShapeError as exc:
                log.warning("judge payload in the wrong shape (attempt %d/%d): %s", attempt, SHAPE_ATTEMPTS, exc)
                continue
            return _Outcome(batch, kept, problems)
    return _Outcome(batch)


async def _pending(session: AsyncSession, model: str, limit: int) -> list[Signal]:
    # A new live model re-reads what an older model (or the mock) judged. The mock re-reads
    # nothing: run without a key, it must never replace a paid reading with keyword hits.
    unread = Signal.judged_by.is_(None)
    if model != MOCK_MODEL:
        unread = or_(unread, Signal.judged_by != model)
    stmt = (
        select(Signal)
        .outerjoin(Source, Source.id == Signal.source_id)
        .options(selectinload(Signal.source), selectinload(Signal.feed_item))
        .where(
            Signal.is_founder.is_(True),
            unread,
            or_(Signal.regional_relevance >= settings.judge_min_relevance,
                Source.layer.in_(ALWAYS_JUDGED_LAYERS)),
        )
        # Newest first: under the cap, this week's evidence beats the backfill's.
        .order_by(Signal.published_at.desc(), Signal.id)
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())


async def judge_pending(session: AsyncSession, *, limit: int | None = None) -> JudgeStats:
    stats = JudgeStats()
    model = current_model()
    questions = (await session.execute(select(Question).order_by(Question.sort))).scalars().all()
    if not questions:
        stats.aborted = "no questions loaded (run scripts/load_sources.py)"
        log.warning("judge: %s", stats.aborted)
        return stats

    # Cost guard: half the extraction cap per run, unless the caller says otherwise.
    limit = limit or max(1, settings.max_extractions_per_cycle // 2)
    signals = await _pending(session, model, limit)
    if not signals:
        return stats

    system = prompt.system_blocks(questions)
    question_ids = {q.id for q in questions}
    size = max(1, settings.judge_batch_size)
    batches: list[tuple[list[tuple[str, Signal]], dict[str, list[str]]]] = []
    for start in range(0, len(signals), size):
        # Batch-local ids (s1, s2, …): nothing for the model to mistype, and an id from
        # another batch cannot validate.
        batch = [(f"s{i}", s) for i, s in enumerate(signals[start:start + size], start=1)]
        batches.append((batch, {lid: signal_fields(s) for lid, s in batch}))

    sem = asyncio.Semaphore(JUDGE_CONCURRENCY if settings.llm_enabled else 64)
    abort = _Abort()
    outcomes = await asyncio.gather(*(_run_batch(b, f, system, question_ids, sem, abort) for b, f in batches))
    stats.aborted = abort.reason

    now = utcnow()
    for out in outcomes:
        if out.kept is None:
            continue
        stats.dropped += len(out.problems)
        for problem in out.problems:
            log.info("judge dropped %s", problem)
        by_local = dict(out.batch)
        # A savepoint per batch: one bad write must not roll back the other paid calls.
        try:
            async with session.begin_nested():
                # One reading per signal: a re-read by a new model replaces the old one, so a
                # signal never counts twice in a balance.
                await session.execute(delete(Judgement).where(Judgement.signal_id.in_([s.id for _, s in out.batch])))
                for d in out.kept:
                    session.add(Judgement(
                        signal_id=by_local[d.signal_id].id, question_id=d.question_id, direction=d.direction,
                        strength=d.strength, weight=vocab.STRENGTH_WEIGHTS[d.strength], quote=d.quote,
                        rationale_de=d.rationale_de, rationale_en=d.rationale_en, model=model,
                    ))
                for _, s in out.batch:
                    s.judged_by = model
                    s.judged_at = now
                await session.flush()
        except Exception as exc:  # noqa: BLE001
            log.warning("persisting a judge batch failed: %s", exc)
            continue
        stats.judged += len(out.batch)
        stats.judgements += len(out.kept)
    await session.commit()
    return stats
