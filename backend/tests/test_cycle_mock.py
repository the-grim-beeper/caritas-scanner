"""End to end in mock mode over fixture feeds: adopt → collect → extract → analyse →
judge → network → trends, with the cycle record telling the truth about each stage.
The weekly Lagebericht is its own job; the daily cycle writes no report."""
from pathlib import Path

import httpx
import respx
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from mhs.cycle import run_cycle
from mhs.db.models import Cycle, Digest, Judgement, Signal, Source, Story, TrendCell
from mhs.entities import load_seed

FIX = Path(__file__).parent / "fixtures"
DATA = Path(__file__).resolve().parents[2] / "data"


@respx.mock
async def test_mock_cycle_produces_signals_stories_judgements_and_trends_but_no_report(db_session, session_factory, monkeypatch):
    from scripts.load_sources import upsert_entities
    from mhs.questions.load import load_questions, upsert_questions
    from mhs import config
    from mhs.analyse import embedding

    monkeypatch.setattr(config.settings, "max_item_age_days", 36500)  # fixed fixture dates must not age out
    await upsert_entities(db_session, load_seed(DATA / "entities.yaml"))
    await upsert_questions(db_session, load_questions(DATA / "questions.yaml"))
    a = Source(slug="merkur-miesbach", name="Merkur Region Miesbach", layer="medien", authority="medium",
               scope="landkreis", method="rss", url="https://mm.test/a.xml", collect=True)
    b = Source(slug="merkur-holzkirchen", name="Merkur Holzkirchen", layer="medien", authority="medium",
               scope="landkreis", method="rss", url="https://mm.test/b.xml", collect=True)
    db_session.add_all([a, b])
    await db_session.commit()
    respx.get("https://mm.test/a.xml").mock(return_value=httpx.Response(200, content=(FIX / "feed_a.xml").read_bytes()))
    respx.get("https://mm.test/b.xml").mock(return_value=httpx.Response(200, content=(FIX / "feed_b.xml").read_bytes()))

    # Deterministic embeddings keyed on the text — no model download in tests.
    def fake_embed(texts):
        import hashlib
        out = []
        for t in texts:
            h = hashlib.sha256(t.encode()).digest()
            vec = [((b_ - 128) / 128.0) for b_ in (h * 12)[:384]]
            out.append(vec)
        return out
    monkeypatch.setattr(embedding, "embed_texts", fake_embed)
    monkeypatch.setattr("mhs.analyse.run.embed_texts", fake_embed)

    cycle = await run_cycle(session_factory)

    assert cycle.mode == "mock"
    assert cycle.items_new == 2 and cycle.extracted == 2
    assert cycle.signals == 2 and cycle.stories_new == 2
    assert cycle.finished_at is not None and cycle.error is None
    # The judge ran over the founders and wrote provenance-checked judgements.
    assert cycle.judged == 2 and cycle.judgements >= 1

    signals = (await db_session.execute(select(Signal).options(selectinload(Signal.topics)))).scalars().all()
    assert all(s.embedding is not None and s.story_id is not None for s in signals)
    by_topic = {t.topic_code: s for s in signals for t in s.topics}
    assert "umlagen" in by_topic and "pflege" in by_topic
    assert by_topic["umlagen"].consequence > 0 and by_topic["umlagen"].regional_relevance == 1.0
    assert all(s.judged_by == "mock" for s in signals)
    judgements = (await db_session.execute(select(Judgement))).scalars().all()
    texts = {str(s.id): " ".join(filter(None, [s.headline_de, s.summary_de, s.headline_en, s.summary_en])) for s in signals}
    assert judgements and all(j.quote and str(j.signal_id) in texts for j in judgements)
    assert any(j.question_id == "q02" and j.direction == "for" for j in judgements)  # Kreisumlage rise
    assert (await db_session.execute(select(Story))).scalars().all()
    assert (await db_session.execute(select(TrendCell))).scalars().all()
    assert (await db_session.execute(select(Digest))).scalars().all() == []

    # A second cycle changes nothing and judges nothing twice.
    cycle2 = await run_cycle(session_factory)
    assert cycle2.items_new == 0 and cycle2.signals == 0 and cycle2.judged == 0
    assert len((await db_session.execute(select(Judgement))).scalars().all()) == len(judgements)
    assert (await db_session.execute(select(Cycle))).scalars().all().__len__() == 2
