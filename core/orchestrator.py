"""Orchestration primitives: parallel fan-out, retry with backoff, idempotency.

Deliberately thread-based (not asyncio) so it composes with synchronous model
SDKs and stays trivial to test. The design rule encoded here: *one agent failing
must not fail the run*. ``fan_out`` degrades a failed item to ``None`` and keeps
going; the caller decides whether a degraded run is still useful.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any, TypeVar

T = TypeVar("T")
R = TypeVar("R")


def fan_out(
    items: list[T],
    fn: Callable[[T], R],
    *, max_concurrency: int = 8,
    on_error: Callable[[T, Exception], None] | None = None,
) -> list[R | None]:
    """Run ``fn`` over ``items`` concurrently. Results are returned in input order.

    A failing item yields ``None`` (graceful degradation) and the rest proceed.
    ``on_error(item, exc)`` is invoked for observability if supplied.
    """
    if not items:
        return []
    results: list[R | None] = [None] * len(items)

    def _run(idx_item):
        idx, item = idx_item
        try:
            results[idx] = fn(item)
        except Exception as exc:  # degrade, don't crash the run
            if on_error is not None:
                on_error(item, exc)
            results[idx] = None

    workers = max(1, min(max_concurrency, len(items)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(_run, enumerate(items)))
    return results


def retry(
    fn: Callable[[], R],
    *, attempts: int = 3, backoff: float = 0.5,
    exceptions: tuple[type[BaseException], ...] = (Exception,),
) -> R:
    """Call ``fn`` up to ``attempts`` times with exponential backoff. Re-raises last."""
    last: BaseException | None = None
    for i in range(attempts):
        try:
            return fn()
        except exceptions as exc:
            last = exc
            if i < attempts - 1 and backoff > 0:
                time.sleep(backoff * (2 ** i))
    assert last is not None
    raise last


def memoize(*, key: Callable[..., Any]):
    """Idempotency decorator: cache results by ``key(*args, **kwargs)``."""
    def deco(fn: Callable[..., R]) -> Callable[..., R]:
        cache: dict[Any, R] = {}

        def wrapper(*args, **kwargs) -> R:
            k = key(*args, **kwargs)
            if k not in cache:
                cache[k] = fn(*args, **kwargs)
            return cache[k]

        wrapper.cache = cache  # type: ignore[attr-defined]
        return wrapper
    return deco


def pipeline(value: Any, *stages: Callable[[Any], Any]) -> Any:
    """Thread ``value`` through ``stages`` sequentially, returning the final result."""
    for stage in stages:
        value = stage(value)
    return value
