"""judge_pending: founders above the relevance floor are read against the fifteen questions,
in batches, live or mock; only validated judgements are written; a signal is marked judged
only when its batch came back in shape."""
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml
from sqlalchemy import func, select

from mhs.config import settings
from mhs.db.models import FeedItem, Judgement, Question, Signal, Source
from mhs.questions.judge import JUDGE_CONCURRENCY, judge_pending, signal_text
from mhs.questions.load import load_questions, upsert_questions

DATA = Path(__file__).resolve().parents[2] / "data"


# ---------------------------------------------------------------------------
# loading the fifteen
# ---------------------------------------------------------------------------
def test_load_questions_reads_the_fifteen_in_order():
    qs = load_questions(DATA / "questions.yaml")
    assert [q["id"] for q in qs] == [f"q{i:02d}" for i in range(1, 16)]
    assert [q["sort"] for q in qs] == list(range(1, 16))
    assert qs[2]["for_label_de"] == "Verstetigung in Sicht"


def test_load_questions_rejects_a_duplicate_or_missing_question(tmp_path):
    qs = yaml.safe_load((DATA / "questions.yaml").read_text())
    dup = [dict(q) for q in qs]
    dup[14]["id"] = "q14"
    (tmp_path / "dup.yaml").write_text(yaml.safe_dump(dup, allow_unicode=True))
    with pytest.raises(ValueError):
        load_questions(tmp_path / "dup.yaml")
    (tmp_path / "short.yaml").write_text(yaml.safe_dump(qs[:14], allow_unicode=True))
    with pytest.raises(ValueError):
        load_questions(tmp_path / "short.yaml")
    blank = [dict(q) for q in qs]
    blank[4]["against_de"] = " "
    (tmp_path / "blank.yaml").write_text(yaml.safe_dump(blank, allow_unicode=True))
    with pytest.raises(ValueError):
        load_questions(tmp_path / "blank.yaml")


async def test_upsert_questions_is_idempotent_and_updates_text(db_session):
    qs = load_questions(DATA / "questions.yaml")
    assert await upsert_questions(db_session, qs) == 15
    qs[0] = {**qs[0], "title_en": "Changed"}
    assert await upsert_questions(db_session, qs) == 0
    assert (await db_session.execute(select(func.count(Question.id)))).scalar_one() == 15
    assert (await db_session.get(Question, "q01")).title_en == "Changed"


# ---------------------------------------------------------------------------
# judging
# ---------------------------------------------------------------------------
async def _questions(db):
    await upsert_questions(db, load_questions(DATA / "questions.yaml"))


async def _signal(db, headline_de, summary_de=None, *, relevance=1.0, layer="landkreis", founder=True,
                  title=None, text=None, published=None) -> Signal:
    src = Source(slug=f"src-{uuid.uuid4().hex[:8]}", name=f"Quelle {layer}", layer=layer, authority="high",
                 scope="landkreis", method="rss", url="https://q.test/rss", collect=True)
    db.add(src)
    await db.flush()
    key = uuid.uuid4().hex
    item = FeedItem(source_id=src.id, external_id=key, title=title or headline_de, summary=text,
                    url=f"https://q.test/{key}", canonical_url=f"https://q.test/{key}", content_hash=key)
    db.add(item)
    await db.flush()
    sig = Signal(feed_item_id=item.id, source_id=src.id, headline_de=headline_de, headline_en=f"EN: {headline_de}",
                 summary_de=summary_de, summary_en=None, signal_type="decision", regional_relevance=relevance,
                 is_founder=founder, published_at=published or datetime.now(timezone.utc))
    db.add(sig)
    await db.commit()
    return sig


async def _judgements(db, signal_id=None):
    stmt = select(Judgement)
    if signal_id is not None:
        stmt = stmt.where(Judgement.signal_id == signal_id)
    return (await db.execute(stmt)).scalars().all()


