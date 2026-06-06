"""Real DeepSeek client (OpenAI-compatible chat completions over httpx).

Reads OSSLLM_API_KEY / OSSLLM_MODEL / OSSLLM_BASE_URL from env only. DeepSeek is
tier-0 of the router. Costs are priced under the canonical ``deepseek-chat``
entry regardless of the concrete model id, so the pricing table stays the single
source of truth.
"""
from __future__ import annotations

import os
from time import perf_counter

import httpx

from core.pricing import cost
from core.types import ModelError, ModelResponse, RateLimitError

_CANONICAL = "deepseek-chat"


class DeepSeekClient:
    def __init__(self, api_key: str | None = None, base_url: str | None = None,
                 model: str | None = None, timeout: float = 120.0) -> None:
        key = api_key or os.environ.get("OSSLLM_API_KEY")
        if not key:
            raise RuntimeError(
                "OSSLLM_API_KEY is not set. Source your DeepSeek env file "
                "(e.g. `source /etc/skill-tuning/skill-tuning.env`) before live runs."
            )
        self._key = key
        # This VPS sets OSSLLM_URL (no /v1 suffix); fall back to OSSLLM_BASE_URL,
        # then the public default. DeepSeek accepts {base}/chat/completions for both
        # https://api.deepseek.com and https://api.deepseek.com/v1.
        self._base = (base_url or os.environ.get("OSSLLM_URL")
                      or os.environ.get("OSSLLM_BASE_URL")
                      or "https://api.deepseek.com/v1").rstrip("/")
        self._model = model or os.environ.get("OSSLLM_MODEL") or _CANONICAL
        self._timeout = timeout

    def complete(self, *, model, system, messages, max_tokens) -> ModelResponse:
        payload = {
            "model": self._model,
            "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system}, *messages],
            "stream": False,
        }
        t0 = perf_counter()
        try:
            r = httpx.post(
                f"{self._base}/chat/completions",
                headers={"Authorization": f"Bearer {self._key}",
                         "Content-Type": "application/json"},
                json=payload, timeout=self._timeout,
            )
        except httpx.HTTPError as exc:
            raise ModelError(f"deepseek transport error: {exc}") from exc
        latency = (perf_counter() - t0) * 1000.0
        if r.status_code == 429:
            raise RateLimitError(f"deepseek 429: {r.text[:200]}")
        if r.status_code >= 400:
            raise ModelError(f"deepseek {r.status_code}: {r.text[:300]}")
        data = r.json()
        choice = data["choices"][0]
        text = choice["message"]["content"] or ""
        usage = data.get("usage", {})
        in_tok = int(usage.get("prompt_tokens", 0))
        out_tok = int(usage.get("completion_tokens", 0))
        return ModelResponse(
            text=text, model=_CANONICAL, input_tokens=in_tok, output_tokens=out_tok,
            cost_usd=cost(_CANONICAL, in_tok, out_tok), latency_ms=latency,
            stop_reason=choice.get("finish_reason", "stop"),
        )
