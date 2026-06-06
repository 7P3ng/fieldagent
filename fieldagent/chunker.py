"""Contract -> overlapping char windows.

Commercial contracts routinely exceed a comfortable single-prompt context, and a
clause can straddle any boundary, so we window with overlap and carry each
window's *global* char offsets. Extracted spans are located within a chunk and
shifted by ``chunk.start`` back to absolute offsets, so findings always reference
positions in the original document (what the grader and the demo need).
"""
from __future__ import annotations

from fieldagent.types import Chunk


def chunk_text(text: str, *, window: int = 6000, overlap: int = 800) -> list[Chunk]:
    """Split ``text`` into overlapping ``[start, end)`` windows.

    - ``window`` chars per chunk, consecutive chunks overlapping by ``overlap``
      so a clause spanning a boundary is wholly present in at least one chunk.
    - Returns ``[]`` for empty text; a single chunk for text shorter than a window.
    """
    if not text:
        return []
    if overlap < 0 or overlap >= window:
        raise ValueError("overlap must satisfy 0 <= overlap < window")
    n = len(text)
    if n <= window:
        return [Chunk(index=0, start=0, end=n, text=text)]
    step = window - overlap
    chunks: list[Chunk] = []
    start = 0
    idx = 0
    while start < n:
        end = min(start + window, n)
        chunks.append(Chunk(index=idx, start=start, end=end, text=text[start:end]))
        if end == n:
            break
        start += step
        idx += 1
    return chunks
