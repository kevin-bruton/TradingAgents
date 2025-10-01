from fastapi import FastAPI, Request, Form, BackgroundTasks, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import jinja2
import markdown as md
import bleach
import os
from typing import Dict, Any
import threading
import asyncio
import time
from dotenv import load_dotenv
import re
import shutil
from pathlib import Path
from collections import deque

# Load environment variables from .env file
load_dotenv()

# Check required environment variables
required_env_vars = [
    'FINNHUB_API_KEY',
    'OPENAI_API_KEY',
    #'REDDIT_CLIENT_ID',
    #'REDDIT_CLIENT_SECRET',
    #'REDDIT_USER_AGENT'
]

missing_vars = [var for var in required_env_vars if not os.getenv(var)]
ENABLE_WS_PATCHES = True  # Always on: diff/patch optimization
ENABLE_LOG_STREAM = True  # Always on: live log streaming
ENABLE_CONTENT_PATCHES = True  # Always on: granular content diff (reports/messages)
if ENABLE_WS_PATCHES:
    # Per-run patch tracking: seq + last flattened snapshot
    _patch_state_lock = threading.Lock()
    _run_patch_state: dict[str, dict[str, Any]] = {}

    import hashlib

    def _flatten_execution_tree(tree: list) -> dict[str, dict[str, str]]:
        """Produce a flat mapping of node_id -> {status, sig} where sig is a short hash of content.
        The hash lets us detect content changes (e.g. reports/messages) in the future; for now UI only uses status.
        """
        flat: dict[str, dict[str, str]] = {}
        def _walk(items: list):
            for item in items:
                node_id = item.get("id")
                if not node_id:
                    continue
                content = item.get("content") or ""
                # Hash only first 4KB to reduce cost
                snippet = content[:4096] if isinstance(content, str) else str(content)[:4096]
                h = hashlib.sha1(snippet.encode("utf-8", errors="ignore")).hexdigest()[:8]
                flat[node_id] = {"status": item.get("status", "pending"), "sig": h}
                if item.get("children"):
                    _walk(item["children"]) 
        _walk(tree)
        return flat

    def _compute_patch(run_id: str, tree: list) -> tuple[int, list[dict]]:
        """Compute changed nodes since last snapshot for run. Returns (seq, changed_nodes).
        Each changed node is {id, status, status_icon}.
        """
        if not ENABLE_WS_PATCHES:
            return 0, []
        flat = _flatten_execution_tree(tree)
        with _patch_state_lock:
            state = _run_patch_state.get(run_id)
            if not state:
                # Register initial snapshot with seq = 0
                _run_patch_state[run_id] = {"seq": 0, "snapshot": flat}
                return 0, []  # No patch on first registration (init_run carries full snapshot)
            prev_flat = state.get("snapshot", {})
            changed = []
            for node_id, meta in flat.items():
                prev = prev_flat.get(node_id)
                if (not prev) or prev.get("status") != meta["status"] or prev.get("sig") != meta["sig"]:
                    changed.append({
                        "id": node_id,
                        "status": meta["status"],
                        "status_icon": get_status_icon(meta["status"]),
                    })
            # NOTE: We are not detecting deletions (tree static for now)
            if changed:
                new_seq = state["seq"] + 1
                state["seq"] = new_seq
                state["snapshot"] = flat
                return new_seq, changed
            else:
                return state["seq"], []

    def _register_full_snapshot(run_id: str, tree: list) -> int:
        flat = _flatten_execution_tree(tree)
        with _patch_state_lock:
            _run_patch_state[run_id] = {"seq": 0, "snapshot": flat}
        return 0

    def _refresh_snapshot(run_id: str, tree: list) -> int:
        """Refresh the stored flattened snapshot for a run WITHOUT incrementing seq.
        Used when servicing a client resync request after a detected gap.
        If run not registered yet, behaves like initial registration (seq stays 0).
        Returns current sequence number after refresh.
        """
        flat = _flatten_execution_tree(tree)
        with _patch_state_lock:
            state = _run_patch_state.get(run_id)
            if not state:
                _run_patch_state[run_id] = {"seq": 0, "snapshot": flat}
                return 0
            state["snapshot"] = flat
            return state["seq"]

    # ------------------ Content Patch (Reports / Messages) ------------------
    _content_patch_state_lock = threading.Lock()
    _content_patch_state: dict[str, dict[str, Any]] = {}

    def _compute_content_patches(run_id: str, tree: list) -> tuple[int, list[dict]]:
        """Compute granular content patches for large, frequently changing nodes (messages/report).

        Strategy:
          - Track last full content string per node.
          - If new content starts with previous content => treat as append (mode=append, text=delta).
          - Else if content changed => replace (mode=replace, content=new_full_content).
          - Ignore nodes whose content unchanged.

        Returns (seq, patches). Sequence increments only when at least one patch produced.
        """
        if not ENABLE_CONTENT_PATCHES:
            return 0, []
        # Collect candidate nodes
        candidates: list[tuple[str, str]] = []  # (id, content)
        def _walk(nodes: list):
            for n in nodes:
                nid = n.get("id")
                if not nid:
                    continue
                if isinstance(n.get("content"), str) and (nid.endswith("_messages") or nid.endswith("_report")):
                    candidates.append((nid, n.get("content") or ""))
                if n.get("children"):
                    _walk(n["children"])
        _walk(tree)
        with _content_patch_state_lock:
            state = _content_patch_state.get(run_id)
            if not state:
                # First registration: store snapshot, no patches
                _content_patch_state[run_id] = {"seq": 0, "nodes": {nid: content for nid, content in candidates}}
                return 0, []
            prev_nodes: dict[str, str] = state.get("nodes", {})
            patches: list[dict] = []
            updated_nodes = dict(prev_nodes)  # will mutate then store
            for nid, content in candidates:
                prev = prev_nodes.get(nid)
                if prev is None:
                    # New node -> full replace
                    patches.append({"id": nid, "mode": "replace", "content": content})
                    updated_nodes[nid] = content
                elif content != prev:
                    if content.startswith(prev):
                        # Pure append
                        delta = content[len(prev):]
                        patches.append({"id": nid, "mode": "append", "text": delta})
                        updated_nodes[nid] = content
                    else:
                        patches.append({"id": nid, "mode": "replace", "content": content})
                        updated_nodes[nid] = content
            if patches:
                new_seq = state["seq"] + 1
                state["seq"] = new_seq
                state["nodes"] = updated_nodes
                return new_seq, patches
            return state["seq"], []

if missing_vars:
    print(f"Error: Missing required environment variables: {', '.join(missing_vars)}")
    print("Please create a .env file with these variables or set them in your environment.")

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.utils.run_manager import run_manager
from tradingagents.config_loader import (
    get_provider_base_url,
    validate_model,
    get_providers,
)

app = FastAPI()

# Feature flags
ENABLE_MULTI_RUN = os.getenv("ENABLE_MULTI_RUN", "0") == "1"

