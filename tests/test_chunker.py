"""Overlapping char-window chunker. Spans must reconstruct via global offsets."""
from __future__ import annotations

from fieldagent.chunker import chunk_text


def test_short_doc_is_single_chunk():
    text = "A short contract."
    chunks = chunk_text(text, window=1000, overlap=100)
    assert len(chunks) == 1
    assert chunks[0].start == 0
    assert chunks[0].end == len(text)
    assert chunks[0].text == text


def test_windows_cover_all_chars():
    text = "x" * 2500
    chunks = chunk_text(text, window=1000, overlap=200)
    # union of [start,end) must cover [0, len)
    covered = set()
    for c in chunks:
        covered.update(range(c.start, c.end))
    assert covered == set(range(len(text)))


def test_overlap_between_consecutive_chunks():
    text = "y" * 2500
    chunks = chunk_text(text, window=1000, overlap=200)
    assert len(chunks) >= 3
    # consecutive chunks overlap by `overlap` (except possibly the last)
    assert chunks[1].start == chunks[0].end - 200


def test_global_offsets_reconstruct_substring():
    text = "The quick brown fox jumps over the lazy dog. " * 60
    chunks = chunk_text(text, window=400, overlap=80)
    for c in chunks:
        assert text[c.start:c.end] == c.text


def test_indices_are_sequential():
    text = "z" * 3000
    chunks = chunk_text(text, window=1000, overlap=100)
    assert [c.index for c in chunks] == list(range(len(chunks)))


def test_empty_text_yields_no_chunks():
    assert chunk_text("", window=1000, overlap=100) == []
