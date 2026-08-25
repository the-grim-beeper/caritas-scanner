"""Stories: one development, possibly reported by several outlets.

The brief: "Secondary newspaper confirmation can then raise confidence without
making the duplicated story appear as several separate signals." A new signal
whose nearest recent neighbour is closer than the threshold *joins* that story as
a corroboration (row kept, novelty 0); otherwise it founds a new story."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from rns.analyse.scoring import ScoreComponents, score, story_confidence
from rns.config import settings
from rns.db.models import Signal, Story


@dataclass(frozen=True)
class StoryDecision:
    story_id: UUID
    founded: bool
    distance: float | None


def novelty(distance: float | None, threshold: float) -> float:
    """0 at distance 0, 0.5 at the story threshold, 1 at twice the threshold or
    beyond. Nothing to compare with is fully novel."""
    if distance is None:
        return 1.0
    return max(0.0, min(1.0, distance / (2 * threshold)))


def _score_signal(signal: Signal) -> float:
    return score(ScoreComponents(
        authority=signal.authority,
        regional_relevance=signal.regional_relevance,
        novelty=signal.novelty,
        economic_materiality=signal.economic_materiality,
        forward_lag=signal.forward_lag,
    ))


async def _nearest(session: AsyncSession, signal: Signal, window_days: int) -> tuple[Signal | None, float | None]:
    lo = signal.published_at - timedelta(days=window_days)
    hi = signal.published_at + timedelta(days=window_days)
    dist = Signal.embedding.cosine_distance(signal.embedding).label("d")
    row = (
        await session.execute(
            select(Signal, dist)
            .where(
                Signal.id != signal.id,
                Signal.story_id.isnot(None),
                Signal.embedding.isnot(None),
                Signal.published_at >= lo,
                Signal.published_at <= hi,
            )
            .order_by(dist)
            .limit(1)
        )
    ).first()
    if row is None:
        return None, None
    return row[0], float(row[1])


async def _refresh_story(session: AsyncSession, story: Story) -> None:
    distinct = (
        await session.execute(
            select(func.count(func.distinct(Signal.source_id))).where(Signal.story_id == story.id)
        )
    ).scalar_one()
    members = (
        await session.execute(select(func.count(Signal.id), func.max(Signal.score), func.max(Signal.published_at))
                              .where(Signal.story_id == story.id))
    ).one()
    story.corroboration_count = max(0, int(members[0]) - 1)
    story.distinct_sources = max(1, int(distinct))
    story.confidence = story_confidence(story.distinct_sources)
    story.score = float(members[1] or 0.0)
    story.last_seen = members[2] or story.last_seen


async def assign(
    session: AsyncSession,
    signal: Signal,
    *,
    threshold: float | None = None,
    window_days: int | None = None,
) -> StoryDecision:
    threshold = settings.story_threshold if threshold is None else threshold
    window_days = settings.story_window_days if window_days is None else window_days
    if signal.embedding is None:
        raise ValueError("signal must be embedded before story assignment")

    nearest, distance = await _nearest(session, signal, window_days)
    signal.nearest_distance = distance

    if nearest is not None and distance is not None and distance < threshold:
        story = await session.get(Story, nearest.story_id)
        signal.story_id = story.id
        signal.is_founder = False
        signal.novelty = 0.0
        signal.score = 0.0
        await session.flush()
        await _refresh_story(session, story)
        await session.flush()
        return StoryDecision(story_id=story.id, founded=False, distance=distance)

    signal.novelty = novelty(distance, threshold)
    signal.score = _score_signal(signal)
    signal.is_founder = True
    story = Story(
        founding_signal_id=signal.id,
        corroboration_count=0,
        distinct_sources=1,
        confidence=story_confidence(1),
        score=signal.score,
        first_seen=signal.published_at,
        last_seen=signal.published_at,
    )
    session.add(story)
    await session.flush()
    signal.story_id = story.id
    await session.flush()
    return StoryDecision(story_id=story.id, founded=True, distance=distance)
