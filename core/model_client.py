"""The model-client seam — the keystone that makes the whole kernel testable.

Every component (router, orchestrator, pipeline, evals) talks to models *only*
through the ``ModelClient`` protocol. In tests and dry-run evals we inject
``FakeClient`` / ``RecordedClient`` so not a single paid call happens; in
production the real ``AnthropicClient`` / ``DeepSeekClient`` implement the same
three-argument ``complete(...)`` shape.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from typing import Any, Protocol, runtime_checkable

from core.pricing import cost
from core.types import ModelResponse, Tier


def estimate_tokens(text: str) -> int:
    """Cheap, provider-agnostic token estimate (~4 chars/token). >=1."""
    return max(1, len(text) // 4)


def prompt_key(model: str, system: str, messages: list[dict[str, Any]]) -> str:
    """Stable content hash identifying a call — the fixture/cache key."""
    blob = json.dumps(
        {"model": model, "system": system, "messages": messages},
        sort_keys=True, ensure_ascii=False,
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


@runtime_checkable
class ModelClient(Protocol):
    def complete(
        self, *, model: str, system: str,
        messages: list[dict[str, Any]], max_tokens: int,
    ) -> ModelResponse:
        ...


class FakeClient:
    """Deterministic in-memory client. ``responder`` maps inputs -> output text.

    Token counts are estimated from the prompt/response text and priced through
    the real pricing table, so cost arithmetic is exercised end-to-end in tests.
    """

    def __init__(
        self,
        responder: Callable[[str, str, list[dict[str, Any]], int], str],
        *, latency_ms: float = 1.0, tier: Tier | None = None,
    ) -> None:
        self._responder = responder
        self._latency_ms = latency_ms
        self._tier = tier

    def complete(self, *, model, system, messages, max_tokens) -> ModelResponse:
        text = self._responder(model, system, messages, max_tokens)
        prompt_text = system + "".join(str(m.get("content", "")) for m in messages)
        in_tok = estimate_tokens(prompt_text)
        out_tok = estimate_tokens(text)
        return ModelResponse(
            text=text, model=model, input_tokens=in_tok, output_tokens=out_tok,
            cost_usd=cost(model, in_tok, out_tok), latency_ms=self._latency_ms,
            tier=self._tier,
        )


class RecordedClient:
    """Replays previously recorded responses keyed by :func:`prompt_key`.

    Used for zero-cost dry-run evals. ``strict=True`` (default) raises on a cache
    miss — a dry run must never silently fall back to a live or empty response.
    """

    def __init__(self, fixtures: dict[str, dict[str, Any]], *, strict: bool = True) -> None:
        self._fixtures = fixtures
        self._strict = strict
        self.hits = 0
        self.misses = 0

    def complete(self, *, model, system, messages, max_tokens) -> ModelResponse:
        key = prompt_key(model, system, messages)
        if key not in self._fixtures:
            self.misses += 1
            if self._strict:
                raise KeyError(
                    f"no recorded fixture for call (model={model}, key={key[:12]}…). "
                    "Re-record fixtures or run with live keys."
                )
            return ModelResponse(text="", model=model, input_tokens=0,
                                 output_tokens=0, cost_usd=0.0, latency_ms=0.0)
        self.hits += 1
        f = self._fixtures[key]
        in_tok = int(f.get("input_tokens", 0))
        out_tok = int(f.get("output_tokens", 0))
        return ModelResponse(
            text=f["text"], model=f.get("model", model),
            input_tokens=in_tok, output_tokens=out_tok,
            cost_usd=cost(f.get("model", model), in_tok, out_tok),
            latency_ms=float(f.get("latency_ms", 0.0)),
            stop_reason=f.get("stop_reason", "stop"),
        )
