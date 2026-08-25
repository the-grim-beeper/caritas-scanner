"""Anthropic access, hardened against the two failure modes that bite in production.

1. Empty completions — a syntactically fine response with no text block. Not an
   exception, so the SDK's retry never sees it. Retried here, then failed over.
2. Refusals — HTTP 200 with stop_reason="refusal". Not worth retrying on the same
   model; go straight to the fallback.

The response shape is constrained with ``output_config.format`` (structured
outputs); assistant-turn prefill returns 400 on every current model.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from anthropic import APIStatusError, AsyncAnthropic, AuthenticationError, RateLimitError

from rns.config import settings

log = logging.getLogger(__name__)


class LLMUnavailable(RuntimeError):
    """No API key configured. Callers degrade to the mock path."""


class LLMEmptyCompletion(RuntimeError):
    """No usable text after every retry and the fallback."""


class LLMAuthError(RuntimeError):
    """The key is rejected. Not retryable, not per-item: the whole batch must stop."""


_client: AsyncAnthropic | None = None


def client() -> AsyncAnthropic:
    global _client
    if not settings.llm_enabled:
        raise LLMUnavailable("ANTHROPIC_API_KEY is not set")
    if _client is None:
        _client = AsyncAnthropic(api_key=settings.anthropic_api_key, max_retries=3)
    return _client


def _first_text(message: Any) -> str | None:
    for block in getattr(message, "content", []) or []:
        if getattr(block, "type", None) == "text":
            text = (block.text or "").strip()
            if text:
                return text
    return None


async def complete_json(
    *,
    model: str,
    system: list[dict] | str,
    user: str,
    schema: dict,
    max_tokens: int = 4096,
    fallback_model: str | None = None,
    attempts: int = 3,
    effort: str | None = None,
) -> dict:
    output_config: dict[str, Any] = {"format": {"type": "json_schema", "schema": schema}}
    if effort:
        output_config["effort"] = effort
    models = [model] + ([fallback_model] if fallback_model else [])
    last_error: Exception | None = None

    for candidate in models:
        for attempt in range(1, attempts + 1):
            try:
                message = await client().messages.create(
                    model=candidate,
                    max_tokens=max_tokens,
                    system=system,
                    messages=[{"role": "user", "content": user}],
                    output_config=output_config,
                )
            except AuthenticationError as exc:
                raise LLMAuthError(str(exc)) from exc
            except RateLimitError as exc:
                last_error = exc
                await asyncio.sleep(min(2**attempt, 30))
                continue
            except APIStatusError as exc:
                last_error = exc
                if exc.status_code and exc.status_code < 500:
                    break  # a 400 does not become valid by being re-sent
                await asyncio.sleep(min(2**attempt, 30))
                continue

            if getattr(message, "stop_reason", None) == "refusal":
                log.warning("model %s refused; moving to fallback", candidate)
                last_error = LLMEmptyCompletion(f"{candidate} refused")
                break

            text = _first_text(message)
            if text is None:
                log.warning("empty completion from %s (attempt %d/%d)", candidate, attempt, attempts)
                last_error = LLMEmptyCompletion(f"{candidate} returned no text")
                continue
            try:
                return json.loads(text)
            except json.JSONDecodeError as exc:
                last_error = exc
                log.warning("unparseable JSON from %s (attempt %d): %s", candidate, attempt, exc)
                continue

    raise LLMEmptyCompletion(str(last_error) if last_error else "no completion")
