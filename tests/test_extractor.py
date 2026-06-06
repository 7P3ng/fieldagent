"""Extractor: focused taxonomy extraction per chunk via the ModelClient seam.

Uses FakeClient (zero paid calls). Asserts model quotes map to correct GLOBAL
offsets and that malformed model output degrades gracefully (no crash, no fake
findings).
"""
from __future__ import annotations

import json

from core.model_client import FakeClient
from fieldagent.chunker import chunk_text
from fieldagent.extractor import extract_chunk, locate_span


def _responder(payload):
    return lambda model, system, messages, max_tokens: json.dumps(payload)


def test_locate_span_exact():
    text = "Alpha beta gamma delta."
    assert locate_span(text, "beta gamma") == (6, 16)


def test_locate_span_whitespace_tolerant():
    text = "The   liability  shall\n  not exceed fees."
    span = locate_span(text, "liability shall not exceed")
    assert span is not None
    s, e = span
    # located region, when whitespace-normalized, equals the needle
    assert " ".join(text[s:e].split()) == "liability shall not exceed"


def test_locate_span_missing_returns_none():
    assert locate_span("hello world", "nonexistent phrase") is None


def test_extract_maps_quote_to_global_offset():
    full = "PADDING. " * 100 + "Either party may terminate for convenience on 30 days notice."
    chunks = chunk_text(full, window=400, overlap=80)
    target_chunk = next(c for c in chunks if "terminate for convenience" in c.text)
    payload = {"findings": [{
        "clause_type": "Termination For Convenience",
        "quote": "terminate for convenience on 30 days notice",
        "why": "either party may exit at will",
    }]}
    client = FakeClient(_responder(payload))
    cands = extract_chunk(client, target_chunk, model="deepseek-chat")
    assert len(cands) == 1
    c = cands[0]
    assert c.clause_type == "Termination For Convenience"
    # global offset points at the real location in the FULL document
    assert full[c.start:c.end] == "terminate for convenience on 30 days notice"


def test_unknown_clause_type_skipped():
    chunk = chunk_text("some contract text here", window=400, overlap=80)[0]
    payload = {"findings": [{"clause_type": "Not A Real Type", "quote": "contract", "why": "x"}]}
    client = FakeClient(_responder(payload))
    assert extract_chunk(client, chunk, model="deepseek-chat") == []


def test_malformed_json_yields_no_candidates():
    chunk = chunk_text("contract text", window=400, overlap=80)[0]
    client = FakeClient(lambda m, s, msg, mt: "I think there are no clauses here, sorry!")
    assert extract_chunk(client, chunk, model="deepseek-chat") == []


def test_unlocatable_quote_skipped():
    chunk = chunk_text("real contract text about widgets", window=400, overlap=80)[0]
    payload = {"findings": [{"clause_type": "Exclusivity", "quote": "totally absent phrase", "why": "x"}]}
    client = FakeClient(_responder(payload))
    assert extract_chunk(client, chunk, model="deepseek-chat") == []