async def test_mock_judges_a_kreisumlage_founder_with_a_verbatim_quote(db_session):
    await _questions(db_session)
    sig = await _signal(db_session, "Kreistag Miesbach beschließt höhere Kreisumlage für 2027",
                        "Die Gemeinden müssen 2027 mehr an den Landkreis abführen. Waakirchen prüft Kürzungen.")
    stats = await judge_pending(db_session)
    assert stats.judged == 1 and stats.judgements >= 1 and stats.aborted is None
    js = await _judgements(db_session, sig.id)
    q02 = [j for j in js if j.question_id == "q02"]
    assert len(q02) == 1
    j = q02[0]
    assert j.direction == "for" and j.strength == "moderate" and j.weight == 2 and j.model == "mock"
    assert j.quote in (sig.headline_de + "\n" + (sig.summary_de or ""))
    assert j.rationale_de and j.rationale_en
    await db_session.refresh(sig)
    assert sig.judged_by == "mock" and sig.judged_at is not None


async def test_running_twice_writes_no_duplicates(db_session):
    await _questions(db_session)
    await _signal(db_session, "Kreistag Miesbach beschließt höhere Kreisumlage für 2027")
    first = await judge_pending(db_session)
    n = len(await _judgements(db_session))
    second = await judge_pending(db_session)
    assert first.judged == 1 and second.judged == 0 and second.judgements == 0
    assert len(await _judgements(db_session)) == n >= 1


async def test_relevance_floor_with_upstream_and_peer_layers_excepted(db_session):
    # Wrong: judging every founder (cost, noise) — or applying the floor to Bund/Freistaat/peers,
    # whose relevance score is low by construction but which carry q12/q15 evidence.
    await _questions(db_session)
    local_low = await _signal(db_session, "Kreisumlage: Gemeinderat diskutiert", relevance=0.1, layer="gemeinden")
    bund_low = await _signal(db_session, "Bund: Hebesatz-Debatte in den Ländern", relevance=0.1, layer="bund")
    peer_low = await _signal(db_session, "Gemeindeschwester plus wird verstetigt", relevance=0.1, layer="vergleich")
    corrob = await _signal(db_session, "Kreisumlage steigt (Zweitmeldung)", founder=False)
    stats = await judge_pending(db_session)
    assert stats.judged == 2
    for s in (local_low, bund_low, peer_low, corrob):
        await db_session.refresh(s)
    assert local_low.judged_by is None and corrob.judged_by is None
    assert bund_low.judged_by == "mock" and peer_low.judged_by == "mock"


async def test_signal_with_no_evidence_is_still_marked_judged(db_session):
    # Wrong: marking only signals that produced a judgement — the rest are re-sent every cycle.
    await _questions(db_session)
    sig = await _signal(db_session, "Landratsamt veröffentlicht neue Öffnungszeiten der Zulassungsstelle")
    stats = await judge_pending(db_session)
    assert stats.judged == 1 and stats.judgements == 0
    await db_session.refresh(sig)
    assert sig.judged_by == "mock"
    assert (await judge_pending(db_session)).judged == 0


async def test_limit_caps_the_number_of_signals_read(db_session):
    await _questions(db_session)
    for i in range(3):
        await _signal(db_session, f"Kreisumlage Meldung {i} mit genug Text für ein Zitat")
    assert (await judge_pending(db_session, limit=2)).judged == 2
    assert (await judge_pending(db_session)).judged == 1


async def test_signal_text_joins_headlines_summaries_and_the_source_item(db_session):
    sig = await _signal(db_session, "Kopfzeile DE", "Zusammenfassung DE", title="Originaltitel",
                        text="Originaltext aus der Quelle")
    loaded = (await db_session.execute(select(Signal).where(Signal.id == sig.id))).scalar_one()
    await db_session.refresh(loaded, ["feed_item"])
    t = signal_text(loaded)
    for part in ("Kopfzeile DE", "Zusammenfassung DE", "EN: Kopfzeile DE", "Originaltitel", "Originaltext aus der Quelle"):
        assert part in t


