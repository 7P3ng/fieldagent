"""Structured tracing — the observability spine.

Every agent call runs inside a ``span``: a node in a run's tree that records the
model, tier decision, tokens, cost, latency, retries, and outcome. Spans persist
to SQLite (queryable; the UI reads it back). A span that exits via exception is
recorded as FAILED with its error message, then the exception re-raises so the
orchestrator can decide whether the *run* degrades or fails.

Thread-safe for the orchestrator's fan-out: a lock guards writes and
``check_same_thread=False`` lets pooled worker threads share one store.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from core.types import ModelResponse, RunOutcome, Tier

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    label TEXT,
    created_at REAL
);
CREATE TABLE IF NOT EXISTS spans (
    id TEXT PRIMARY KEY,
    run_id TEXT,
    parent_id TEXT,
    name TEXT,
    model TEXT,
    tier INTEGER,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    cost_usd REAL DEFAULT 0.0,
    latency_ms REAL DEFAULT 0.0,
    outcome TEXT,
    retries INTEGER DEFAULT 0,
    error TEXT,
    started_at REAL,
    ended_at REAL,
    attrs_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_spans_run ON spans(run_id);
"""


class Span:
    """A single traced operation. Populated via :meth:`record` / :meth:`record_response`."""

    def __init__(self, span_id: str, run_id: str, name: str, parent_id: str | None) -> None:
        self.id = span_id
        self.run_id = run_id
        self.name = name
        self.parent_id = parent_id
        self.model: str | None = None
        self.tier: int | None = None
        self.input_tokens = 0
        self.output_tokens = 0
        self.cost_usd = 0.0
        self.latency_ms = 0.0
        self.retries = 0
        self.outcome = RunOutcome.OK
        self.error: str | None = None
        self.attrs: dict[str, Any] = {}
        self.started_at = 0.0
        self.ended_at = 0.0
        self._latency_set = False

    def record(self, *, input_tokens: int = 0, output_tokens: int = 0,
               cost_usd: float = 0.0, outcome: RunOutcome | None = None,
               retries: int | None = None, error: str | None = None,
               model: str | None = None, tier: Tier | None = None) -> None:
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.cost_usd += cost_usd
        if outcome is not None:
            self.outcome = outcome
        if retries is not None:
            self.retries = retries
        if error is not None:
            self.error = error
        if model is not None:
            self.model = model
        if tier is not None:
            self.tier = int(tier)

    def record_response(self, resp: ModelResponse, *, retries: int = 0) -> None:
        self.model = resp.model
        if resp.tier is not None:
            self.tier = int(resp.tier)
        self.input_tokens += resp.input_tokens
        self.output_tokens += resp.output_tokens
        self.cost_usd += resp.cost_usd
        self.latency_ms += resp.latency_ms
        self._latency_set = True
        self.retries = retries

    def set(self, **attrs: Any) -> None:
        self.attrs.update(attrs)


class TraceStore:
    def __init__(self, path: str = "traces.db") -> None:
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    def new_run(self, label: str | None = None) -> str:
        run_id = uuid.uuid4().hex
        with self._lock:
            self._conn.execute(
                "INSERT INTO runs(run_id, label, created_at) VALUES (?,?,?)",
                (run_id, label, time.time()),
            )
            self._conn.commit()
        return run_id

    @contextmanager
    def span(self, name: str, *, run_id: str, parent: str | None = None,
             model: str | None = None, tier: Tier | None = None) -> Iterator[Span]:
        sp = Span(uuid.uuid4().hex, run_id, name, parent)
        if model is not None:
            sp.model = model
        if tier is not None:
            sp.tier = int(tier)
        sp.started_at = time.time()
        clock = time.perf_counter()
        try:
            yield sp
        except BaseException as exc:  # record failure, then re-raise
            sp.outcome = RunOutcome.FAILED
            sp.error = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            sp.ended_at = time.time()
            if not sp._latency_set:
                sp.latency_ms = (time.perf_counter() - clock) * 1000.0
            self._write(sp)

    def _write(self, sp: Span) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT OR REPLACE INTO spans
                   (id, run_id, parent_id, name, model, tier, input_tokens,
                    output_tokens, cost_usd, latency_ms, outcome, retries, error,
                    started_at, ended_at, attrs_json)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (sp.id, sp.run_id, sp.parent_id, sp.name, sp.model, sp.tier,
                 sp.input_tokens, sp.output_tokens, sp.cost_usd, sp.latency_ms,
                 sp.outcome.value, sp.retries, sp.error, sp.started_at, sp.ended_at,
                 json.dumps(sp.attrs)),
            )
            self._conn.commit()

    def query(self, run_id: str) -> list[dict[str, Any]]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM spans WHERE run_id=? ORDER BY started_at ASC", (run_id,))
            rows = [dict(r) for r in cur.fetchall()]
        for r in rows:
            r["attrs"] = json.loads(r.pop("attrs_json") or "{}")
        return rows

    def query_runs(self) -> list[dict[str, Any]]:
        with self._lock:
            cur = self._conn.execute(
                """SELECT r.run_id, r.label, r.created_at,
                          COUNT(s.id) AS span_count,
                          COALESCE(SUM(s.cost_usd),0) AS total_cost_usd,
                          COALESCE(SUM(s.input_tokens+s.output_tokens),0) AS total_tokens,
                          MAX(CASE WHEN s.outcome='failed' THEN 1 ELSE 0 END) AS had_failure
                   FROM runs r LEFT JOIN spans s ON s.run_id=r.run_id
                   GROUP BY r.run_id ORDER BY r.created_at DESC""")
            return [dict(r) for r in cur.fetchall()]

    def close(self) -> None:
        self._conn.close()
