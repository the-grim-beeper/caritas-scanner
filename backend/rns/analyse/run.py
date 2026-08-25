"""analyse_pending — embed every un-embedded signal, then assign stories in
publication order so a corroboration always finds its founder."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rns.analyse import stories
from rns.analyse.embedding import embed_texts, signal_text
from rns.db.models import Signal


@dataclass
class AnalyseStats:
    embedded: int = 0
    stories_new: int = 0
    corroborations: int = 0


async def analyse_pending(session: AsyncSession) -> AnalyseStats:
    stats = AnalyseStats()
    pending = (
        await session.execute(
            select(Signal).where(Signal.embedding.is_(None)).order_by(Signal.published_at.asc())
        )
    ).scalars().all()
    if not pending:
        return stats
    texts = [signal_text(s.headline_de, s.summary_de) for s in pending]
    vectors = await asyncio.to_thread(embed_texts, texts)
    for sig, vec in zip(pending, vectors):
        sig.embedding = vec
    await session.flush()
    stats.embedded = len(pending)
    for sig in pending:
        decision = await stories.assign(session, sig)
        if decision.founded:
            stats.stories_new += 1
        else:
            stats.corroborations += 1
    await session.commit()
    return stats