# Pruning / retention configuration (defaults are conservative)
RUN_PRUNE_INTERVAL_SECONDS = int(os.getenv("RUN_PRUNE_INTERVAL_SECONDS", "300"))  # 5 min
RUN_MAX_AGE_HOURS = int(os.getenv("RUN_MAX_AGE_HOURS", "24"))  # in-memory run state retention
RUN_RESULTS_MAX_PER_TICKER = int(os.getenv("RUN_RESULTS_MAX_PER_TICKER", "20"))  # keep last N result folders per ticker
# Backward compatibility: if legacy RUN_RESULTS_MAX_AGE_HOURS is set, convert to days (ceil division)
_legacy_age_hours = os.getenv("RUN_RESULTS_MAX_AGE_HOURS")
if _legacy_age_hours is not None and os.getenv("RUN_RESULTS_MAX_AGE_DAYS") is None:
    try:
        hrs = int(_legacy_age_hours)
        # Map hours -> days; 0 preserves disable semantics
        if hrs == 0:
            os.environ["RUN_RESULTS_MAX_AGE_DAYS"] = "0"
        else:
            days = max(1, (hrs + 23) // 24)
            os.environ["RUN_RESULTS_MAX_AGE_DAYS"] = str(days)
    except ValueError:
        pass
RUN_RESULTS_MAX_AGE_DAYS = int(os.getenv("RUN_RESULTS_MAX_AGE_DAYS", "7"))  # default one week

# Base results dir (mirrors logic in default_config)
RESULTS_BASE = Path(os.getenv("TRADINGAGENTS_RESULTS_DIR", "./results")).resolve()

_pruning_thread: threading.Thread | None = None
_pruning_stop = threading.Event()

# Custom exception used for cooperative cancellation in multi-run mode
class RunCanceled(Exception):
    pass

# Main event loop reference (captured at startup) so threads can schedule coroutines
MAIN_EVENT_LOOP: asyncio.AbstractEventLoop | None = None

@app.on_event("startup")
async def _capture_loop():
    global MAIN_EVENT_LOOP
    MAIN_EVENT_LOOP = asyncio.get_event_loop()
    # Start pruning scheduler thread (only once; safe if multi-run disabled—still prunes legacy results dirs)
    def _prune_loop():
        while not _pruning_stop.is_set():
            try:
                # Prune in-memory run states
                try:
                    removed = run_manager.prune(max_age_hours=RUN_MAX_AGE_HOURS)
                    if removed:
                        print(f"[prune] Removed {removed} expired run state entries (> {RUN_MAX_AGE_HOURS}h)")
                except Exception as e:
                    print(f"[prune] RunManager prune error: {e}")
                # Prune results directories
                try:
                    prune_results_directories()
                except Exception as e:
                    print(f"[prune] Results prune error: {e}")
            finally:
                _pruning_stop.wait(RUN_PRUNE_INTERVAL_SECONDS)
    global _pruning_thread
    if _pruning_thread is None:
        _pruning_thread = threading.Thread(target=_prune_loop, name="RunPruner", daemon=True)
        _pruning_thread.start()

@app.on_event("shutdown")
async def _stop_pruner():
    _pruning_stop.set()
    if _pruning_thread and _pruning_thread.is_alive():
        _pruning_thread.join(timeout=2)
        print("[prune] Pruning thread stopped")

# ==============================================
# WebSocket Connection Management
# ==============================================
class ConnectionManager:
    """Tracks active websocket connections and allows broadcast of messages."""
    def __init__(self):
        self._connections: set[WebSocket] = set()
        self._lock = threading.Lock()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        with self._lock:
            self._connections.add(websocket)

    def disconnect_sync(self, websocket: WebSocket):
        # Called from sync context in finally blocks
        with self._lock:
            if websocket in self._connections:
                self._connections.remove(websocket)

    async def disconnect(self, websocket: WebSocket):
        with self._lock:
            if websocket in self._connections:
                self._connections.remove(websocket)
        try:
            await websocket.close()
        except Exception:
            pass

    async def broadcast_json(self, payload: dict):
        """Broadcast JSON payload to all active connections, pruning dead ones."""
        to_remove = []
        with self._lock:
            conns = list(self._connections)
        for ws in conns:
            try:
                await ws.send_json(payload)
            except Exception:
                to_remove.append(ws)
        if to_remove:
            with self._lock:
                for ws in to_remove:
                    self._connections.discard(ws)

manager = ConnectionManager()

# In-memory storage for the process state
# Using a lock for thread-safe access to app_state
app_state_lock = threading.Lock()
app_state: Dict[str, Any] = {
    # Legacy single-run state (used when ENABLE_MULTI_RUN is off)
    "process_running": False,
    "company_symbol": None,
    "execution_tree": [],
    "overall_status": "idle",  # idle, in_progress, completed, error
    "overall_progress": 0  # 0-100
}

# ==============================================
# Log Streaming Support (ring buffer per run)
# ==============================================
if ENABLE_LOG_STREAM:
    _log_lock = threading.Lock()
    # Mapping: run_id -> {"buffer": deque[dict], "seq": int}
    _run_logs: dict[str, dict[str, Any]] = {}
    LOG_BUFFER_MAX = int(os.getenv("LOG_BUFFER_MAX_LINES", "250"))

    # Severity levels (ordered)
    SEVERITY_LEVELS = {"TRACE": 0, "DEBUG": 10, "INFO": 20, "WARN": 30, "ERROR": 40}

    def _log_buffer_for(run_id: str):
        """Get or create the structured log buffer state for a run."""
        with _log_lock:
            state = _run_logs.get(run_id)
            if not state:
                state = {"buffer": deque(maxlen=LOG_BUFFER_MAX), "seq": 0}
                _run_logs[run_id] = state
            return state

    def log_run(
        run_id: str,
        message: str,
        severity: str = "INFO",
        source: str = "system",
        agent_id: str | None = None,
        raw: str | None = None,
    ):
        """Append a structured log entry and broadcast it over websocket.

        Broadcast payload shape (v2):
          { type: "log_append_run", run_id, entries: [ {seq, ts, iso, severity, source, agent_id, message} ], seq }
        """
        if not ENABLE_LOG_STREAM:
            return
        severity = severity.upper()
        if severity not in SEVERITY_LEVELS:
            severity = "INFO"
        now = time.time()
        iso = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(now))
        entry: dict[str, Any] = {
            "ts": now,
            "iso": iso,
            "severity": severity,
            "source": source,
            "agent_id": agent_id,
            "message": message.rstrip("\n"),
            "raw": raw,
        }
        state = _log_buffer_for(run_id)
        with _log_lock:
            state["seq"] += 1
            entry["seq"] = state["seq"]
            state["buffer"].append(entry)
            seq = state["seq"]
        payload = {"type": "log_append_run", "run_id": run_id, "entries": [entry], "seq": seq}
        try:
            if MAIN_EVENT_LOOP and not MAIN_EVENT_LOOP.is_closed():
                asyncio.run_coroutine_threadsafe(manager.broadcast_json(payload), MAIN_EVENT_LOOP)
        except Exception:
            pass

    def snapshot_run_logs(run_id: str) -> dict[str, Any] | None:
        """Return snapshot of structured log entries.

        Shape: {entries: [...], seq}
        """
        if not ENABLE_LOG_STREAM:
            return None
        with _log_lock:
            state = _run_logs.get(run_id)
            if not state:
                return {"entries": [], "seq": 0}
            entries = list(state["buffer"])
            seq = state["seq"]
        return {"entries": entries, "seq": seq}

    def _filter_logs(
        run_id: str,
        min_severity: str | None = None,
        severity_set: set[str] | None = None,
        sources: set[str] | None = None,
        q: str | None = None,
        after_seq: int | None = None,
        limit: int = 200,
    ) -> tuple[list[dict], int, int]:
        """Filter log entries for a run. Returns (entries, last_seq, total_seq).

        - min_severity: threshold (inclusive) if severity_set not provided.
        - severity_set: explicit allowed severities (overrides min_severity).
        - sources: restrict to given sources.
        - q: case-insensitive substring search over message & raw.
        - after_seq: only include entries with seq > after_seq.
        """
        with _log_lock:
            state = _run_logs.get(run_id)
            if not state:
                return [], 0, 0
            buf = list(state["buffer"])  # copy
            total_seq = state["seq"]
        if not buf:
            return [], 0, total_seq
        # Determine severity predicate
        if severity_set:
            allowed = {s.upper() for s in severity_set if s}
            def sev_ok(s: str):
                return s.upper() in allowed
        else:
            if min_severity and min_severity.upper() in SEVERITY_LEVELS:
                threshold = SEVERITY_LEVELS[min_severity.upper()]
            else:
                threshold = SEVERITY_LEVELS["INFO"]
            def sev_ok(s: str):
                return SEVERITY_LEVELS.get(s.upper(), 100) >= threshold
        q_lower = q.lower() if q else None
        res = []
        for e in buf:
            if after_seq is not None and e.get("seq", 0) <= after_seq:
                continue
            if not sev_ok(e.get("severity", "INFO")):
                continue
            if sources and e.get("source") not in sources:
                continue
            if q_lower:
                msg = e.get("message") or ""
                raw_val = e.get("raw") or ""
                if q_lower not in msg.lower() and (not raw_val or q_lower not in raw_val.lower()):
                    continue
            res.append(e)
            if len(res) >= limit:
                break
        last_seq = res[-1]["seq"] if res else after_seq or 0
        return res, last_seq, total_seq

# For multi-run mode we keep no global per-run state here; we rely on run_manager.

# Define the strict sequential phase execution order
PHASE_SEQUENCE = [
    "data_collection_phase",
    "research_phase",
    "planning_phase",
    "execution_phase",
    "risk_analysis_phase",
    # New dedicated top-level phase for the final portfolio decision
    "final_decision_phase"
]

# Mount the static directory to serve CSS, JS, etc.
app.mount("/static", StaticFiles(directory="webapp/static"), name="static")

# Setup Jinja2 for templating
template_dir = os.path.join(os.path.dirname(__file__), "templates")
jinja_env = jinja2.Environment(loader=jinja2.FileSystemLoader(template_dir))

# Allowed tags and attributes for sanitized markdown rendering
ALLOWED_TAGS = list(bleach.sanitizer.ALLOWED_TAGS) + [
    "p", "pre", "span", "h1", "h2", "h3", "h4", "h5", "h6", "table", "thead", "tbody", "tr", "th", "td", "blockquote", "code"
]
ALLOWED_ATTRIBUTES = {**bleach.sanitizer.ALLOWED_ATTRIBUTES, "span": ["class"], "code": ["class"], "th": ["align"], "td": ["align"]}

def render_markdown(value: str) -> str:
    """Convert markdown text to sanitized HTML."""
    if not isinstance(value, str):
        value = str(value)
    html = md.markdown(
        value,
        extensions=["fenced_code", "tables", "codehilite", "toc", "sane_lists"],
        output_format="html5"
    )
    cleaned = bleach.clean(html, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRIBUTES, strip=True)
    return cleaned

jinja_env.filters['markdown'] = render_markdown

async def _broadcast_status_locked_unlocked():
    """Helper to broadcast status updates using existing helper logic."""
    if ENABLE_MULTI_RUN:
        # Broadcast lightweight summaries for all runs (aggregate channel)
        aggregate = {}
        runs = run_manager.list_runs(summary_only=False)
        for r in runs:
            aggregate[r["run_id"]] = {
                "ticker": r["ticker"],
                "status": r["status"],
                "overall_progress": r["overall_progress"],
            }
        await manager.broadcast_json({
            "type": "status_update_aggregate",
            "runs": aggregate
        })
    else:
        status_updates = {}
        def extract_status_info(items):
            for item in items:
                status_updates[item["id"]] = {
                    "status": item["status"],
                    "status_icon": get_status_icon(item["status"])
                }
                if item.get("children"):
                    extract_status_info(item["children"])
        with app_state_lock:
            extract_status_info(app_state.get("execution_tree", []))
            payload = {
                "type": "status_update",
                "status_updates": status_updates,
                "overall_progress": app_state.get("overall_progress", 0),
                "overall_status": app_state.get("overall_status", "idle")
            }
        await manager.broadcast_json(payload)

def update_execution_state(state: Dict[str, Any], run_id: str | None = None):
    """Callback to merge new partial state into the appropriate execution tree (single or multi-run)."""
    #print(f"📡 Callback received state keys: {list(state.keys())} run_id={run_id}")

    agent_state_mapping = {
        "Market Analyst": {"phase": "data_collection", "agent_id": "market_analyst", "report_key": "market_report", "report_name": "Market Analysis Report"},
        "Social Analyst": {"phase": "data_collection", "agent_id": "social_analyst", "report_key": "sentiment_report", "report_name": "Sentiment Analysis Report"},
        "News Analyst": {"phase": "data_collection", "agent_id": "news_analyst", "report_key": "news_report", "report_name": "News Analysis Report"},
        "Fundamentals Analyst": {"phase": "data_collection", "agent_id": "fundamentals_analyst", "report_key": "fundamentals_report", "report_name": "Fundamentals Report"},
        "Bull Researcher": {"phase": "research", "agent_id": "bull_researcher", "report_key": "investment_debate_state.bull_history", "report_name": "Bull Case Analysis"},
        "Bear Researcher": {"phase": "research", "agent_id": "bear_researcher", "report_key": "investment_debate_state.bear_history", "report_name": "Bear Case Analysis"},
        "Research Manager": {"phase": "research", "agent_id": "research_manager", "report_key": "investment_debate_state.judge_decision", "report_name": "Research Synthesis"},
        "Trade Planner": {"phase": "planning", "agent_id": "trade_planner", "report_key": "trader_investment_plan", "report_name": "Trading Plan"},
        "Trader": {"phase": "execution", "agent_id": "trader", "report_key": "investment_plan", "report_name": "Execution Report"},
        "Risky Analyst": {"phase": "risk_analysis", "agent_id": "risky_analyst", "report_key": "risk_debate_state.risky_history", "report_name": "Risk Assessment (Aggressive)"},
        "Neutral Analyst": {"phase": "risk_analysis", "agent_id": "neutral_analyst", "report_key": "risk_debate_state.neutral_history", "report_name": "Risk Assessment (Neutral)"},
        "Safe Analyst": {"phase": "risk_analysis", "agent_id": "safe_analyst", "report_key": "risk_debate_state.safe_history", "report_name": "Risk Assessment (Conservative)"},
        "Risk Judge": {"phase": "final_decision", "agent_id": "risk_judge", "report_key": "final_trade_decision", "report_name": "Portfolio Manager's Decision"},
    }

    if ENABLE_MULTI_RUN and run_id:
        # Per-run update path
        run = run_manager.get_run(run_id)
        if not run:
            return
        execution_tree = run.get("execution_tree") or []
        if not execution_tree:
            execution_tree = initialize_complete_execution_tree()
        # Update agent statuses
        for _, agent_info in agent_state_mapping.items():
            report_data = get_nested_value(state, agent_info["report_key"])
            if report_data:
                # Use adapted update function that operates on provided tree
                update_agent_status_for_tree(agent_info, "completed", report_data, state, execution_tree)
                # Log streaming: append a concise log line for this agent's completion
                if ENABLE_LOG_STREAM:
                    try:
                        summary = agent_info.get("report_name") or agent_info.get("agent_id")
                        log_run(run_id, f"[{agent_info['agent_id']}] report updated -> {summary}", severity="INFO", source="agent", agent_id=agent_info['agent_id'])
                    except Exception:
                        pass
        mark_in_progress_agents(execution_tree)
        recalc_phase_statuses(execution_tree)
        total_agents = len(agent_state_mapping)
        completed_agents = count_completed_agents(execution_tree)
        overall_progress = min(100, int((completed_agents / max(total_agents, 1)) * 100))
        run_manager.update_run(run_id, execution_tree=execution_tree, overall_progress=overall_progress, status=(run.get("status") or "in_progress"))
    # Metrics removed: previously updated run metrics here
        # In multi-run mode we will broadcast later in enhanced websocket step; send minimal legacy broadcast for compatibility
        try:
            if MAIN_EVENT_LOOP and not MAIN_EVENT_LOOP.is_closed():
                asyncio.run_coroutine_threadsafe(_broadcast_status_locked_unlocked(), MAIN_EVENT_LOOP)
        except Exception:
            pass

