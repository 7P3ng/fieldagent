"""Risk taxonomy invariants. Keys MUST be exact CUAD labels or gold matching fails."""
from __future__ import annotations

import json
from pathlib import Path

from fieldagent.clauses import CLAUSES, RISK_TYPES, extraction_taxonomy_block

_GOLD = json.loads((Path(__file__).parent.parent / "evals/benchmark/heldout_gold.json").read_text())


def test_fifteen_risk_types():
    assert len(CLAUSES) == 15
    assert len(RISK_TYPES) == 15


def test_keys_are_exact_cuad_labels():
    # every taxonomy key must be one of the CUAD risk labels recorded in the gold file
    cuad_labels = set(_GOLD["risk_types"])
    assert set(CLAUSES.keys()) == cuad_labels


def test_every_clause_fully_specified():
    for name, c in CLAUSES.items():
        assert c.name == name
        assert c.severity in {"high", "medium", "low"}
        assert len(c.definition) > 20, f"{name} needs a real definition"
        assert len(c.risk_note) > 20, f"{name} needs a real risk note"


def test_taxonomy_block_lists_all_types():
    block = extraction_taxonomy_block()
    for name in CLAUSES:
        assert name in block
