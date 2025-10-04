import os
import threading
from contextlib import contextmanager
from typing import Dict, Tuple

"""Concurrency Limiter

Supports:
  - Global max concurrency (env: LLM_MAX_CONCURRENCY)
  - Per-provider (and optional provider+model) limits via env:
        LLM_PROVIDER_LIMITS="openai:3,anthropic:2,openai:gpt-4o:2"

Parsing rules:
  - Entries are comma separated.
  - Each entry is provider[:model]:limit
  - A provider+model entry overrides provider-only limit for that model.
  - If neither global nor provider limit present => unlimited (no semaphore acquired).

Usage:
    from tradingagents.utils.concurrency_limiter import limiter
    with limiter.acquire(provider="openai", model="gpt-4o"):
        ... call LLM ...

Metrics: accessible via limiter.snapshot() returning dict w/ current counts & limits.
"""

def _parse_int(val: str, default: int | None) -> int | None:
    try:
        return int(val)
    except Exception:
        return default

class ConcurrencyLimiter:
    def __init__(self):
        self._global_limit = _parse_int(os.getenv("LLM_MAX_CONCURRENCY", ""), None)
        self._provider_limits: Dict[str, int] = {}
        self._model_limits: Dict[Tuple[str, str], int] = {}
        self._locks: Dict[Tuple[str, str], threading.Semaphore] = {}
        self._provider_locks: Dict[str, threading.Semaphore] = {}
        self._global_lock: threading.Semaphore | None = None
        self._tracking_counts = {"global": 0, "providers": {}, "models": {}}
        self._mtx = threading.Lock()
        self._init_from_env()

    def _init_from_env(self):
        limits_env = os.getenv("LLM_PROVIDER_LIMITS", "").strip()
        if limits_env:
            for part in limits_env.split(','):
                if not part.strip():
                    continue
                try:
                    key, lim = part.split(':')[-2:], part.split(':')[-1]
                except Exception:
                    continue
            # Proper parse loop
            for entry in limits_env.split(','):
                e = entry.strip()
                if not e:
                    continue
                try:
                    target, limit_s = e.rsplit(':', 1)
                    limit = int(limit_s)
                except Exception:
                    continue
                if ':' in target:
                    provider, model = target.split(':', 1)
                    self._model_limits[(provider.strip(), model.strip())] = limit
                else:
                    self._provider_limits[target.strip()] = limit
        if self._global_limit and self._global_limit > 0:
            self._global_lock = threading.Semaphore(self._global_limit)

    def _get_model_semaphore(self, provider: str, model: str) -> threading.Semaphore | None:
        key = (provider, model)
        if key in self._model_limits:
            if key not in self._locks:
                self._locks[key] = threading.Semaphore(self._model_limits[key])
            return self._locks[key]
        return None

    def _get_provider_semaphore(self, provider: str) -> threading.Semaphore | None:
        if provider in self._provider_limits:
            if provider not in self._provider_locks:
                self._provider_locks[provider] = threading.Semaphore(self._provider_limits[provider])
            return self._provider_locks[provider]
        return None

    @contextmanager
    def acquire(self, provider: str | None = None, model: str | None = None):
        acquired = []
        try:
            # Order: global -> provider -> model (avoids deadlock by consistent ordering)
            if self._global_lock:
                self._global_lock.acquire()
                acquired.append(('global', None))
                with self._mtx:
                    self._tracking_counts['global'] += 1
            if provider:
                sem_p = self._get_provider_semaphore(provider)
                if sem_p:
                    sem_p.acquire()
                    acquired.append(('provider', provider))
                    with self._mtx:
                        self._tracking_counts['providers'].setdefault(provider, 0)
                        self._tracking_counts['providers'][provider] += 1
                if model:
                    sem_m = self._get_model_semaphore(provider, model)
                    if sem_m:
                        sem_m.acquire()
                        acquired.append(('model', f"{provider}:{model}"))
                        with self._mtx:
                            self._tracking_counts['models'].setdefault(f"{provider}:{model}", 0)
                            self._tracking_counts['models'][f"{provider}:{model}"] += 1
            yield
        finally:
            # Release in reverse order
            for kind, ident in reversed(acquired):
                if kind == 'model' and ident:
                    provider_model = ident
                    with self._mtx:
                        if self._tracking_counts['models'].get(provider_model, 0) > 0:
                            self._tracking_counts['models'][provider_model] -= 1
                    prov, mod = provider_model.split(':',1)
                    self._locks.get((prov, mod), threading.Semaphore(1)).release()
                elif kind == 'provider' and ident:
                    with self._mtx:
                        if self._tracking_counts['providers'].get(ident,0) > 0:
                            self._tracking_counts['providers'][ident] -= 1
                    self._provider_locks.get(ident, threading.Semaphore(1)).release()
                elif kind == 'global':
                    with self._mtx:
                        if self._tracking_counts['global'] > 0:
                            self._tracking_counts['global'] -= 1
                    if self._global_lock:
                        self._global_lock.release()

    def snapshot(self) -> dict:
        with self._mtx:
            return {
                "global_limit": self._global_limit,
                "global_in_use": self._tracking_counts['global'],
                "provider_limits": dict(self._provider_limits),
                "provider_in_use": dict(self._tracking_counts['providers']),
                "model_limits": {f"{p}:{m}": lim for (p,m), lim in self._model_limits.items()},
                "model_in_use": dict(self._tracking_counts['models']),
            }

limiter = ConcurrencyLimiter()

__all__ = ["limiter", "ConcurrencyLimiter"]