def make_update_callback(run_id: str):
    """Return a per-run update callback closure that merges state and broadcasts a focused update.
    This wraps update_execution_state and then enqueues a targeted websocket broadcast with minimal payload.
    """
    def _cb(state_fragment: Dict[str, Any]):
        # Cooperative cancellation check before doing more work
        if run_manager.is_canceled(run_id):
            raise RunCanceled()
        update_execution_state(state_fragment, run_id=run_id)
        # Targeted broadcast with latest summary
        try:
            if MAIN_EVENT_LOOP and not MAIN_EVENT_LOOP.is_closed():
                async def _emit():
                    run = run_manager.get_run(run_id)
                    if not run:
                        return
                    payload = {
                        "type": "status_update_run",
                        "run_id": run_id,
                        "status": run["status"],
                        "overall_progress": run["overall_progress"],
                        "ticker": run["ticker"],
                    }
                    # When run is completed (or errored) include final_decision content if present
                    if run.get("status") in ("completed", "error", "canceled"):
                        final_decision = run.get("final_decision")
                        if final_decision is not None:
                            try:
                                if isinstance(final_decision, dict) and final_decision.get("version") == 1:
                                    # Build concise markdown from enriched schema
                                    risk = final_decision.get("risk_metrics", {})
                                    conf = final_decision.get("confidence", {})
                                    md_lines = [f"**Summary:** {final_decision.get('summary','')}"]
                                    if final_decision.get("action"):
                                        md_lines.append(f"**Action:** `{final_decision['action']}`")
                                    if any(risk.get(k) for k in ("stop_loss","take_profit","reward_risk_ratio")):
                                        rbits = []
                                        if risk.get("stop_loss"): rbits.append(f"SL {risk['stop_loss']}")
                                        if risk.get("take_profit"): rbits.append(f"TP {risk['take_profit']}")
                                        if risk.get("reward_risk_ratio") is not None: rbits.append(f"R/R {risk['reward_risk_ratio']}")
                                        md_lines.append("**Risk:** " + ", ".join(rbits))
                                    if conf.get("score") is not None:
                                        md_lines.append(f"**Confidence:** {conf['score']}")
                                    if final_decision.get("rationale"):
                                        md_lines.append("\n**Rationale:**")
                                        for r in final_decision["rationale"][:5]:
                                            md_lines.append(f"- {r}")
                                    md_lines.append("\n<details><summary>Raw Decision</summary>\n\n" + (final_decision.get("raw") or "") + "\n\n</details>")
                                    md_source = "\n".join(md_lines)
                                elif isinstance(final_decision, (str, bytes)):
                                    md_source = final_decision.decode() if isinstance(final_decision, bytes) else final_decision
                                else:
                                    md_source = str(final_decision)
                                decision_html = render_markdown(md_source)
                                payload["final_decision"] = final_decision
                                payload["decision_html"] = decision_html
                                if ENABLE_LOG_STREAM:
                                    try:
                                        log_run(run_id, "[final_decision] Portfolio decision available", severity="INFO", source="decision")
                                    except Exception:
                                        pass
                            except Exception:
                                pass
                    # If patches enabled, compute diff & send patch message (in addition to status summary for backward compatibility)
                    if ENABLE_WS_PATCHES:
                        seq, changed = _compute_patch(run_id, run.get("execution_tree", []))
                        if changed:
                            patch_payload = {
                                "type": "status_patch_run",
                                "run_id": run_id,
                                "seq": seq,
                                "changed": changed,
                                "overall_progress": run["overall_progress"],
                                "status": run["status"],
                            }
                            await manager.broadcast_json(patch_payload)
                    # Content patches (reports/messages) – separate sequence
                    if ENABLE_WS_PATCHES and ENABLE_CONTENT_PATCHES:
                        try:
                            cseq, cpatches = _compute_content_patches(run_id, run.get("execution_tree", []))
                            if cpatches:
                                await manager.broadcast_json({
                                    "type": "content_patch_run",
                                    "run_id": run_id,
                                    "seq": cseq,
                                    "patches": cpatches
                                })
                        except Exception:
                            pass
                    # Update metrics after broadcasting patch (non-terminal)
                    try:
                        # Metrics removed: previously updated run metrics here
                        pass
                    except Exception:
                        pass
                    await manager.broadcast_json(payload)
                asyncio.run_coroutine_threadsafe(_emit(), MAIN_EVENT_LOOP)
        except Exception:
            pass
    return _cb

def prune_results_directories():
    """Apply retention rules to results/ directory.

    Rules:
      - Keep at most RUN_RESULTS_MAX_PER_TICKER newest dated folders per ticker.
    - Remove folders older than RUN_RESULTS_MAX_AGE_DAYS even if within count (skips active runs).
      - Active runs (whose results_path matches a run in RunManager with status pending/in_progress) are never deleted.
    """
    if not RESULTS_BASE.exists():
        return
    # If age hours set to 0 => disable all deletion (user wants full retention)
    if RUN_RESULTS_MAX_AGE_DAYS == 0:
        return
    now = time.time()
    max_age_seconds = RUN_RESULTS_MAX_AGE_DAYS * 86400
    # Build set of protected active paths
    active_paths = set()
    for r in run_manager.list_runs(summary_only=False):
        if r["status"] in ("pending", "in_progress") and r.get("results_path"):
            try:
                active_paths.add(Path(r["results_path"]).resolve())
            except Exception:
                pass
    for ticker_dir in RESULTS_BASE.iterdir():
        if not ticker_dir.is_dir():
            continue
        # Collect candidate run directories
        run_dirs = [d for d in ticker_dir.iterdir() if d.is_dir()]
        # Sort newest first by directory name (timestamps sortable) then by mtime as fallback
        run_dirs.sort(key=lambda p: (p.name, p.stat().st_mtime), reverse=True)
        # Enforce count retention (skip active)
        for idx, d in enumerate(run_dirs):
            if d.resolve() in active_paths:
                continue
            if idx >= RUN_RESULTS_MAX_PER_TICKER:
                safe_remove_directory(d)
        # Age-based removal
        for d in run_dirs:
            if d.resolve() in active_paths:
                continue
            try:
                age = now - d.stat().st_mtime
                if age > max_age_seconds:
                    safe_remove_directory(d)
            except FileNotFoundError:
                continue

def safe_remove_directory(path: Path):
    try:
        shutil.rmtree(path)
        print(f"[prune] Removed old results dir: {path}")
    except Exception as e:
        print(f"[prune] Failed to remove {path}: {e}")

# -------------------- Decision Enrichment --------------------
def build_enriched_decision(raw_decision: Any, final_state: dict, meta: dict | None = None) -> dict:
    """Construct a structured enriched decision object from the raw LLM decision text.

    Schema (versioned for forward compatibility):
    {
      version: 1,
      summary: str,
      action: str | None,
      sizing: { suggested_units: float | None, sizing_basis: str },
      risk_metrics: { stop_loss, take_profit, reward_risk_ratio, est_upside_pct, est_downside_pct },
      confidence: { score: float | None, basis: str },
      rationale: [str],
      raw: str
    }
    NOTE: Current implementation uses heuristics; future iterations can inject real analytics.
    """
    if raw_decision is None:
        return {
            "version": 1,
            "summary": "No decision produced",
            "action": None,
            "sizing": {"suggested_units": None, "sizing_basis": "no_decision"},
            "risk_metrics": {"stop_loss": None, "take_profit": None, "reward_risk_ratio": None, "est_upside_pct": None, "est_downside_pct": None},
            "confidence": {"score": None, "basis": "n/a"},
            "rationale": [],
            "raw": ""
        }
    text = raw_decision.decode() if isinstance(raw_decision, bytes) else str(raw_decision)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    summary = lines[0][:180] if lines else text[:180]
    lower_full = text.lower()
    action = None
    action_map = {
        "open_long": ["open a long", "open long", "go long"],
        "close_long": ["close the long", "close long"],
        "maintain_long": ["maintain the long", "hold long", "keep long"],
        "open_short": ["open a short", "open short", "go short"],
        "close_short": ["close the short", "close short"],
        "maintain_short": ["maintain the short", "hold short", "keep short"],
        "none": ["do nothing", "no action", "stay neutral"],
    }
    for key, tokens in action_map.items():
        if any(tok in lower_full for tok in tokens):
            action = key
            break
    import re
    sl_match = re.search(r"stop[- ]loss[^0-9]{0,12}([0-9]+\.?[0-9]*)", lower_full)
    tp_match = re.search(r"take[- ]profit[^0-9]{0,12}([0-9]+\.?[0-9]*)", lower_full)
    stop_loss = sl_match.group(1) if sl_match else None
    take_profit = tp_match.group(1) if tp_match else None
    reward_risk_ratio = None
    try:
        if stop_loss and take_profit:
            sl_v = float(stop_loss)
            tp_v = float(take_profit)
            if sl_v > 0:
                reward_risk_ratio = round(tp_v / sl_v, 2)
    except Exception:
        pass
    rationale = []
    for ln in lines[1:]:
        if len(rationale) >= 8:
            break
        if ln.startswith(('-', '*')) or any(k in ln.lower() for k in ["because", "due to", "therefore", "as a result", "given", "driven"]):
            rationale.append(ln[:300])
    if not rationale and len(lines) > 1:
        rationale = [l[:300] for l in lines[1:4]]
    rationale_markers = sum(1 for ln in lines if any(k in ln.lower() for k in ["because", "due to", "therefore", "since"]))
    length_factor = min(1.0, len(text) / 4000)
    confidence_score = round(min(1.0, 0.3 + 0.1 * rationale_markers + 0.6 * length_factor), 2)
    enriched = {
        "version": 1,
        "summary": summary,
        "action": action,
        "sizing": {"suggested_units": None, "sizing_basis": "heuristic_placeholder"},
        "risk_metrics": {
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "reward_risk_ratio": reward_risk_ratio,
            "est_upside_pct": None,
            "est_downside_pct": None,
        },
        "confidence": {"score": confidence_score, "basis": "heuristic(length + rationale_markers)"},
        "rationale": rationale,
        "raw": text,
    }
    return enriched

