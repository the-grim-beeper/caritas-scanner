"""Once a key is set, the Lagebericht reads only live judgements — the same rule the
questions API applies — so a report never cites evidence the UI no longer shows."""
from datetime import date, datetime, timedelta, timezone

from mhs.config import settings
from mhs.db.models import Judgement, Question, Signal, Source
from mhs.report.run import _question_movements, _questions


async def _seed(db_session, model: str):
    q = Question(id="q02", sort=2, title_de="t", title_en="t", driver_de="d", driver_en="d", sources_de="s",
                 for_label_de="f", for_label_en="f", for_de="f", for_en="f",
                 against_label_de="a", against_label_en="a", against_de="a", against_en="a")
    src = Source(slug="lk", name="LK", layer="landkreis", authority="high", scope="landkreis", method="rss")
    db_session.add_all([q, src])
    await db_session.flush()
    now = datetime.now(timezone.utc)
    s = Signal(source_id=src.id, headline_de="Kreistag erhöht die Kreisumlage deutlich", headline_en="h",
               signal_type="budget", published_at=now - timedelta(days=1))
    db_session.add(s)
    await db_session.flush()
    db_session.add(Judgement(signal_id=s.id, question_id="q02", direction="for", strength="strong", weight=3,
                             quote="Kreistag erhöht die Kreisumlage deutlich", rationale_de="r", rationale_en="r",
                             model=model))
    await db_session.commit()
    return now


async def test_live_report_ignores_mock_judgements(db_session, monkeypatch):
    now = await _seed(db_session, "mock")
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-test")  # live mode
    qs = await _questions(db_session, now - timedelta(days=7), now + timedelta(minutes=1), {})
    assert qs[0]["judgements"] == []
    assert (await _question_movements(db_session, date.today()))["q02"] == "quiet"


async def test_live_report_keeps_live_judgements(db_session, monkeypatch):
    now = await _seed(db_session, "claude-sonnet-5-5")
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-test")
    qs = await _questions(db_session, now - timedelta(days=7), now + timedelta(minutes=1), {})
    assert len(qs[0]["judgements"]) == 1
    assert (await _question_movements(db_session, date.today()))["q02"] == "for"
