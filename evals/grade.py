"""Grading primitives for both headline claims.

Pure functions, no model calls — so grading logic is unit-tested independently of
any live run, and the same code grades dry-run and live results identically.
"""
from __future__ import annotations

import re
import string

_PUNCT = string.punctuation + " "


def normalize_text(s: str) -> str:
    return re.sub(r"\s+", " ", str(s).strip().lower()).strip(_PUNCT)


def routing_correct(gold: str, text: str) -> bool:
    """True if the gold answer appears in the model's response (normalized).

    Also matches whitespace-insensitively so list/number answers like
    ``[2, 5, 8]`` grade correctly regardless of spacing.
    """
    g, t = normalize_text(gold), normalize_text(text)
    if not g:
        return False
    if g in t:
        return True
    return g.replace(" ", "") in t.replace(" ", "")


def fp_rate(clean_flags: list[bool]) -> float:
    """Fraction of clean snippets that were (wrongly) flagged with any finding."""
    return sum(1 for f in clean_flags if f) / len(clean_flags) if clean_flags else 0.0


def recall(detect_flags: list[bool]) -> float:
    """Fraction of buggy snippets whose seeded bug was detected among kept findings."""
    return sum(1 for f in detect_flags if f) / len(detect_flags) if detect_flags else 0.0


def bug_detected(kept_lines: list[int], bug_line: int, tol: int = 2) -> bool:
    return any(abs(int(ln) - int(bug_line)) <= tol for ln in kept_lines)


def bootstrap_ci(flags: list[bool], *, iters: int = 2000, seed: int = 0,
                 alpha: float = 0.05) -> tuple[float, float]:
    """Percentile bootstrap CI for the mean of a 0/1 list. Seeded for reproducibility."""
    import random
    if not flags:
        return (0.0, 0.0)
    rng = random.Random(seed)
    n = len(flags)
    means = sorted(sum(flags[rng.randrange(n)] for _ in range(n)) / n for _ in range(iters))
    lo = means[int((alpha / 2) * iters)]
    hi = means[min(iters - 1, int((1 - alpha / 2) * iters))]
    return (round(lo, 4), round(hi, 4))
