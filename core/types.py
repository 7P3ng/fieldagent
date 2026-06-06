"""Core data types shared across the kernel and pipelines.

Kept dependency-free and dataclass-based so the whole spine is trivial to
construct in tests and serialize into traces.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any


class Tier(enum.IntEnum):
    """Model tiers ordered cheapest -> most capable.

    IntEnum so ``Tier.HAIKU < Tier.SONNET`` is the cost/capability ordering the
    router escalates along. The canonical model id per tier is used for pricing
    and trace display; the live DeepSeek model id can be overridden via env.
    """

    DEEPSEEK = 0
    HAIKU = 1
    SONNET = 2
    OPUS = 3

    @property
    def model_id(self) -> str:
        return _TIER_MODEL[self]

    @classmethod
    def from_name(cls, name: str) -> Tier:
        return cls[name.strip().upper()]


# Canonical model id per tier (current model family as of 2026-06).
_TIER_MODEL: dict[Tier, str] = {
    Tier.DEEPSEEK: "deepseek-chat",
    Tier.HAIKU: "claude-haiku-4-5-20251001",
    Tier.SONNET: "claude-sonnet-4-6",
    Tier.OPUS: "claude-opus-4-8",
}


class RunOutcome(str, enum.Enum):
    OK = "ok"
    DEGRADED = "degraded"   # something failed but the run produced a usable result
    FAILED = "failed"       # the run could not produce a result


@dataclass(frozen=True)
class ModelResponse:
    """The normalized result of one model call, regardless of provider."""

    text: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: float
    stop_reason: str = "stop"
    tier: Tier | None = None


@dataclass
class Task:
    """A unit of work the router tiers and (optionally) the eval harness grades."""

    id: str
    kind: str                       # e.g. "qa", "transform", "code", "find_bugs"
    prompt: str
    difficulty: int = 1             # 1 (trivial) .. 5 (hard) — drives routing
    gold: Any = None                # gold answer for eval grading (optional)
    meta: dict[str, Any] = field(default_factory=dict)


class ModelError(RuntimeError):
    """Generic, retryable model/provider error."""


class RateLimitError(ModelError):
    """Provider signalled rate limiting (429) — triggers fallback/backoff."""
