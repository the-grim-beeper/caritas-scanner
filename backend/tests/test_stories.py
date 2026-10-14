"""Stories: a second outlet's version of the same development joins the story;
a different development founds a new one."""
from datetime import timedelta

import numpy as np
import pytest

from mhs.analyse import stories
from mhs.db.models import Signal, Source, Story, utcnow


def _unit(seed: int, dim: int = 384) -> list[float]:
    rng = np.random.default_rng(seed)
    v = rng.normal(size=dim)
    return (v / np.linalg.norm(v)).tolist()


def _near(vec: list[float], eps: float = 0.02) -> list[float]:
    v = np.array(vec) + eps * np.array(_unit(999))
    return (v / np.linalg.norm(v)).tolist()


async def _src(db_session, slug):
    s = Source(slug=slug, name=slug, layer="medien", authority="high", scope="landkreis", method="rss",
               url=f"https://{slug}.test/f", collect=True)
    db_session.add(s)
    await db_session.flush()
    return s


async def _signal(db_session, src, vec, headline="x", when=None):
    sig = Signal(source_id=src.id, headline_en=headline, headline_de=headline, signal_type="announcement",
                 authority=1.0, regional_relevance=1.0, consequence=0.5, forward_lag=0.7,
                 embedding=vec, published_at=when or utcnow())
    db_session.add(sig)
    await db_session.flush()
    return sig


async def test_near_signal_joins_story_and_distinct_sources_counts_only_new_outlets(db_session):
    # Wrong: corroboration_count and distinct_sources both increment on every join,
    # so two items from the same outlet look like independent confirmation.
    a, b = await _src(db_session, "merkur"), await _src(db_session, "br24")
    base = _unit(1)
    s1 = await _signal(db_session, a, base, "Kreisumlage steigt")
    d1 = await stories.assign(db_session, s1, threshold=0.22)
    assert d1.founded and s1.is_founder

    s2 = await _signal(db_session, b, _near(base), "Kreistag erhöht Kreisumlage")
    d2 = await stories.assign(db_session, s2, threshold=0.22)
    assert not d2.founded and d2.story_id == d1.story_id and not s2.is_founder

    s3 = await _signal(db_session, b, _near(base, 0.03), "Kreisumlage: Details")
    await stories.assign(db_session, s3, threshold=0.22)

    story = await db_session.get(Story, d1.story_id)
    assert story.corroboration_count == 2
    assert story.distinct_sources == 2
    assert story.confidence == pytest.approx(0.75)


async def test_far_signal_founds_a_new_story_with_full_novelty(db_session):
    a = await _src(db_session, "merkur")
    s1 = await _signal(db_session, a, _unit(1))
    await stories.assign(db_session, s1, threshold=0.22)
    s2 = await _signal(db_session, a, _unit(2))
    d2 = await stories.assign(db_session, s2, threshold=0.22)
    assert d2.founded and d2.story_id != s1.story_id
    assert s2.novelty == 1.0 and s2.score > 0


async def test_corroboration_has_zero_novelty_and_story_score_is_max_of_members(db_session):
    a, b = await _src(db_session, "merkur"), await _src(db_session, "br24")
    base = _unit(3)
    s1 = await _signal(db_session, a, base)
    await stories.assign(db_session, s1, threshold=0.22)
    s2 = await _signal(db_session, b, _near(base))
    await stories.assign(db_session, s2, threshold=0.22)
    assert s2.novelty == 0.0 and s2.score == 0.0
    story = await db_session.get(Story, s1.story_id)
    assert story.score == pytest.approx(s1.score)


async def test_old_signals_outside_window_do_not_absorb_new_ones(db_session):
    a = await _src(db_session, "merkur")
    base = _unit(4)
    old = await _signal(db_session, a, base, when=utcnow() - timedelta(days=40))
    await stories.assign(db_session, old, threshold=0.22)
    new = await _signal(db_session, a, _near(base))
    d = await stories.assign(db_session, new, threshold=0.22, window_days=14)
    assert d.founded


def test_novelty_scales_distance_over_twice_the_threshold():
    assert stories.novelty(0.0, 0.22) == 0.0
    assert stories.novelty(0.22, 0.22) == pytest.approx(0.5)
    assert stories.novelty(0.9, 0.22) == 1.0
    assert stories.novelty(None, 0.22) == 1.0  # nothing to compare with → fully novel
