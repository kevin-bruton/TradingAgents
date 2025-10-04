import threading
import time
import uuid
from typing import Dict, Any, Optional, List

RUN_ID_TIME_FORMAT = "%Y-%m-%d_%H.%M.%S"


def generate_run_id(ticker: str) -> str:
    """Generate a sortable, mostly unique run id: <TICKER>--<YYYY-MM-DD_HH.MM.SS>--<shortuuid>
    Short UUID suffix protects against same‑second collisions (very unlikely but safer under bursts).
    """
    ts = time.strftime(RUN_ID_TIME_FORMAT, time.localtime())
    short = uuid.uuid4().hex[:6]
    return f"{ticker.upper()}--{ts}--{short}"  # Keep ticker uppercase for consistency


class RunManager:
    """Thread-safe in-memory registry of active & historical runs.

    NOTE: Persistence is intentionally not implemented (kept in-memory) – restarts clear history.
    """

    def __init__(self, max_parallel: int = 5):
        self._runs: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()
        self._max_parallel = max_parallel

    # ---------------------- Creation & Update ----------------------
    def create_run(self, ticker: str, results_path: str) -> str:
        with self._lock:
            active_in_progress = sum(1 for r in self._runs.values() if r["status"] in ("pending", "in_progress"))
            if active_in_progress >= self._max_parallel:
                raise RuntimeError(f"Maximum parallel run limit reached. Max: {self._max_parallel}; Already active: {active_in_progress}")
            run_id = generate_run_id(ticker)
            now = time.time()
            self._runs[run_id] = {
                "run_id": run_id,
                "ticker": ticker.upper(),
                "status": "pending",
                "overall_progress": 0,
                "execution_tree": [],
                "final_decision": None,
                "error": None,
                "created_at": now,
                "updated_at": now,
                "thread": None,
                "results_path": results_path,
                "cancellation_flag": False,
            }
            return run_id

    def set_thread(self, run_id: str, thread):
        with self._lock:
            run = self._runs.get(run_id)
            if run:
                run["thread"] = thread
                run["updated_at"] = time.time()

    def update_run(self, run_id: str, _preserve_timestamp: bool = False, **fields):
        """Update run fields.

        _preserve_timestamp: internal/testing flag – when True, do not overwrite updated_at
        allowing callers (tests) to inject synthetic timestamps for pruning logic.
        """
        with self._lock:
            run = self._runs.get(run_id)
            if not run:
                return False
            run.update(fields)
            if not _preserve_timestamp:
                run["updated_at"] = time.time()
            return True

    # ---------------------- Retrieval ----------------------
    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            run = self._runs.get(run_id)
            if not run:
                return None
            # Return a shallow copy to prevent accidental external mutation
            return dict(run)

    def list_runs(self, summary_only: bool = True) -> List[Dict[str, Any]]:
        with self._lock:
            if summary_only:
                return [
                    {
                        "run_id": r["run_id"],
                        "ticker": r["ticker"],
                        "status": r["status"],
                        "overall_progress": r["overall_progress"],
                        "created_at": r["created_at"],
                        "updated_at": r["updated_at"],
                    }
                    for r in self._runs.values()
                ]
            else:
                return [dict(r) for r in self._runs.values()]

    # ---------------------- Cancellation & Pruning ----------------------
    def cancel_run(self, run_id: str) -> bool:
        with self._lock:
            run = self._runs.get(run_id)
            if not run:
                return False
            if run["status"] in ("completed", "error", "canceled"):
                return False
            run["cancellation_flag"] = True
            run["status"] = "canceled"  # optimistic; worker will respect and finalize
            run["updated_at"] = time.time()
            return True

    def is_canceled(self, run_id: str) -> bool:
        with self._lock:
            run = self._runs.get(run_id)
            return bool(run and run.get("cancellation_flag"))

    def prune(self, max_age_hours: int = 24) -> int:
        cutoff = time.time() - max_age_hours * 3600
        removed = 0
        with self._lock:
            to_delete = [rid for rid, r in self._runs.items() if r["updated_at"] < cutoff]
            for rid in to_delete:
                del self._runs[rid]
                removed += 1
        return removed

    # ---------------------- Introspection ----------------------
    @property
    def max_parallel(self) -> int:
        return self._max_parallel

    def active_count(self) -> int:
        with self._lock:
            return sum(1 for r in self._runs.values() if r["status"] in ("pending", "in_progress"))

# Singleton pattern: module-level instance (can be imported elsewhere)
import os
_MAX = int(os.getenv("MAX_PARALLEL_RUNS", "5"))
run_manager = RunManager(max_parallel=_MAX)

__all__ = [
    "RunManager",
    "run_manager",
    "generate_run_id",
]
