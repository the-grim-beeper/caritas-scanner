"""scripts/check_models.py exercises every configured model the way the app does
(one structured-output call). It must never spend money without a key, and it must
fail loudly when one model fails."""
import subprocess
import sys
from pathlib import Path

from scripts import check_models

BACKEND = Path(__file__).resolve().parents[1]


def test_without_a_key_it_skips_and_exits_zero():
    # conftest forces anthropic_api_key=None in-process; run it as the user would, key unset.
    env = {"PATH": "/usr/bin:/bin", "ANTHROPIC_API_KEY": ""}
    out = subprocess.run([sys.executable, "scripts/check_models.py"], cwd=BACKEND, env=env,
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert "no key — skipped" in out.stdout


def test_one_failing_model_fails_the_check(monkeypatch, capsys):
    # Wrong: reporting only the first model, or exiting 0 because "most" models answered.
    from mhs.config import settings

    monkeypatch.setattr(settings, "anthropic_api_key", "sk-test")
    called: list[str] = []

    async def fake_complete_json(*, model, schema, **kw):
        called.append(model)
        assert "minimum" not in str(schema)
        if model == settings.judge_model:
            raise RuntimeError("403 for this account")
        return {"ok": True}

    monkeypatch.setattr(check_models, "complete_json", fake_complete_json)
    assert check_models.main() == 1
    printed = capsys.readouterr().out
    assert f"{settings.judge_model} FAIL" in printed and f"{settings.extraction_model} OK" in printed
    # Each distinct model is called once, without a fallback masking its failure.
    assert sorted(called) == sorted({settings.extraction_model, settings.judge_model, settings.digest_model,
                                     settings.digest_fallback_model})


def test_a_reply_without_ok_true_is_a_failure(monkeypatch):
    from mhs.config import settings

    monkeypatch.setattr(settings, "anthropic_api_key", "sk-test")

    async def empty(**kw):
        return {}

    monkeypatch.setattr(check_models, "complete_json", empty)
    assert check_models.main() == 1


def test_configured_models_are_the_verified_ones():
    from mhs.config import Settings

    s = Settings(_env_file=None)
    assert (s.extraction_model, s.judge_model, s.digest_model, s.digest_fallback_model) == (
        "claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5", "claude-sonnet-5-5")
