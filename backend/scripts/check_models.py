"""Exercise every configured model the way the app does: one structured-output call each.

Re-run before changing model defaults (CLAUDE.md). A model listed by models.list can
still return an empty completion or a 403 for this account; only a real call shows it.

    cd backend && .venv/bin/python scripts/check_models.py

Exit 0 when every model answers (or no key is set: "no key — skipped"), 1 otherwise.
Each model is called on its own, never with a fallback that could mask its failure."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mhs.config import settings  # noqa: E402
from mhs.llm.client import complete_json  # noqa: E402

SCHEMA = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"], "additionalProperties": False}
SYSTEM = "You are a health check. Answer with the JSON object you are asked for."
USER = 'Return {"ok": true}.'


def configured_models() -> list[str]:
    return list(dict.fromkeys([
        settings.extraction_model,
        settings.judge_model,
        settings.digest_model,
        settings.digest_fallback_model,
    ]))


async def _check(model: str) -> str | None:
    """None when the model answered as the app needs; otherwise why not."""
    try:
        payload = await complete_json(model=model, system=SYSTEM, user=USER, schema=SCHEMA, max_tokens=256,
                                      attempts=2)
    except Exception as exc:  # noqa: BLE001 — every failure is a finding, not a crash
        return f"{type(exc).__name__}: {exc}"
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        return f"unexpected reply {payload!r}"
    return None


async def _run() -> int:
    failures = 0
    for model in configured_models():
        problem = await _check(model)
        if problem is None:
            print(f"{model} OK")
        else:
            failures += 1
            print(f"{model} FAIL — {problem}")
    return 1 if failures else 0


def main() -> int:
    if not settings.llm_enabled:
        print("no key — skipped")
        return 0
    return asyncio.run(_run())


if __name__ == "__main__":
    sys.exit(main())