def initialize_complete_execution_tree():
    """Initialize the complete execution tree with all agents in pending state."""
    return [
        {
            "id": "data_collection_phase",
            "name": "📊 Data Collection Phase",
            "status": "pending",
            "node_type": "phase",
            "started_at": None,
            "ended_at": None,
            "duration_ms": None,
            "content": "Collecting market data and analysis from various sources",
            "children": [
                create_agent_node("market_analyst", "📈 Market Analyst"),
                create_agent_node("social_analyst", "📱 Social Media Analyst"),
                create_agent_node("news_analyst", "📰 News Analyst"),
                create_agent_node("fundamentals_analyst", "📊 Fundamentals Analyst")
            ]
        },
        {
            "id": "research_phase",
            "name": "🔍 Research Phase",
            "status": "pending",
            "node_type": "phase",
            "started_at": None,
            "ended_at": None,
            "duration_ms": None,
            "content": "Research and debate investment perspectives",
            "children": [
                create_agent_node("bull_researcher", "🐂 Bull Researcher"),
                create_agent_node("bear_researcher", "🐻 Bear Researcher"),
                create_agent_node("research_manager", "🔍 Research Manager")
            ]
        },
        {
            "id": "planning_phase",
            "name": "📋 Planning Phase", 
            "status": "pending",
            "node_type": "phase",
            "started_at": None,
            "ended_at": None,
            "duration_ms": None,
            "content": "Develop trading strategy and execution plan",
            "children": [
                create_agent_node("trade_planner", "📋 Trade Planner")
            ]
        },
        {
            "id": "execution_phase",
            "name": "⚡ Execution Phase",
            "status": "pending", 
            "node_type": "phase",
            "started_at": None,
            "ended_at": None,
            "duration_ms": None,
            "content": "Execute trades based on analysis and planning",
            "children": [
                create_agent_node("trader", "⚡ Trader")
            ]
        },
        {
            "id": "risk_analysis_phase",
            "name": "⚠️ Risk Management Phase",
            "status": "pending",
            "node_type": "phase",
            "started_at": None,
            "ended_at": None,
            "duration_ms": None,
            "content": "Assess and manage investment risks",
            "children": [
                create_agent_node("risky_analyst", "🚨 Aggressive Risk Analyst"),
                create_agent_node("neutral_analyst", "⚖️ Neutral Risk Analyst"),
                create_agent_node("safe_analyst", "🛡️ Conservative Risk Analyst")
            ]
        },
        {
            "id": "final_decision_phase",
            "name": "🧠 Portfolio Manager's Decision",
            "status": "pending",
            "node_type": "phase",
            "started_at": None,
            "ended_at": None,
            "duration_ms": None,
            "content": "Final portfolio / trade decision synthesized from all prior phases",
            "children": [
                create_agent_node("risk_judge", "🧠 Portfolio Manager")
            ]
        }
    ]

def create_agent_node(agent_id: str, agent_name: str):
    """Create a standardized agent node with report and messages sub-items."""
    return {
        "id": agent_id,
        "name": agent_name,
        "status": "pending",
        "node_type": "agent",
        "started_at": None,
        "ended_at": None,
        "duration_ms": None,
        "content": f"Agent: {agent_name} - Awaiting execution",
        "children": [
            {
                "id": f"{agent_id}_messages",
                "name": "💬 Messages",
                "status": "pending", 
                "node_type": "messages",
                "started_at": None,
                "ended_at": None,
                "duration_ms": None,
                "content": "No messages yet",
                "children": [],
                "timestamp": time.time()
            },
            {
                "id": f"{agent_id}_report",
                "name": "📄 Report",
                "status": "pending",
                "node_type": "report",
                "started_at": None,
                "ended_at": None,
                "duration_ms": None,
                "content": "Report not yet generated",
                "children": [],
                "timestamp": time.time()
            }
        ],
        "timestamp": time.time()
    }

def get_nested_value(data: dict, key_path: str):
    """Get value from nested dict using dot notation (e.g., 'investment_debate_state.bull_history')."""
    keys = key_path.split('.')
    value = data
    for key in keys:
        if isinstance(value, dict) and key in value:
            value = value[key]
        else:
            return None
    return value

def update_agent_status(agent_info: dict, status: str, report_data: any, full_state: dict):
    """Update an agent's status and content in the execution tree."""
    execution_tree = app_state["execution_tree"]
    
    # Find the agent in the tree
    agent_node = find_agent_in_tree(agent_info["agent_id"], execution_tree)
    if not agent_node:
        return
        
    # Update agent status
    if agent_node["status"] != "completed":
        # Instrument timing
        now_ts = time.time()
        if agent_node.get("started_at") is None:
            agent_node["started_at"] = now_ts
        if status == "in_progress" and agent_node.get("started_at") is None:
            agent_node["started_at"] = now_ts
        if status in ("completed", "error", "canceled"):
            if agent_node.get("ended_at") is None:
                agent_node["ended_at"] = now_ts
                if agent_node.get("started_at") is not None:
                    agent_node["duration_ms"] = int((agent_node["ended_at"] - agent_node["started_at"]) * 1000)
        agent_node["status"] = status
        if status == "completed":
            agent_node["content"] = f"✅ {agent_node['name']} - Analysis completed"
        elif status == "error":
            agent_node["content"] = f"❌ {agent_node['name']} - Error during analysis"
        elif status == "canceled":
            agent_node["content"] = f"⛔ {agent_node['name']} - Canceled"
        
        # Update report sub-item
        report_node = find_item_by_id(f"{agent_info['agent_id']}_report", agent_node["children"])
        if report_node:
            report_node["status"] = "completed"
            report_node["content"] = format_report_content(agent_info["report_name"], report_data)
            
        # Update messages sub-item (extract from state if available)
        messages_node = find_item_by_id(f"{agent_info['agent_id']}_messages", agent_node["children"])
        if messages_node:
            messages_node["status"] = "completed"
            messages_node["content"] = extract_agent_messages(full_state, agent_info["agent_id"])
    
    # Phase status recalculated globally in recalc_phase_statuses

def update_agent_status_for_tree(agent_info: dict, status: str, report_data: any, full_state: dict, execution_tree: list):
    """Variant of update_agent_status operating on an explicit execution_tree (used for multi-run)."""
    agent_node = find_agent_in_tree(agent_info["agent_id"], execution_tree)
    if not agent_node:
        return
    if agent_node["status"] != "completed":
        now_ts = time.time()
        if agent_node.get("started_at") is None:
            agent_node["started_at"] = now_ts
        if status in ("completed", "error", "canceled") and agent_node.get("ended_at") is None:
            agent_node["ended_at"] = now_ts
            if agent_node.get("started_at") is not None:
                agent_node["duration_ms"] = int((agent_node["ended_at"] - agent_node["started_at"]) * 1000)
        agent_node["status"] = status
        if status == "completed":
            agent_node["content"] = f"✅ {agent_node['name']} - Analysis completed"
        elif status == "error":
            agent_node["content"] = f"❌ {agent_node['name']} - Error during analysis"
        elif status == "canceled":
            agent_node["content"] = f"⛔ {agent_node['name']} - Canceled"
        report_node = find_item_by_id(f"{agent_info['agent_id']}_report", agent_node["children"])
        if report_node:
            report_node["status"] = "completed"
            report_node["content"] = format_report_content(agent_info["report_name"], report_data)
        messages_node = find_item_by_id(f"{agent_info['agent_id']}_messages", agent_node["children"])
        if messages_node:
            messages_node["status"] = "completed"
            messages_node["content"] = extract_agent_messages(full_state, agent_info["agent_id"])

def find_agent_in_tree(agent_id: str, tree: list):
    """Find an agent node in the execution tree."""
    for phase in tree:
        if phase.get("children"):
            for agent in phase["children"]:
                if agent["id"] == agent_id:
                    return agent
    return None

def mark_agent_error(agent_id: str, error_message: str):
    """Mark a specific agent (and its phase) as error with provided message."""
    execution_tree = app_state.get("execution_tree", [])
    target_agent = find_agent_in_tree(agent_id, execution_tree)
    if not target_agent:
        return False
    # Mark agent
    target_agent["status"] = "error"
    target_agent["content"] = f"❌ {target_agent['name']} - Error encountered\n\n{error_message}"
    # Mark any children as error for clarity
    for child in target_agent.get("children", []):
        if child["status"] != "completed":
            child["status"] = "error"
            if not child.get("content"):
                child["content"] = "Error in parent agent"
    # Mark containing phase error
    for phase in execution_tree:
        if phase.get("children") and any(c is target_agent for c in phase["children"]):
            phase["status"] = "error"
            if not phase.get("content") or "Error" not in phase["content"]:
                phase["content"] = f"❌ {phase['name']} - Error in {target_agent['name']}"
            break
    return True

def find_item_by_id(item_id: str, items: list):
    """Find an item by ID in a list of items."""
    for item in items:
        if item["id"] == item_id:
            return item
    return None

def format_report_content(report_name: str, report_data: any) -> str:
    """Format report data for display."""
    if isinstance(report_data, str):
        return f"📄 {report_name}\n\n{report_data}"
    elif isinstance(report_data, dict):
        return f"📄 {report_name}\n\n{str(report_data)}"
    elif isinstance(report_data, list) and report_data:
        # For debate histories, show the latest message
        latest = report_data[-1] if report_data else "No data"
        return f"📄 {report_name}\n\n{str(latest)}"
    else:
        return f"📄 {report_name}\n\nReport generated successfully"

