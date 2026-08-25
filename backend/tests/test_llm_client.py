"""The two production failure modes: empty completions and refusals."""
import pytest

from rns.llm import client as llm


class _Block:
    def __init__(self, text):
        self.type, self.text = "text", text


class _Msg:
    def __init__(self, blocks, stop_reason="end_turn"):
        self.content, self.stop_reason = blocks, stop_reason


class _FakeMessages:
    def __init__(self, script):
        self.script, self.calls = list(script), []

    async def create(self, **kw):
        self.calls.append(kw["model"])
        return self.script.pop(0)


class _FakeClient:
    def __init__(self, script):
        self.messages = _FakeMessages(script)


async def test_empty_completion_is_retried_then_falls_back(monkeypatch):
    # Wrong: return "" and let the caller json.loads it.
    fake = _FakeClient([_Msg([]), _Msg([]), _Msg([]), _Msg([_Block('{"ok": true}')])])
    monkeypatch.setattr(llm, "client", lambda: fake)
    out = await llm.complete_json(model="a", system="s", user="u", schema={"type": "object"},
                                  fallback_model="b", attempts=3)
    assert out == {"ok": True}
    assert fake.messages.calls == ["a", "a", "a", "b"]


async def test_refusal_moves_to_fallback_without_burning_attempts(monkeypatch):
    fake = _FakeClient([_Msg([], stop_reason="refusal"), _Msg([_Block('{"ok": 1}')])])
    monkeypatch.setattr(llm, "client", lambda: fake)
    out = await llm.complete_json(model="a", system="s", user="u", schema={"type": "object"},
                                  fallback_model="b", attempts=3)
    assert out == {"ok": 1} and fake.messages.calls == ["a", "b"]


async def test_all_empty_raises(monkeypatch):
    fake = _FakeClient([_Msg([]), _Msg([])])
    monkeypatch.setattr(llm, "client", lambda: fake)
    with pytest.raises(llm.LLMEmptyCompletion):
        await llm.complete_json(model="a", system="s", user="u", schema={"type": "object"}, attempts=2)
