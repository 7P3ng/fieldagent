"""Real Anthropic client. Reads ANTHROPIC_API_KEY from env only (public repo).

Fails loud if the key is absent — a silent fallback would corrupt the routing
eval's cost numbers. Maps provider rate-limits to ``RateLimitError`` so the
router's fallback ladder engages.
"""
from __future__ import annotations

import os
from time import perf_counter

from core.pricing import cost
from core.types import ModelError, ModelResponse, RateLimitError


class AnthropicClient:
    def __init__(self, api_key: str | None = None) -> None:
        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. Export it (export ANTHROPIC_API_KEY=sk-ant-...) "
                "before running live evals or the live pipeline."
            )
        import anthropic  # imported lazily so dry-run paths need no SDK
        self._anthropic = anthropic
        self._client = anthropic.Anthropic(api_key=key)

    def complete(self, *, model, system, messages, max_tokens) -> ModelResponse:
        t0 = perf_counter()
        try:
            resp = self._client.messages.create(
                model=model, system=system, max_tokens=max_tokens, messages=messages,
            )
        except self._anthropic.RateLimitError as exc:
            raise RateLimitError(str(exc)) from exc
        except self._anthropic.APIError as exc:
            raise ModelError(str(exc)) from exc
        latency = (perf_counter() - t0) * 1000.0
        text = "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", "") == "text")
        in_tok = resp.usage.input_tokens
        out_tok = resp.usage.output_tokens
        return ModelResponse(
            text=text, model=model, input_tokens=in_tok, output_tokens=out_tok,
            cost_usd=cost(model, in_tok, out_tok), latency_ms=latency,
            stop_reason=resp.stop_reason or "stop",
        )