def extract_agent_messages(state: dict, agent_id: str) -> str:
    """Extract relevant messages for an agent from the state."""
    # Expecting state['messages'] to be a list of dicts with optional keys like
    # 'role', 'content', 'timestamp'. We'll display each in an expandable box.
    messages = state.get("messages", []) or []
    if not messages:
        return "💬 Agent Messages\n\nNo messages recorded for this agent."

    # Filter messages for this agent if agent_id field present
    filtered = []
    for m in messages:
        if isinstance(m, dict):
            msg_agent = m.get("agent_id") or m.get("agent")
            if msg_agent and msg_agent != agent_id:
                continue
            filtered.append(m)
        else:
            # Try common attributes used by message objects (e.g., langchain HumanMessage / AIMessage)
            msg_agent = getattr(m, "agent_id", None) or getattr(m, "agent", None)
            if msg_agent and msg_agent != agent_id:
                continue
            filtered.append(m)
    if not filtered:
        filtered = messages  # fallback to all if no agent-specific match

    parts = ["💬 Agent Messages", "", f"Total messages: {len(filtered)}", ""]
    for idx, m in enumerate(filtered, start=1):
        if isinstance(m, dict):
            role = m.get("role") or m.get("type") or "message"
            ts = m.get("timestamp")
            content = m.get("content") or m.get("text") or "(no content)"
        else:
            # Object-based message
            role = getattr(m, "role", None) or getattr(m, "type", None) or m.__class__.__name__
            ts = getattr(m, "timestamp", None)
            # LangChain messages often have a .content attribute
            content = getattr(m, "content", None) or getattr(m, "text", None) or str(m)
        # Escape triple backticks to avoid markdown parser confusion
        if isinstance(content, str):
            content = content.replace('```', '\u0060\u0060\u0060')
        header = f"{idx}. {role.title()}" + (f" – {ts}" if ts else "")
        # Use HTML <details> so user can expand long messages
        parts.append(
            f"<details class=\"message-box\" {'open' if idx <= 3 else ''}>")
        parts.append(f"  <summary>{header}</summary>")
        # Wrap content in pre for formatting
        parts.append("  <pre class=\"message-content\">" + str(content) + "</pre>")
        parts.append("</details>")

    return "\n".join(parts)

def recalc_phase_statuses(execution_tree: list):
    """Recalculate each phase's status: pending (no started), in_progress (some running/completed but not all), completed (all done), error if any child error."""
    for phase in execution_tree:
        if not phase.get("children"):
            continue
        child_statuses = [c["status"] for c in phase["children"]]
        if any(s == "error" for s in child_statuses):
            phase["status"] = "error"
            phase["content"] = f"❌ {phase['name']} - Error in sub-task"
        elif all(s == "completed" for s in child_statuses):
            phase["status"] = "completed"
            phase["content"] = f"✅ {phase['name']} - All agents completed successfully"
        elif any(s in ("in_progress", "completed") for s in child_statuses):
            # At least one started but not all done
            if phase["status"] != "in_progress":
                phase["status"] = "in_progress"
                phase["content"] = f"⏳ {phase['name']} - Running..."
        else:
            # All pending
            phase["status"] = "pending"


def count_completed_agents(execution_tree: list) -> int:
    """Count the number of completed agents across all phases."""
    count = 0
    for phase in execution_tree:
        if phase.get("children"):
            for agent in phase["children"]:
                if agent["status"] == "completed":
                    count += 1
    return count

def mark_in_progress_agents(execution_tree: list):
    """Activate all pending agents in the earliest not-yet-complete phase.
    Updated logic for parallel execution within a phase:
      - Identify the first phase (by PHASE_SEQUENCE) whose predecessors are fully completed and which itself isn't complete.
      - For that phase, mark every agent still in 'pending' as 'in_progress'.
      - Do NOT overwrite agents already marked 'in_progress' or 'completed'.
      - Also mark their immediate child nodes (messages/report) from pending -> in_progress so UI shows activity.
    """
    if not execution_tree:
        return

    phase_map = {p["id"]: p for p in execution_tree}

    active_phase = None
    for phase_id in PHASE_SEQUENCE:
        phase = phase_map.get(phase_id)
        if not phase:
            continue
        prev_completed = all(
            (phase_map.get(prev_id) and all(c["status"] == "completed" for c in phase_map[prev_id].get("children", [])))
            for prev_id in PHASE_SEQUENCE[:PHASE_SEQUENCE.index(phase_id)]
        )
        if not prev_completed:
            continue
        children = phase.get("children", [])
        if not children:
            continue
        phase_done = all(c["status"] == "completed" for c in children)
        if not phase_done:
            active_phase = phase
            break

    if not active_phase:
        return

    # Mark all pending agents in this phase as in_progress (parallel start)
    for agent in active_phase.get("children", []):
        if agent["status"] == "pending":
            agent["status"] = "in_progress"
            agent["content"] = f"⏳ {agent['name']} - Running analysis..."
            for child in agent.get("children", []):
                if child["status"] == "pending":
                    child["status"] = "in_progress"

