"""Global LLM concurrency controls.

Provides a process‑wide semaphore to bound simultaneous outbound LLM API calls.
Configured by env var LLM_MAX_CONCURRENT (default: 4). Minimum enforced: 1.

Usage:
    from tradingagents.utils.concurrency import llm_call

    with llm_call():
        # perform one LLM API request

The context manager acquires the shared semaphore and releases it afterward,
ensuring fairness (FIFO-ish) across threads.
"""
from __future__ import annotations
import os
import threading
from contextlib import contextmanager

__all__ = ["llm_call", "set_max_concurrent", "get_max_concurrent"]

_lock = threading.Lock()
_semaphore = None  # lazily created so tests can reconfigure
_max_concurrent = None


def _init_if_needed():
    global _semaphore, _max_concurrent
    if _semaphore is None:
        # Read once; allow tests to override via set_max_concurrent
        raw = os.getenv("LLM_MAX_CONCURRENT", "4")
        try:
            value = int(raw)
        except ValueError:
            value = 4
        if value < 1:
            value = 1
        _max_concurrent = value
        _semaphore = threading.Semaphore(value)


def set_max_concurrent(n: int):
    """Reconfigure the semaphore capacity (mainly for tests)."""
    if n < 1:
        n = 1
    global _semaphore, _max_concurrent
    with _lock:
        _max_concurrent = n
        _semaphore = threading.Semaphore(n)


def get_max_concurrent() -> int:
    _init_if_needed()
    return _max_concurrent  # type: ignore


@contextmanager
def llm_call():
    """Context manager wrapping a single outbound LLM call.

    Example:
        with llm_call():
            client.chat.completions.create(...)
    """
    _init_if_needed()
    assert _semaphore is not None
    _semaphore.acquire()
    try:
        yield
    finally:
        _semaphore.release()