# ---------------------------------------------------------------------------
# live path (the model is faked; no money is spent)
# ---------------------------------------------------------------------------
def _live(monkeypatch):
    from mhs import config
    monkeypatch.setattr(config.settings, "anthropic_api_key", "sk-test")


async def test_live_wiring_model_fallback_cached_questions_and_source_text(db_session, monkeypatch):
    # Wrong: the questions in the per-call user message (no cache), the wrong model, or the
    # original source text withheld so the model can only quote the scanner's own summary.
    from mhs.llm import client as llm_client

    await _questions(db_session)
    _live(monkeypatch)
    await _signal(db_session, "Kreisumlage steigt", text="Der Kreistag hat am Montag die Kreisumlage auf 52 Punkte erhöht.")
    seen = {}

    async def fake_complete_json(**kw):
        seen.update(kw)
        return {"judgements": []}

    monkeypatch.setattr(llm_client, "complete_json", fake_complete_json)
    stats = await judge_pending(db_session)
    assert stats.judged == 1
    assert seen["model"] == settings.judge_model and seen["fallback_model"] == settings.digest_fallback_model
    assert seen["max_tokens"] == 8000
    system = seen["system"]
    assert isinstance(system, list) and system[-1]["cache_control"] == {"type": "ephemeral"}
    sys_text = "".join(b["text"] for b in system)
    for i in range(1, 16):
        assert f"q{i:02d}" in sys_text
    # The fifteen live in the cached system block, the batch in the user message — never the reverse.
    assert "Are municipalities losing discretionary capacity" in sys_text
    assert "Are municipalities losing discretionary capacity" not in seen["user"]
    assert "52 Punkte" not in sys_text
    assert "auf 52 Punkte erhöht" in seen["user"]
    assert seen["schema"]["properties"]["judgements"]["type"] == "array"


async def test_live_keeps_valid_drops_paraphrase_and_foreign_ids(db_session, monkeypatch):
    from mhs.questions import judge

    await _questions(db_session)
    sig = await _signal(db_session, "Kreistag erhöht Kreisumlage",
                        text="Der Kreistag hat die Kreisumlage auf 52 Punkte erhöht. Hausham streicht deshalb den Zuschuss.")
    _live(monkeypatch)

    async def fake_live(system, user):
        return {"judgements": [
            {"signal_id": "s1", "question_id": "q02", "direction": "for", "strength": "strong",
             "quote": "Hausham streicht deshalb den Zuschuss", "rationale_de": "Umlage verdrängt.", "rationale_en": "Levy crowds out."},
            {"signal_id": "s1", "question_id": "q01", "direction": "for", "strength": "moderate",
             "quote": "Gemeinden verlieren Spielraum", "rationale_de": "x", "rationale_en": "x"},  # paraphrase
            {"signal_id": "s7", "question_id": "q02", "direction": "for", "strength": "weak",
             "quote": "Der Kreistag hat die Kreisumlage", "rationale_de": "x", "rationale_en": "x"},  # not in batch
        ]}

    monkeypatch.setattr(judge, "_judge_live", fake_live)
    stats = await judge_pending(db_session)
    assert stats.judged == 1 and stats.judgements == 1 and stats.dropped == 2
    (j,) = await _judgements(db_session)
    assert (j.signal_id, j.question_id, j.weight, j.model) == (sig.id, "q02", 3, settings.judge_model)
    await db_session.refresh(sig)
    assert sig.judged_by == settings.judge_model