def run_trading_process(company_symbol: str, config: Dict[str, Any], run_id: str | None = None):
    """Runs the TradingAgentsGraph in a separate thread.

    If run_id is provided and multi-run enabled, updates go through RunManager; else legacy app_state.
    """
    if ENABLE_MULTI_RUN and run_id:
        run_manager.update_run(run_id, status="in_progress", overall_progress=0)
    else:
        with app_state_lock:
            app_state["overall_status"] = "in_progress"
            app_state["overall_progress"] = 0

    try:
        # Import and create custom config
        from tradingagents.default_config import DEFAULT_CONFIG
        
        # Create custom configuration with user selections
        custom_config = DEFAULT_CONFIG.copy()
        custom_config["llm_provider"] = config["llm_provider"]
        custom_config["max_debate_rounds"] = config["max_debate_rounds"]
        custom_config["cost_per_trade"] = config["cost_per_trade"]
        
        # Validate selected models against central config
        provider_key = config["llm_provider"]
        for model_field in ("quick_think_llm", "deep_think_llm"):
            mval = config.get(model_field)
            if mval and not validate_model(provider_key, mval):
                raise ValueError(f"Model '{mval}' not valid for provider '{provider_key}'")

        # Set the appropriate LLM models based on provider (Gemini special naming retained)
        if provider_key == "google":
            custom_config["gemini_quick_think_llm"] = config["quick_think_llm"]
            custom_config["gemini_deep_think_llm"] = config["deep_think_llm"]
        else:
            custom_config["quick_think_llm"] = config["quick_think_llm"]
            custom_config["deep_think_llm"] = config["deep_think_llm"]

        # Central provider base_url
        try:
            custom_config["backend_url"] = get_provider_base_url(provider_key)
        except Exception:
            # Fallback to environment-specific logic (should not happen if YAML maintained)
            if provider_key == "ollama":
                custom_config["backend_url"] = f"http://{os.getenv('OLLAMA_HOST', 'localhost')}:11434/v1"
            else:
                custom_config["backend_url"] = "https://api.openai.com/v1"
        
        print(f"🚀 Initializing TradingAgentsGraph for {company_symbol}")
        if ENABLE_MULTI_RUN and run_id and ENABLE_LOG_STREAM:
            try:
                log_run(run_id, f"Starting run for {company_symbol}", severity="INFO", source="system")
            except Exception:
                pass
        graph = TradingAgentsGraph(config=custom_config)
        # Create timestamped results directory for this run
        from tradingagents.utils.results import create_run_results_dirs
        from tradingagents.utils.run_manager import generate_run_id  # local import if needed
        # Provide run_id to results dir for marker file when multi-run
        results_dir, reports_dir, log_file = create_run_results_dirs(
            custom_config.get("results_dir", "./results"), company_symbol, config["analysis_date"], run_id=run_id
        )
        if ENABLE_MULTI_RUN and run_id:
            # Persist actual results path now that it exists
            run_manager.update_run(run_id, results_path=str(results_dir))
        print(f"📁 Results directory: {results_dir}")
        if ENABLE_MULTI_RUN and run_id and ENABLE_LOG_STREAM:
            try:
                log_run(run_id, f"Results directory ready: {results_dir}", severity="DEBUG", source="system")
            except Exception:
                pass
        analysis_date = config["analysis_date"]  # Use user-selected date
        print(f"🔄 Starting propagation for {company_symbol} on {analysis_date}")
        if ENABLE_MULTI_RUN and run_id and ENABLE_LOG_STREAM:
            try:
                log_run(run_id, f"Propagation started for trade_date={analysis_date}", severity="INFO", source="system")
            except Exception:
                pass
        
        # Include user position context
        user_position = config.get("user_position", "none")
        init_sl = config.get("initial_stop_loss")
        init_tp = config.get("initial_take_profit")

        # The propagate method now accepts the callback and trade_date and we will inject user position.
        # Wrap callback to also persist logs and report sections
        # Choose update mechanism depending on mode
        per_run_callback = make_update_callback(run_id) if (ENABLE_MULTI_RUN and run_id) else None

        def logging_callback(state: Dict[str, Any]):
            # Persist selected evolving report sections (no verbose state key logging)
            try:
                report_keys = [
                    "market_report", "sentiment_report", "news_report", "fundamentals_report",
                    "investment_plan", "trader_investment_plan", "final_trade_decision"
                ]
                for rk in report_keys:
                    content = state.get(rk)
                    if content:
                        out_path = reports_dir / f"{rk}.md"
                        with open(out_path, "w", encoding="utf-8") as rf:
                            rf.write(str(content))
            except Exception:
                pass
            # Cancellation check (multi-run)
            if ENABLE_MULTI_RUN and run_id and run_manager.is_canceled(run_id):
                raise RunCanceled()
            if per_run_callback:
                per_run_callback(state)
            else:
                update_execution_state(state, run_id=None)

        # stream event logger to capture raw message content
        def stream_logger(event_state: Dict[str, Any]):
            messages = event_state.get("messages", [])
            if messages:
                last_msg = messages[-1]
                # Try to extract textual content similar to CLI logic
                text = None
                if hasattr(last_msg, "content"):
                    lc = last_msg.content
                    if isinstance(lc, str):
                        text = lc
                    elif isinstance(lc, list):
                        # Join textual segments
                        segs = []
                        for seg in lc:
                            if isinstance(seg, dict) and seg.get("type") == "text":
                                segs.append(seg.get("text", ""))
                            else:
                                segs.append(str(seg))
                        text = " ".join(segs)
                # Agent attribution
                agent_name = None
                for attr in ("name", "role", "sender", "author"):
                    if hasattr(last_msg, attr):
                        val = getattr(last_msg, attr)
                        if isinstance(val, str) and val:
                            agent_name = val
                            break
                if not agent_name and text:
                    # Heuristic attribution based on state keys
                    if event_state.get("market_report"):
                        agent_name = "Market Analyst"
                    elif event_state.get("sentiment_report"):
                        agent_name = "Social Analyst"
                    elif event_state.get("news_report"):
                        agent_name = "News Analyst"
                    elif event_state.get("fundamentals_report"):
                        agent_name = "Fundamentals Analyst"
                    elif event_state.get("investment_debate_state"):
                        inv_state = event_state.get("investment_debate_state", {}) or {}
                        cr = inv_state.get("current_response", "").lower()
                        if cr.startswith("bull"):
                            agent_name = "Bull Researcher"
                        elif cr.startswith("bear"):
                            agent_name = "Bear Researcher"
                        elif inv_state.get("judge_decision"):
                            agent_name = "Research Manager"
                    elif event_state.get("risk_debate_state"):
                        risk_state = event_state.get("risk_debate_state", {}) or {}
                        cr = risk_state.get("current_response", "").lower()
                        if cr.startswith("risky"):
                            agent_name = "Risky Analyst"
                        elif cr.startswith("safe"):
                            agent_name = "Safe Analyst"
                        elif cr.startswith("neutral"):
                            agent_name = "Neutral Analyst"
                        elif risk_state.get("judge_decision"):
                            agent_name = "Risk Judge"
                if agent_name and text and not text.startswith(f"[{agent_name}]"):
                    text = f"[{agent_name}] {text}"
                if text:
                    try:
                        with open(log_file, "a", encoding="utf-8") as lf:
                            lf.write(f"MESSAGE: {text.replace('\n',' ')}\n")
                    except Exception:
                        pass
                    if ENABLE_MULTI_RUN and run_id and ENABLE_LOG_STREAM:
                        try:
                            log_run(run_id, text, severity="DEBUG", source="llm", agent_id=None)
                        except Exception:
                            pass
                # Tool calls if present
                if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
                    for tc in last_msg.tool_calls:
                        try:
                            if isinstance(tc, dict):
                                name = tc.get("name", "unknown")
                                args = tc.get("args", {})
                            else:
                                name = getattr(tc, "name", "unknown")
                                args = getattr(tc, "args", {})
                            with open(log_file, "a", encoding="utf-8") as lf:
                                lf.write(f"TOOL_CALL: {name} args={args}\n")
                            if ENABLE_MULTI_RUN and run_id and ENABLE_LOG_STREAM:
                                try:
                                    log_run(run_id, f"Tool call: {name} args={args}", severity="DEBUG", source="tool")
                                except Exception:
                                    pass
                        except Exception:
                            pass
            # Cancellation cooperative check after processing stream event
            if ENABLE_MULTI_RUN and run_id and run_manager.is_canceled(run_id):
                raise RunCanceled()

        final_state = {}
        processed_signal = None
        try:
            final_state, processed_signal = graph.propagate(
                company_symbol,
                trade_date=analysis_date,
                user_position=user_position,
                cost_per_trade=config.get("cost_per_trade", 0.0),
                on_step_callback=logging_callback,
                on_stream_event=stream_logger,
                initial_stop_loss=init_sl,
                initial_take_profit=init_tp,
            )
        except RunCanceled:
            if ENABLE_MULTI_RUN and run_id:
                # Mark tree nodes still in progress as canceled for clarity
                run = run_manager.get_run(run_id)
                tree = run.get("execution_tree") if run else []
                for phase in tree:
                    for agent in phase.get("children", []):
                        if agent.get("status") in ("pending", "in_progress"):
                            agent["status"] = "canceled"
                            agent["content"] = f"🚫 {agent['name']} - Canceled"
                            for child in agent.get("children", []):
                                if child.get("status") in ("pending", "in_progress"):
                                    child["status"] = "canceled"
                    if phase.get("status") in ("pending", "in_progress"):
                        phase["status"] = "canceled"
                run_manager.update_run(run_id, status="canceled", execution_tree=tree)
            else:
                with app_state_lock:
                    for phase in app_state.get("execution_tree", []):
                        for agent in phase.get("children", []):
                            if agent.get("status") in ("pending", "in_progress"):
                                agent["status"] = "canceled"
                                agent["content"] = f"🚫 {agent['name']} - Canceled"
                    app_state["overall_status"] = "canceled"
            # Early exit after cancellation
            return
        print(f"✅ Propagation completed for {company_symbol}")
        if ENABLE_MULTI_RUN and run_id and ENABLE_LOG_STREAM:
            try:
                log_run(run_id, f"Run completed successfully", severity="INFO", source="system")
            except Exception:
                pass
        
        if ENABLE_MULTI_RUN and run_id:
            run_manager.update_run(run_id, status="completed", overall_progress=100, final_decision=processed_signal)
            # Mark run end metric
            try:
                # Metrics removed: previously marked run terminal for metrics
                pass
            except Exception:
                pass
        else:
            with app_state_lock:
                app_state["overall_status"] = "completed"
                app_state["overall_progress"] = 100
                if app_state["execution_tree"]:
                    app_state["execution_tree"][0]["status"] = "completed"
                    app_state["execution_tree"][0]["content"] = f"✅ Analysis completed successfully!\n\nFinal Decision: {processed_signal}\n\nFull State: {str(final_state)}\n\nResults saved to: {results_dir}"

    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        # Attempt to extract agent name from traceback (LangGraph style: "During task with name 'Risk Judge'")
        import re
        agent_name = None
        m = re.search(r"During task with name '([^']+)'", error_detail)
        if m:
            agent_name = m.group(1)
        # Map human-readable agent name to internal agent_id used in tree
        name_to_id = {
            "Market Analyst": "market_analyst",
            "Social Analyst": "social_analyst",
            "News Analyst": "news_analyst",
            "Fundamentals Analyst": "fundamentals_analyst",
            "Bull Researcher": "bull_researcher",
            "Bear Researcher": "bear_researcher",
            "Research Manager": "research_manager",
            "Trade Planner": "trade_planner",
            "Trader": "trader",
            "Risky Analyst": "risky_analyst",
            "Neutral Analyst": "neutral_analyst",
            "Safe Analyst": "safe_analyst",
            "Risk Judge": "risk_judge"
        }
        mapped_agent_id = name_to_id.get(agent_name) if agent_name else None
        if ENABLE_MULTI_RUN and run_id:
            # Attach error to run state
            run = run_manager.get_run(run_id)
            exec_tree = run.get("execution_tree") if run else []
            if not exec_tree:
                exec_tree = initialize_complete_execution_tree()
            # Simplistic error append
            exec_tree.append({
                "id": "error",
                "name": f"Process Error{(' - ' + agent_name) if agent_name else ''}",
                "status": "error",
                "content": f"Error during execution: {str(e)}\n\n{error_detail}",
                "children": [],
                "timestamp": time.time()
            })
            run_manager.update_run(run_id, status="error", overall_progress=100, error=str(e), execution_tree=exec_tree)
            if ENABLE_LOG_STREAM:
                try:
                    log_run(run_id, f"Error: {str(e)}", severity="ERROR", source="system")
                except Exception:
                    pass
            try:
                # Metrics removed: previously marked run terminal for metrics
                pass
            except Exception:
                pass
            try:
                # Metrics removed: previously marked run terminal for metrics
                pass
            except Exception:
                pass
        else:
            with app_state_lock:
                app_state["overall_status"] = "error"
                app_state["overall_progress"] = 100
                if mapped_agent_id and mark_agent_error(mapped_agent_id, f"Error during execution: {str(e)}"):
                    pass
                elif app_state["execution_tree"]:
                    app_state["execution_tree"][0]["status"] = "error"
                    app_state["execution_tree"][0]["content"] = f"Error during execution: {str(e)}\n\n{error_detail}"
                app_state["execution_tree"].append({
                    "id": "error",
                    "name": f"Process Error{(' - ' + agent_name) if agent_name else ''}",
                    "status": "error",
                    "content": f"Error during execution: {str(e)}\n\n{error_detail}",
                    "children": [],
                    "timestamp": time.time()
                })
        # Immediate broadcast of error state
        if MAIN_EVENT_LOOP and not MAIN_EVENT_LOOP.is_closed():
            try:
                asyncio.run_coroutine_threadsafe(_broadcast_status_locked_unlocked(), MAIN_EVENT_LOOP)
            except Exception:
                pass

# Run metrics removed: previously instrumentation helpers & /metrics/runs endpoint


@app.get("/", response_class=HTMLResponse)
async def read_root():
    from datetime import date
    template = jinja_env.get_template("index.html")
    today_str = date.today().isoformat()
    return template.render(app_state=app_state, default_date=today_str)

@app.get("/config/providers")
async def list_providers():
    """Return provider + model metadata for dynamic UI population."""
    providers = get_providers()
    # Reshape to simpler JSON for frontend: {providers: [{key, display_name, models:{quick: [...], deep: [...]}}]}
    simplified = []
    for p in providers:
        simplified.append({
            "key": p["key"],
            "display_name": p["display_name"],
            "models": p.get("models", {}),
        })
    return {"providers": simplified}

