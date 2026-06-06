"""Per-model token pricing.

Public list prices in USD per million tokens (MTok), as of 2026-06.
These are configuration, not measurements — edit the table if prices move.
Unknown models raise ``KeyError`` on purpose: silently pricing an unknown
model at $0 would corrupt every cost number downstream (fail loud).
"""
from __future__ import annotations

# model_id -> (input_$_per_MTok, output_$_per_MTok)
PRICING: dict[str, tuple[float, float]] = {
    "claude-opus-4-8": (15.0, 75.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5-20251001": (1.0, 5.0),
    "deepseek-chat": (0.27, 1.10),
}

_MTOK = 1_000_000


def cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """USD cost of a call. Raises KeyError for an unpriced model (fail loud)."""
    in_price, out_price = PRICING[model]
    return (input_tokens / _MTOK) * in_price + (output_tokens / _MTOK) * out_price
