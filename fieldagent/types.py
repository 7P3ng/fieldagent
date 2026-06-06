"""Shared dataclasses for the FieldAgent pipeline — dependency-free + serializable."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Chunk:
    """An overlapping window of a contract carrying its global char offsets."""

    index: int
    start: int   # inclusive char offset into the full contract
    end: int     # exclusive
    text: str


@dataclass
class Candidate:
    """A raw extraction before verification: a clause type + a span + a rationale."""

    clause_type: str
    quote: str
    start: int          # global char offset into the full contract (-1 if unlocatable)
    end: int
    rationale: str = ""
    chunk_index: int = -1


@dataclass
class Finding:
    """A verified, structured red flag emitted by the pipeline."""

    clause_type: str
    span_text: str
    start: int
    end: int
    severity: str        # "high" | "medium" | "low"
    risk_note: str       # plain-English "why this is risky"
    confidence: float = 1.0
    verified: bool = True
    rationale: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "clause_type": self.clause_type,
            "span_text": self.span_text,
            "start": self.start,
            "end": self.end,
            "severity": self.severity,
            "risk_note": self.risk_note,
            "confidence": round(self.confidence, 3),
            "verified": self.verified,
            "rationale": self.rationale,
            **({"meta": self.meta} if self.meta else {}),
        }