@app.post("/start", response_class=HTMLResponse)
async def start_process(
    background_tasks: BackgroundTasks,  # kept for backward compat; no longer used for long task
    company_symbol: str = Form(...),
    llm_provider: str = Form(...), 
    quick_think_llm: str = Form(...),
    deep_think_llm: str = Form(...),
    max_debate_rounds: int = Form(...),
    cost_per_trade: float = Form(...),
    analysis_date: str = Form(...),
    position_status: str = Form("none"),
    current_stop_loss: str | None = Form(None),
    current_take_profit: str | None = Form(None)
):
    # Check if all required environment variables are set
    missing_vars = [var for var in required_env_vars if not os.getenv(var)]
    if missing_vars:
        app_state["overall_status"] = "error"
        app_state["execution_tree"] = [{
            "id": "error",
            "name": "Configuration Error",
            "status": "error",
            "content": f"Missing required environment variables: {', '.join(missing_vars)}. Please check .env.example file.",
            "children": [],
            "timestamp": time.time()
        }]
        template = jinja_env.get_template("_partials/left_panel.html")
        return template.render(tree=app_state["execution_tree"], app_state=app_state)

    # Shared validation & normalization logic
    position_status = (position_status or "none").lower()
    if position_status not in ("none", "long", "short"):
        position_status = "none"

    def _parse_level(val: str | None):
        if val is None or val == "":
            return None
        try:
            f = float(val)
            if f <= 0:
                return None
            return f
        except ValueError:
            return None

    initial_stop_loss = _parse_level(current_stop_loss)
    initial_take_profit = _parse_level(current_take_profit)
    if position_status == "none":
        initial_stop_loss = None
        initial_take_profit = None

    config_payload = {
        "llm_provider": llm_provider,
        "quick_think_llm": quick_think_llm,
        "deep_think_llm": deep_think_llm,
        "max_debate_rounds": max_debate_rounds,
        "cost_per_trade": cost_per_trade,
        "analysis_date": analysis_date,
        "user_position": position_status,
        "initial_stop_loss": initial_stop_loss,
        "initial_take_profit": initial_take_profit
    }

    if ENABLE_MULTI_RUN:
        # Multi-run path: create run in manager and start thread
        from tradingagents.utils.results import create_run_results_dirs
        try:
            # Pass placeholder results path (actual directory built inside run)
            run_id = run_manager.create_run(company_symbol, results_path="<pending>")
        except RuntimeError as e:
            raise HTTPException(status_code=429, detail=str(e))
        # Initialize execution tree
        run_manager.update_run(run_id, execution_tree=initialize_complete_execution_tree(), status="in_progress")
        worker = threading.Thread(target=run_trading_process, args=(company_symbol, config_payload, run_id), daemon=True)
        worker.start()
        run_manager.set_thread(run_id, worker)
        template = jinja_env.get_template("_partials/left_panel.html")
        # Render legacy template with first run's tree for backward compatibility
        # (Front-end upgrade will consume multi-run endpoints later)
        return template.render(tree=run_manager.get_run(run_id).get("execution_tree"), app_state={"overall_status": "in_progress", "overall_progress": 0})
    else:
        with app_state_lock:
            if app_state["process_running"]:
                template = jinja_env.get_template("_partials/left_panel.html")
                return template.render(tree=app_state["execution_tree"], app_state=app_state)
            app_state["process_running"] = True
            app_state["company_symbol"] = company_symbol
            app_state["overall_status"] = "in_progress"
            app_state["overall_progress"] = 5
            app_state["config"] = config_payload
            app_state["execution_tree"] = initialize_complete_execution_tree()
        worker = threading.Thread(target=run_trading_process, args=(company_symbol, config_payload), daemon=True)
        worker.start()
        template = jinja_env.get_template("_partials/left_panel.html")
        return template.render(tree=app_state["execution_tree"], app_state=app_state)

@app.get("/status", response_class=HTMLResponse)
async def get_status():
    with app_state_lock:
        template = jinja_env.get_template("_partials/left_panel.html")
        return template.render(tree=app_state["execution_tree"], app_state=app_state)

# =============================================================
# Multi-Run REST API (JSON) – ENABLE_MULTI_RUN flag required
# (Hoisted to module level so routes are always registered)
# =============================================================
TICKER_VALIDATION_REGEX = re.compile(r"^[A-Za-z0-9\.]{1,15}$")
MAX_TICKERS_PER_REQUEST = int(os.getenv("MAX_TICKERS_PER_REQUEST", "10"))

def _validate_tickers(raw: str) -> list[str]:
    symbols = [s.strip().upper() for s in raw.split(',') if s.strip()]
    if not symbols:
        raise HTTPException(status_code=400, detail="No tickers provided")
    if len(symbols) > MAX_TICKERS_PER_REQUEST:
        raise HTTPException(status_code=400, detail=f"Maximum {MAX_TICKERS_PER_REQUEST} tickers allowed per request")
    bad = [s for s in symbols if not TICKER_VALIDATION_REGEX.match(s)]
    if bad:
        raise HTTPException(status_code=400, detail=f"Invalid ticker(s): {', '.join(bad)}")
    return symbols

@app.post("/start-multi")
async def start_multi(
    company_symbols: str = Form(...),
    llm_provider: str = Form(...),
    quick_think_llm: str = Form(...),
    deep_think_llm: str = Form(...),
    max_debate_rounds: int = Form(...),
    cost_per_trade: float = Form(...),
    analysis_date: str = Form(...),
    position_status: str = Form("none"),
    current_stop_loss: str | None = Form(None),
    current_take_profit: str | None = Form(None)
):
    if not ENABLE_MULTI_RUN:
        raise HTTPException(status_code=400, detail="Multi-run feature disabled. Set ENABLE_MULTI_RUN=1 to enable.")

    symbols = _validate_tickers(company_symbols)
    position_status = (position_status or "none").lower()
    if position_status not in ("none", "long", "short"):
        position_status = "none"

    def _parse_level(val: str | None):
        if val is None or val == "":
            return None
        try:
            f = float(val)
            if f <= 0:
                return None
            return f
        except ValueError:
            return None

    initial_stop_loss = _parse_level(current_stop_loss)
    initial_take_profit = _parse_level(current_take_profit)
    if position_status == "none":
        initial_stop_loss = None
        initial_take_profit = None

    config_payload = {
        "llm_provider": llm_provider,
        "quick_think_llm": quick_think_llm,
        "deep_think_llm": deep_think_llm,
        "max_debate_rounds": max_debate_rounds,
        "cost_per_trade": cost_per_trade,
        "analysis_date": analysis_date,
        "user_position": position_status,
        "initial_stop_loss": initial_stop_loss,
        "initial_take_profit": initial_take_profit
    }

    run_records = []
    for sym in symbols:
        try:
            run_id = run_manager.create_run(sym, results_path="<pending>")
        except RuntimeError as e:
            return JSONResponse(status_code=429, content={
                "error": str(e),
                "created_runs": run_records
            })
        run_manager.update_run(run_id, execution_tree=initialize_complete_execution_tree(), status="in_progress")
        worker = threading.Thread(target=run_trading_process, args=(sym, config_payload, run_id), daemon=True)
        worker.start()
        run_manager.set_thread(run_id, worker)
        run_records.append({"run_id": run_id, "ticker": sym})

    return {"runs": run_records, "count": len(run_records)}

@app.get("/runs")
async def list_runs(status: str | None = None):
    if not ENABLE_MULTI_RUN:
        return {"runs": []}
    runs = run_manager.list_runs(summary_only=True)
    if status:
        status = status.lower()
        runs = [r for r in runs if r["status"].lower() == status]
    return {"runs": runs, "count": len(runs)}

@app.get("/runs/{run_id}/status")
async def run_status(run_id: str):
    if not ENABLE_MULTI_RUN:
        raise HTTPException(status_code=400, detail="Multi-run feature disabled")
    run = run_manager.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return {k: run[k] for k in ("run_id","ticker","status","overall_progress","error","created_at","updated_at")}

@app.get("/runs/{run_id}/tree")
async def run_tree(run_id: str):
    if not ENABLE_MULTI_RUN:
        raise HTTPException(status_code=400, detail="Multi-run feature disabled")
    run = run_manager.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return {"run_id": run_id, "execution_tree": run.get("execution_tree", [])}

@app.get("/runs/{run_id}/decision")
async def run_decision(run_id: str):
    if not ENABLE_MULTI_RUN:
        raise HTTPException(status_code=400, detail="Multi-run feature disabled")
    run = run_manager.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    fd = run.get("final_decision")
    if fd is None:
        return JSONResponse(status_code=404, content={"error": "Decision not available yet"})
    # Build markdown view if structured enriched form
    if isinstance(fd, dict) and fd.get("version") == 1:
        risk = fd.get("risk_metrics", {})
        conf = fd.get("confidence", {})
        md_lines = ["### Decision Summary", f"**Summary:** {fd.get('summary','')}" ]
        if fd.get("action"):
            md_lines.append(f"**Action:** `{fd['action']}`")
        if any(risk.get(k) for k in ("stop_loss","take_profit","reward_risk_ratio")):
            md_lines.append("**Risk Metrics:**")
            if risk.get("stop_loss"): md_lines.append(f"- Stop Loss: {risk['stop_loss']}")
            if risk.get("take_profit"): md_lines.append(f"- Take Profit: {risk['take_profit']}")
            if risk.get("reward_risk_ratio") is not None: md_lines.append(f"- Reward/Risk: {risk['reward_risk_ratio']}")
        if conf.get("score") is not None:
            md_lines.append(f"**Confidence:** {conf['score']} (basis: {conf.get('basis','')})")
        if fd.get("rationale"):
            md_lines.append("**Rationale:**")
            for r in fd["rationale"]:
                md_lines.append(f"- {r}")
        md_lines.append("\n#### Raw Decision\n")
        md_lines.append(fd.get("raw", ""))
        md_source = "\n".join(md_lines)
    else:
        md_source = fd if isinstance(fd, str) else str(fd)
    html = render_markdown(md_source)
    return {"run_id": run_id, "final_decision": fd, "markdown": md_source, "html": html}

@app.get("/runs/{run_id}/logs")
async def run_logs(
    run_id: str,
    severity: str | None = None,
    sources: str | None = None,
    q: str | None = None,
    after_seq: int | None = None,
    limit: int = 200,
):
    if not ENABLE_MULTI_RUN:
        raise HTTPException(status_code=400, detail="Multi-run feature disabled")
    if not ENABLE_LOG_STREAM:
        raise HTTPException(status_code=400, detail="Log streaming disabled")
    run = run_manager.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    # Parse severity parameter: either threshold (single) or explicit list comma-separated
    severity_set = None
    min_sev = None
    if severity:
        if "," in severity:
            severity_set = set([s.strip().upper() for s in severity.split(",") if s.strip()])
        else:
            min_sev = severity.strip().upper()
    source_set = set([s.strip() for s in sources.split(",") if s.strip()]) if sources else None
    try:
        lim = min(max(1, int(limit)), 500)
    except ValueError:
        lim = 200
    entries, last_seq, total_seq = _filter_logs(
        run_id,
        min_severity=min_sev,
        severity_set=severity_set,
        sources=source_set,
        q=q,
        after_seq=after_seq,
        limit=lim,
    )
    return {
        "run_id": run_id,
        "entries": entries,
        "returned": len(entries),
        "last_seq": last_seq,
        "total_seq": total_seq,
    }

@app.get("/runs/{run_id}/logs/download")
async def download_run_logs(run_id: str):
    if not ENABLE_MULTI_RUN:
        raise HTTPException(status_code=400, detail="Multi-run feature disabled")
    if not ENABLE_LOG_STREAM:
        raise HTTPException(status_code=400, detail="Log streaming disabled")
    run = run_manager.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    snap = snapshot_run_logs(run_id) or {"entries": [], "seq": 0}
    lines = [f"# run_id={run_id} generated_at={time.strftime('%Y-%m-%dT%H:%M:%S')} entries={snap['seq']}"]
    for e in snap["entries"]:
        agent_part = f" [{e['agent_id']}]" if e.get("agent_id") else ""
        lines.append(f"[{e.get('iso')}] [{e.get('severity')}] [{e.get('source')}]" + agent_part + f" {e.get('message')}")
    content = "\n".join(lines)
    return HTMLResponse(content, media_type="text/plain")

