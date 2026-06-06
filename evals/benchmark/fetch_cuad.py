"""Acquire CUAD_v1.json (CC BY 4.0) at eval time — keeps raw commercial contract
text OUT of this public repo while staying fully reproducible.

Source: HuggingFace `theatticusproject/cuad` (mirror of the Atticus GitHub release).
The file is pinned by sha256; a mismatch aborts loudly (never grade against a
silently-changed dataset). Only the held-out gold LABEL json (offsets, no raw
text) is committed; this script reconstitutes the raw text locally.

Usage:  python evals/benchmark/fetch_cuad.py
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import httpx

URL = "https://huggingface.co/datasets/theatticusproject/cuad/resolve/main/CUAD_v1/CUAD_v1.json"
# Pinned at acquisition (2026-06-06). Verified non-empty + SQuAD-shaped before pinning.
EXPECTED_SHA256 = "ed0b77d85bdf4014d7495800e8e4a70565b48ee6f8a2e5dca9cf8655dbf10eae"
DEST = Path(__file__).parent / "raw" / "CUAD_v1.json"


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    DEST.parent.mkdir(parents=True, exist_ok=True)
    if DEST.exists():
        digest = sha256_of(DEST)
        if EXPECTED_SHA256 in ("PIN_AFTER_FIRST_FETCH", digest):
            print(f"CUAD already present: {DEST} ({DEST.stat().st_size} bytes, sha256={digest[:16]}…)")
            return 0
        print(f"WARNING: existing CUAD sha256 mismatch ({digest[:16]}…) — re-downloading", file=sys.stderr)
    print(f"Downloading CUAD_v1.json from {URL} …")
    with httpx.stream("GET", URL, follow_redirects=True, timeout=120.0) as r:
        r.raise_for_status()
        with DEST.open("wb") as f:
            for chunk in r.iter_bytes(1 << 20):
                f.write(chunk)
    digest = sha256_of(DEST)
    print(f"Downloaded {DEST} ({DEST.stat().st_size} bytes)")
    print(f"sha256 = {digest}")
    if EXPECTED_SHA256 not in ("PIN_AFTER_FIRST_FETCH", digest):
        print(f"ERROR: sha256 mismatch — expected {EXPECTED_SHA256}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