async def test_new_judge_model_rereads_and_replaces_the_old_reading(db_session, monkeypatch):
    # Wrong: keeping the mock's (or an older model's) judgements next to the new ones, so the
    # same signal counts twice in the balance.
    from mhs.questions import judge

    await _questions(db_session)
    sig = await _signal(db_session, "Kreistag Miesbach beschließt höhere Kreisumlage für 2027")
    await judge_pending(db_session)
    assert {j.model for j in await _judgements(db_session)} == {"mock"}

    _live(monkeypatch)

    async def fake_live(system, user):
        return {"judgements": [{"signal_id": "s1", "question_id": "q02", "direction": "for", "strength": "strong",
                                "quote": "beschließt höhere Kreisumlage", "rationale_de": "a", "rationale_en": "b"}]}

    monkeypatch.setattr(judge, "_judge_live", fake_live)
    stats = await judge_pending(db_session)
    assert stats.judged == 1
    js = await _judgements(db_session)
    assert [(j.model, j.question_id, j.strength) for j in js] == [(settings.judge_model, "q02", "strong")]
    await db_session.refresh(sig)
    assert sig.judged_by == settings.judge_model


async def test_wrong_shape_is_retried_once(db_session, monkeypatch):
    from mhs.questions import judge

    await _questions(db_session)
    sig = await _signal(db_session, "Kreisumlage steigt deutlich an")
    _live(monkeypatch)
    calls = []

    async def flaky(system, user):
        calls.append(1)
        return {"answers": []} if len(calls) == 1 else {"judgements": []}

    monkeypatch.setattr(judge, "_judge_live", flaky)
    stats = await judge_pending(db_session)
    assert len(calls) == 2 and stats.judged == 1
    await db_session.refresh(sig)
    assert sig.judged_by == settings.judge_model


async def test_wrong_shape_twice_leaves_the_batch_unjudged(db_session, monkeypatch):
    # Wrong: marking a batch judged although nothing usable came back — its signals are never read.
    from mhs.questions import judge

    await _questions(db_session)
    sig = await _signal(db_session, "Kreisumlage steigt deutlich an")
    _live(monkeypatch)
    calls = []

    async def broken(system, user):
        calls.append(1)
        return ["not", "an", "object"]

    monkeypatch.setattr(judge, "_judge_live", broken)
    stats = await judge_pending(db_session)
    assert len(calls) == 2 and stats.judged == 0
    await db_session.refresh(sig)
    assert sig.judged_by is None


async def test_auth_error_aborts_all_batches(db_session, monkeypatch):
    # Wrong: catching the 401 per batch and carrying on — a dead key costs one call per batch.
    from mhs.llm.client import LLMAuthError
    from mhs.questions import judge

    await _questions(db_session)
    monkeypatch.setattr(settings, "judge_batch_size", 1)
    for i in range(12):
        await _signal(db_session, f"Kreisumlage Meldung {i}")
    _live(monkeypatch)
    calls = []

    async def dead(system, user):
        calls.append(1)
        raise LLMAuthError("API key is invalid")

    monkeypatch.setattr(judge, "_judge_live", dead)
    stats = await judge_pending(db_session)
    assert len(calls) <= JUDGE_CONCURRENCY
    assert stats.judged == 0 and stats.aborted == "LLMAuthError: API key is invalid"
    marked = (await db_session.execute(select(func.count(Signal.id)).where(Signal.judged_by.is_not(None)))).scalar_one()
    assert marked == 0


async def test_batches_are_judge_batch_size(db_session, monkeypatch):
    from mhs.questions import judge

    await _questions(db_session)
    monkeypatch.setattr(settings, "judge_batch_size", 2)
    for i in range(5):
        await _signal(db_session, f"Meldung {i}", published=datetime.now(timezone.utc) - timedelta(days=i))
    _live(monkeypatch)
    sizes = []

    async def fake_live(system, user):
        sizes.append(user.count("<signal id="))
        return {"judgements": []}

    monkeypatch.setattr(judge, "_judge_live", fake_live)
    stats = await judge_pending(db_session)
    assert sorted(sizes) == [1, 2, 2] and stats.judged == 5