@app.post("/runs/{run_id}/cancel")
async def cancel_run(run_id: str):
    if not ENABLE_MULTI_RUN:
        raise HTTPException(status_code=400, detail="Multi-run feature disabled")
    ok = run_manager.cancel_run(run_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Run not found or already finished")
    return {"run_id": run_id, "status": "canceled"}


@app.get("/status-updates")
async def get_status_updates():
    """Legacy endpoint for polling (kept as fallback)."""
    status_updates = {}
    def extract_status_info(items):
        for item in items:
            status_updates[item["id"]] = {
                "status": item["status"],
                "status_icon": get_status_icon(item["status"])
            }
            if item.get("children"):
                extract_status_info(item["children"])
    with app_state_lock:
        extract_status_info(app_state.get("execution_tree", []))
        return JSONResponse({
            "status_updates": status_updates,
            "overall_progress": app_state.get("overall_progress", 0),
            "overall_status": app_state.get("overall_status", "idle")
        })

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, run_id: str | None = None, patch: int | None = 0):
    """Realtime channel supporting both legacy single-run and multi-run modes.

    Query parameter optional: ?run_id=<id>
      - If provided (and ENABLE_MULTI_RUN), server streams focused updates for that run.
      - If omitted in multi-run mode, an aggregate feed of all runs is sent.
    """
    await manager.connect(websocket)
    try:
        if ENABLE_MULTI_RUN:
            if run_id:
                run = run_manager.get_run(run_id)
                if not run:
                    await websocket.send_json({"type": "error", "message": "Run not found"})
                    return
                # Focused init payload
                tree = run.get("execution_tree", [])
                patches_enabled = ENABLE_WS_PATCHES and patch == 1
                if patches_enabled:
                    # Register base snapshot (seq 0)
                    _register_full_snapshot(run_id, tree)

                @app.get("/metrics/concurrency")
                async def metrics_concurrency():
                    """Expose concurrency limiter snapshot (global/provider/model usage)."""
                    try:
                        from tradingagents.utils.concurrency_limiter import limiter
                    except Exception:
                        return {"error": "limiter module unavailable"}
                    return limiter.snapshot()
                await websocket.send_json({
                    "type": "init_run",
                    "run_id": run_id,
                    "ticker": run["ticker"],
                    "status": run["status"],
                    "overall_progress": run["overall_progress"],
                    "execution_tree": tree,
                    "patches": bool(patches_enabled),
                    "seq": 0 if patches_enabled else None,
                    "log_stream": bool(ENABLE_LOG_STREAM),
                })
            else:
                # Aggregate init
                runs = run_manager.list_runs(summary_only=True)
                await websocket.send_json({
                    "type": "init_all",
                    "runs": runs
                })
        else:
            with app_state_lock:
                init_payload = {
                    "type": "init",
                    "execution_tree_html": jinja_env.get_template("_partials/left_panel.html").render(tree=app_state.get("execution_tree", []), app_state=app_state),
                    "overall_progress": app_state.get("overall_progress", 0),
                    "overall_status": app_state.get("overall_status", "idle"),
                }
            await websocket.send_json(init_payload)

        while True:
            data = await websocket.receive_json()
            action = data.get("action")
            if action == "ping":
                await websocket.send_json({"type": "pong"})
            elif action == "get_content":
                item_id = data.get("item_id")
                if not item_id:
                    await websocket.send_json({"type": "error", "message": "item_id required"})
                    continue
                if ENABLE_MULTI_RUN and run_id:
                    run = run_manager.get_run(run_id)
                    if not run:
                        await websocket.send_json({"type": "error", "message": "Run not found"})
                        continue
                    item = find_item_in_tree(item_id, run.get("execution_tree", []))
                else:
                    with app_state_lock:
                        item = find_item_in_tree(item_id, app_state.get("execution_tree", []))
                if item:
                    html = jinja_env.get_template("_partials/right_panel.html").render(item=item, content=item.get("content", "No content available."))
                    await websocket.send_json({"type": "content", "item_id": item_id, "html": html})
                else:
                    await websocket.send_json({"type": "error", "message": f"Item {item_id} not found"})
            elif action == "resync":
                # Client requests a full snapshot due to detected patch sequence gap.
                if not (ENABLE_MULTI_RUN and run_id and ENABLE_WS_PATCHES):
                    await websocket.send_json({"type": "error", "message": "Resync unsupported in this mode"})
                    continue
                run = run_manager.get_run(run_id)
                if not run:
                    await websocket.send_json({"type": "error", "message": "Run not found"})
                    continue
                tree = run.get("execution_tree", []) or []
                # Refresh backend snapshot so future diffs are from this authoritative state
                current_seq = _refresh_snapshot(run_id, tree)
                await websocket.send_json({
                    "type": "run_snapshot",
                    "run_id": run_id,
                    "seq": current_seq,
                    "status": run.get("status"),
                    "overall_progress": run.get("overall_progress"),
                    "execution_tree": tree,
                })
            elif action == "log_dump":
                # Client explicitly requests current log buffer snapshot
                if not (ENABLE_MULTI_RUN and run_id and ENABLE_LOG_STREAM):
                    await websocket.send_json({"type": "error", "message": "Log dump unsupported in this mode"})
                    continue
                snap = snapshot_run_logs(run_id) or {"lines": [], "seq": 0}
                await websocket.send_json({
                    "type": "log_snapshot_run",
                    "run_id": run_id,
                    "entries": snap["entries"],
                    "seq": snap["seq"],
                })
            else:
                await websocket.send_json({"type": "ack", "received": action})
    except WebSocketDisconnect:
        manager.disconnect_sync(websocket)
    except Exception as e:
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
        manager.disconnect_sync(websocket)

def get_status_icon(status: str) -> str:
    """Get the status icon for a given status."""
    if status == 'completed':
        return '✅'
    elif status == 'in_progress':
        return '⏳'
    elif status == 'error':
        return '❌'
    else:
        return '⏸️'

def find_item_in_tree(item_id: str, tree: list) -> Dict[str, Any] | None:
    """Recursively searches the execution tree for an item by its ID."""
    for item in tree:
        if item["id"] == item_id:
            return item
        if item["children"]:
            found_child = find_item_in_tree(item_id, item["children"])
            if found_child:
                return found_child
    return None

@app.get("/content/{item_id}", response_class=HTMLResponse)
async def get_item_content(item_id: str):
    """Legacy single-run content fetch. Also resolve synthetic *_messages/_report if present."""
    # If the item itself is a real leaf node (id ends with _messages/_report) and exists in tree, we will serve it directly.
    base_id = None
    kind = None
    if item_id.endswith("_messages"):
        kind = "messages"
    elif item_id.endswith("_report"):
        kind = "report"
    with app_state_lock:
        tree = app_state["execution_tree"]
        # Direct attempt: does the exact item_id exist already (real leaf)?
        direct_item = find_item_in_tree(item_id, tree)
        if direct_item and kind:
            content_text = direct_item.get("content", "No content available.")
            template = jinja_env.get_template("_partials/right_panel.html")
            return template.render(item=direct_item, content=content_text)
        # Fallback: treat as synthetic derived from its agent
        base_id = item_id[:-9] if kind == 'messages' else (item_id[:-7] if kind == 'report' else None)
        target_id = base_id or item_id
        agent_or_item = find_item_in_tree(target_id, tree)
        if not agent_or_item:
            return HTMLResponse(content="<p>Item not found.</p>", status_code=404)
        content_text = agent_or_item.get("content", "No content available.")
        if kind == 'messages' and isinstance(agent_or_item.get('messages'), str):
            content_text = agent_or_item['messages']
        elif kind == 'report' and isinstance(agent_or_item.get('report'), str):
            content_text = agent_or_item['report']
        synthetic = {
            "id": item_id,
            "name": f"{agent_or_item.get('name','')} {kind.title()}" if kind else agent_or_item.get('name',''),
            "status": agent_or_item.get("status", "pending"),
            "content": content_text,
            "children": [],
            "started_at": agent_or_item.get("started_at"),
            "ended_at": agent_or_item.get("ended_at"),
            "duration_ms": agent_or_item.get("duration_ms"),
        }
        template = jinja_env.get_template("_partials/right_panel.html")
        return template.render(item=synthetic, content=content_text)

@app.get("/runs/{run_id}/content/{item_id}", response_class=HTMLResponse)
async def get_run_item_content(run_id: str, item_id: str):
    """Run-scoped content fetch supporting synthetic *_messages / *_report leaf nodes.

    The client fabricates IDs like <agent_id>_messages or <agent_id>_report.
    We strip the suffix to locate the agent node, then select appropriate field.
    """
    run = run_manager.get_run(run_id) if ENABLE_MULTI_RUN else None
    if not run:
        return HTMLResponse(content="<p>Run not found.</p>", status_code=404)
    tree = run.get("execution_tree", []) or []
    kind = None
    if item_id.endswith('_messages'):
        kind = 'messages'
    elif item_id.endswith('_report'):
        kind = 'report'
    # First try direct leaf lookup (already present node)
    direct_item = find_item_in_tree(item_id, tree)
    if direct_item and kind:
        content_text = direct_item.get('content', 'No content available.')
        template = jinja_env.get_template('_partials/right_panel.html')
        return template.render(item=direct_item, content=content_text)
    # Fallback: derive from agent
    base_id = item_id[:-9] if kind == 'messages' else (item_id[:-7] if kind == 'report' else item_id)
    agent_item = find_item_in_tree(base_id, tree)
    if not agent_item:
        return HTMLResponse(content='<p>Item not found.</p>', status_code=404)
    content_text = agent_item.get('content', 'No content available.')
    if kind == 'messages' and isinstance(agent_item.get('messages'), str):
        content_text = agent_item['messages']
    elif kind == 'report' and isinstance(agent_item.get('report'), str):
        content_text = agent_item['report']
    synthetic = {
        'id': item_id,
        'name': f"{agent_item.get('name','')} {kind.title()}" if kind else agent_item.get('name',''),
        'status': agent_item.get('status', 'pending'),
        'content': content_text,
        'children': [],
        'started_at': agent_item.get('started_at'),
        'ended_at': agent_item.get('ended_at'),
        'duration_ms': agent_item.get('duration_ms'),
    }
    template = jinja_env.get_template('_partials/right_panel.html')
    return template.render(item=synthetic, content=content_text)

# To run this app:
# uvicorn webapp.main:app --reload
