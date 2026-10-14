"""The weekly proposer: prompt context (coverage gaps, questions, headlines, known URLs), the
web-search call (mocked — tests never spend money) and the parse that enforces the vocabulary."""
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import anthropic
import httpx
import pytest

from mhs.config import settings
from mhs.db.models import Entity, Question, Signal, Source, SourceSuggestion, utcnow
from mhs.entities import load_seed
from mhs.llm.client import LLMAuthError, LLMRequestError
from mhs.suggest import discover
from mhs.suggest.discover import MUNICIPALITIES, SCHEMA, build_prompt, parse_candidates, propose

PLACES = {"weyarn": "Weyarn", "gmund": "Gmund a. Tegernsee", "gmund a. tegernsee": "Gmund a. Tegernsee",
          "miesbach": "Miesbach"}


def _cand(**over) -> dict:
    base = {"name": "Gemeinde Weyarn – Aktuelles", "url": "https://www.weyarn.de/aktuelles", "layer": "gemeinden",
            "scope": "gemeinde", "places": ["Weyarn"], "rationale_de": "Weyarn hat noch keine Quelle.",
            "rationale_en": "Weyarn has no source yet."}
    return {**base, **over}


def test_discovery_payload_with_unknown_layer_is_dropped():
    out = parse_candidates({"candidates": [_cand(layer="policy"), _cand(scope="planet"), _cand()]}, PLACES)
    assert [c.layer for c in out] == ["gemeinden"]


def test_places_outside_the_closed_set_are_dropped_and_aliases_resolve():
    out = parse_candidates({"candidates": [_cand(places=["gmund", "Atlantis", "WEYARN", "Weyarn"])]}, PLACES)
    assert out[0].places == ["Gmund a. Tegernsee", "Weyarn"]


def test_bad_urls_are_dropped_and_the_list_is_capped(monkeypatch):
    monkeypatch.setattr(settings, "suggest_max_candidates", 3)
    junk = [_cand(url="javascript:alert(1)"), _cand(url="ftp://a.test/x"), _cand(url="not a url"),
            _cand(url="https://" + "a" * 2100 + ".test/"), _cand(name="  ")]
    good = [_cand(url=f"https://g{i}.test/aktuelles") for i in range(5)]
    out = parse_candidates({"candidates": junk + good}, PLACES)
    assert [c.url for c in out] == ["https://g0.test/aktuelles", "https://g1.test/aktuelles", "https://g2.test/aktuelles"]
    assert parse_candidates({"nonsense": 1}, PLACES) == []
    assert parse_candidates({"candidates": "x"}, PLACES) == []


def test_schema_has_no_count_keywords_the_api_rejects():
    text = repr(SCHEMA)
    for kw in ("minItems", "maxItems", "minimum", "maximum", "minLength", "maxLength"):
        assert kw not in text


def test_the_seventeen_municipalities_are_seeded_places():
    seeds = load_seed(Path(__file__).resolve().parents[2] / "data" / "entities.yaml")
    places = {s.name for s in seeds if s.kind == "place"}
    assert len(MUNICIPALITIES) == 17 and set(MUNICIPALITIES) <= places


async def test_mock_proposer_returns_nothing(db_session):
    assert settings.llm_enabled is False
    assert await propose(db_session) == []


@pytest.fixture
async def context(db_session):
    db_session.add_all([
        Entity(slug="miesbach", kind="place", name="Miesbach", aliases=["Stadt Miesbach"], seeded=True),
        Entity(slug="weyarn", kind="place", name="Weyarn", aliases=[], seeded=True),
    ])
    src = Source(slug="lk-presse", name="Landratsamt", layer="landkreis", authority="high", scope="landkreis",
                 method="rss", url="https://www.landkreis-miesbach.de/rss", places=["Stadt Miesbach"], collect=True)
    off = Source(slug="tot", name="Tot", layer="medien", authority="low", scope="landkreis", method="rss",
                 url="https://tot.test/rss", collect=False)
    db_session.add_all([src, off])
    await db_session.flush()
    now = utcnow()
    db_session.add_all([
        SourceSuggestion(url="https://abgelehnt.test/x", name="Abgelehnt", layer="gemeinden", scope="gemeinde",
                         rationale_de="r", rationale_en="r", model="mock", status="declined",
                         suggested_at=now, adopt_after=now + timedelta(days=7)),
        Question(id="q01", sort=1, title_de="Verlieren die Gemeinden ihren Spielraum?", title_en="Room?",
                 driver_de="d", driver_en="d", sources_de="s", for_label_de="f", for_label_en="f", for_de="f",
                 for_en="f", against_label_de="a", against_label_en="a", against_de="a", against_en="a"),
        Signal(source_id=src.id, headline_de="Kreistag erhöht die Kreisumlage", headline_en="Levy up",
               signal_type="budget", is_founder=True, published_at=now),
        Signal(source_id=src.id, headline_de="Nur eine Korroboration", headline_en="c",
               signal_type="budget", is_founder=False, published_at=now),
    ])
    await db_session.commit()
    return db_session


async def test_prompt_names_gaps_questions_headlines_and_known_urls(context):
    system, user = await build_prompt(context)
    assert "web search" in system.lower() or "web_search" in system.lower()
    # Coverage per layer, collected sources only: landkreis 1, medien 0 (the uncollected one does not count).
    assert "landkreis: 1" in user and "medien: 0" in user
    # Per municipality, through aliases; zero-count ones named.
    assert "Miesbach: 1" in user
    zero_line = next(line for line in user.splitlines() if line.startswith("Municipalities with NO collected source"))
    assert "Weyarn" in zero_line and "Miesbach" not in zero_line
    assert "Verlieren die Gemeinden ihren Spielraum?" in user
    assert "Kreistag erhöht die Kreisumlage" in user and "Nur eine Korroboration" not in user
    # Known URLs include the declined suggestion and the catalogue's sources.
    assert "https://abgelehnt.test/x" in user and "https://www.landkreis-miesbach.de/rss" in user


class _FakeMessages:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _block(type_, **kw):
    return SimpleNamespace(type=type_, **kw)


@pytest.fixture
def live(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-test-not-used")

    def install(responses):
        fake = _FakeMessages(responses)
        monkeypatch.setattr(discover, "client", lambda: SimpleNamespace(messages=fake))
        return fake

    return install


async def test_live_call_resumes_pause_turn_and_reads_the_last_text_block(context, live):
    import json

    paused = SimpleNamespace(stop_reason="pause_turn", content=[_block("server_tool_use", id="s1", name="web_search")])
    done = SimpleNamespace(stop_reason="end_turn", content=[
        _block("thinking", thinking=""),
        _block("server_tool_use", id="s2", name="web_search"),
        _block("web_search_tool_result", content=[]),
        _block("code_execution_tool_result", content={}),
        _block("text", text="Ich habe gesucht."),
        _block("text", text=json.dumps({"candidates": [_cand(places=["weyarn", "Mond"])]})),
    ])
    fake = live([paused, done])
    out = await propose(context)
    assert [(c.url, c.places) for c in out] == [("https://www.weyarn.de/aktuelles", ["Weyarn"])]
    first, second = fake.calls
    assert first["model"] == settings.suggest_model and first["max_tokens"] == 8000
    tool = first["tools"][0]
    assert tool["type"] == settings.suggest_web_search_tool and tool["name"] == "web_search"
    assert tool["max_uses"] == settings.suggest_web_search_max_uses
    assert tool["user_location"]["city"] == "Miesbach" and tool["user_location"]["country"] == "DE"
    assert first["output_config"]["format"] == {"type": "json_schema", "schema": SCHEMA}
    # The continuation re-sends the paused assistant turn, without an extra user message.
    assert second["messages"][-1] == {"role": "assistant", "content": paused.content}
    assert [m["role"] for m in second["messages"]] == ["user", "assistant"]


async def test_endless_pause_turn_gives_up_after_two_continuations(context, live):
    from mhs.llm.client import LLMEmptyCompletion

    paused = SimpleNamespace(stop_reason="pause_turn", content=[_block("server_tool_use", id="s", name="web_search")])
    fake = live([paused, paused, paused, paused])
    with pytest.raises(LLMEmptyCompletion):
        await propose(context)
    assert len(fake.calls) == 3


async def test_refusal_yields_no_candidates(context, live):
    live([SimpleNamespace(stop_reason="refusal", content=[])])
    assert await propose(context) == []


def _status_error(cls, code):
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return cls("boom", response=httpx.Response(code, request=req), body=None)


async def test_api_errors_map_to_the_llm_error_classes(context, live):
    live([_status_error(anthropic.BadRequestError, 400)])
    with pytest.raises(LLMRequestError):
        await propose(context)
    live([_status_error(anthropic.AuthenticationError, 401)])
    with pytest.raises(LLMAuthError):
        await propose(context)
