# Multi-Instrument (Simultaneous) Execution Architecture & Implementation Plan

> Progress Status (updated)
> - ✅ Completed: RunManager core; results directory seconds + RUN_ID marker; webapp multi-run refactor; multi-run REST endpoints; WebSocket run_id support (aggregate + focused); cancellation mechanism; CLI parallel multi-ticker mode; global LLM concurrency semaphore; frontend tab UI with per-run cancel; REST & WebSocket integration tests; automatic pruning + results retention scheduler (with days-based retention variable); README & plan synchronization.
> - ✅ Completed (recent): WebSocket diff/patch optimization (status_patch_run) + resync recovery; decision rendering panel enrichment (final decision content & HTML in focused run tab).
> - ✅ Completed (new): Streaming message/tool log lines over WebSocket (ring buffer + incremental + snapshot recovery).
> - ✅ Completed (extended tests batch): Added automated coverage for status diff patch sequencing + resync snapshot, content append/replace patch logic, cancellation race (immediate + post in_progress), and UI smoke (config + tree injection markers). All tests passing.
> - ⏳ Pending: execution tree deeper nested tools; timed diff patches for timing-only deltas; content patch resync snapshot integration; enhanced decision panel (advanced sizing model & real risk analytics); provider/model-specific concurrency tiers; historical run index manifest; UI state persistence (tree expansion, active selection, config collapse memory); optional concurrency limiter snapshot unit test.
> - 💤 Deferred / Nice-to-Have: historical run index JSON.

> Goal: Extend current single-instrument TradingAgents execution (CLI + Web) to support concurrent, isolated runs for multiple tickers ("instruments") executing in parallel, each with independent state, progress tracking, logging, and persisted results.

---
## Roadmap (Prioritized Pending Work)

1. Execution Tree & UX Refinement (In Progress / Partial ✅)
  - ✅ Added richer per-node metadata: node_type (phase, agent, report, messages) + timing fields (started_at, ended_at, duration_ms).
  - ✅ Active in-progress node highlighting with CSS (.active-node) and canceled status icon (⛔).
  - ✅ Duration badge rendering in left panel (seconds) with live placeholder while running.
  - ⏳ Remaining: deeper nested tool/task nodes (if/when tool-level granularity added), phase-level timing aggregation & visualization, inline failure reason hover tooltips.
  - ⏳ Remaining: execution tree incremental patch diff to include only timing deltas (currently full patch covers status changes already).
2. Granular Content Patching (Initial ✅ / Further Optimization Pending)
  - ✅ Implemented incremental WebSocket `content_patch_run` messages for agent `_messages` and `_report` nodes.
  - ✅ Append vs replace detection (prefix comparison) reduces payload for growing logs.
  - ✅ Separate sequence tracking from status patching (`status_patch_run`).
  - ⏳ Remaining: integrate with run resync snapshot to include current content cache; compression/size metrics; fallback batching for very rapid appends.
  - 🎯 Target: future measurement of average payload reduction vs full snapshot baseline (>50% goal) – instrumentation not yet added.
3. Decision Panel Enrichment (Foundational ✅ / Advanced Pending)
  - ✅ Enriched decision schema (versioned) with: summary, action inference, risk_metrics (SL/TP/R/R), confidence heuristic, rationale extraction, raw text.
  - ✅ WebSocket & REST now deliver structured object plus rendered markdown + HTML.
  - ✅ Collapsible raw decision section + concise summary formatting.
  - ⏳ Remaining: real position sizing model, probabilistic confidence calibration, risk metric normalization (percentage vs absolute), highlighting deltas vs prior decision (future), UI componentization (badges, table layout) & accessible labels.
4. Provider / Model Concurrency Tiers (Phase 1 ✅ / Advanced Pending)
  - ✅ Layered limiter implemented: global (LLM_MAX_CONCURRENCY), provider + provider:model granular limits via `LLM_PROVIDER_LIMITS` (e.g. `openai:6,anthropic:3,openai:gpt-4o:2`).
  - ✅ Metrics endpoint `/metrics/concurrency` returns live snapshot (in-use vs limits).
  - ⏳ Remaining: adaptive tuning (dynamic lowering on 429s), per-provider retry backoff stats, hot-reload of limits without restart, UI surfacing in metrics panel.
5. Log Enhancements (✅ Completed)
  - Implemented structured, severity-tagged per-run log buffer (TRACE/DEBUG/INFO/WARN/ERROR) with ring buffer & sequence numbers.
  - WebSocket incremental streaming upgraded: `{type: "log_append_run", entries:[{seq,ts,iso,severity,source,agent_id,message}]}` plus snapshot support for gap recovery.
  - New REST endpoints:
    * `GET /runs/{run_id}/logs` – filtering (severity threshold or explicit list), source filtering, keyword search, pagination via `after_seq`.
    * `GET /runs/{run_id}/logs/download` – plain text export with header + formatted lines.
  - Frontend UI per-run log panel: severity selector (threshold), multi-select sources, search box, reload, download link, auto-scroll and live append.
  - Tests added (`tests/test_logs_api.py`) covering severity threshold & explicit list filtering, source filtering, keyword search, pagination, download export.
  - Future (optional): websocket server-side filtering subscription, color-coded severity styling, batching of rapid log bursts.
6. Extended Automated Tests
  - ✅ Implemented new targeted test modules:
    * `tests/test_status_patches.py` – status patch sequence increments, new node detection, resync snapshot (no seq bump), no-op stability.
    * `tests/test_content_patches.py` – append vs replace detection, multi-node sequencing, no-change stability.
    * `tests/test_cancellation_race.py` – immediate cancellation before progress & post in_progress transition idempotency.
    * `tests/test_ui_smoke.py` – index load + multi-run form + websocket script markers + feature flags.
  - ✅ Full suite passes (`uv run pytest -q`).
  - ⏳ Remaining (optional): concurrency limiter direct snapshot test; log streaming gap recovery end-to-end (currently indirectly covered by patch/core unit tests).
7. UI State Persistence
  - localStorage for config collapse state, last-active run, selected tree node, filter preferences.

Nice-to-Have (Lower Priority)
- Adaptive backoff telemetry & dynamic throttling.

Status Legend: (Planned) not started | (Design) under design spike | (Dev) in progress | (Done) complete.

---
## 1. Objectives & Non-Goals

### Objectives
- Allow a user (web + CLI) to launch N instrument analyses simultaneously.
- Maintain isolated execution graphs, logs, Markdown reports, and final decision artifacts per instrument.
- Provide real-time progress via WebSockets for each run without interference.
- Introduce a manageable Run Manager abstraction with lifecycle control (create, track, cancel, prune).
- Persist results using existing directory schema, enhanced to avoid collisions when runs start in the same minute.
- Expose REST + WebSocket APIs to list, inspect, and stream state for all active/finished runs.
- Provide frontend UI with tabs (or side panel) to switch between instruments.

### Non-Goals (Phase 1)
- Distributed execution across multiple machines.
- Automatic horizontal scaling / queue backpressure beyond a simple max concurrency limit.
- Advanced scheduling, prioritization, or resource-aware throttling (beyond simple semaphore).
- Live cancellation deep inside an LLM call (will be cooperative at safe checkpoints).

---
## 2. Current State Summary (Single Instrument)
- Global `app_state` (in `webapp/main.py`) holds: execution tree, progress, final decision, errors.
- WebSocket (`/ws`) broadcasts aggregated status updates for the single active run.
- Results directory creation handled via `tradingagents/utils/results.py` using ticker + timestamp.
- CLI performs one `TradingAgentsGraph.propagate()` at a time.

Pain points for multi-run:
- Global mutable state enforces single active run.
- WebSocket payload lacks run identity.
- File system collisions if two runs start in the same minute for the same ticker.

---
## 3. High-Level Architecture Changes

| Concern | Current | Target |
|---------|---------|--------|
| Run State | Single global dict | Per-run entry managed by `RunManager` |
| Identification | Implicit (only one) | Explicit `run_id` (UUID or time-based) |
| WebSocket | One stream | Broadcast multi-run updates, client can filter by `run_id` |
| Results Dir | `results/<TICKER>/<YYYY-MM-DD_HH.MM(_n)>` | Can keep current structure as different runs will be saved in different instrument directories, but add seconds in the date time signature, example: `results/<TICKER>/<YYYY-MM-DD_HH.MM.SS>` |
| Start Endpoint | `/start-process` single ticker | `/start-multi` for batch, still keep legacy |
| Frontend | Single execution tree | Tabbed interface; each tab subscribes to it own run updates |
| CLI | Sequential | Parallel (thread pool) or sequential option |

---
## 4. Run Identity & Data Structures

### 4.1 `run_id` Format  ✅ Implemented
Implemented variant: `<TICKER>--<YYYY-MM-DD_HH.MM.SS>--<short>` (short = 6 hex chars from UUID) e.g. `AAPL--2025-09-22_10.00.00--a1b2c3` — sortable, human readable, collision resistant even for same‑second launches.

### 4.2 In-Memory Representation
```python
RunState = {
  'run_id': str,
  'ticker': str,
  'status': 'pending' | 'in_progress' | 'completed' | 'error' | 'canceled',
  'overall_progress': int,            # 0..100
  'execution_tree': list,             # Mirrors existing structure
  'final_decision': dict | None,
  'error': str | None,
  'created_at': float,
  'updated_at': float,
  'thread': threading.Thread | None,
  'results_path': str,                # Base directory for artifacts
  'cancellation_flag': bool,
}
```

### 4.3 `RunManager` API  ✅ Implemented
```python
class RunManager:
  def create_run(ticker) -> run_id
  def set_thread(run_id, thread)
  def update_run(run_id, **fields)
  def get_run(run_id) -> RunState | None
  def list_runs(summary_only=True)
  def cancel_run(run_id) -> bool
  def prune(max_age_hours=24)
```
Thread safety via internal lock.

---
## 5. Lifecycle Flow

1. User submits batch (e.g., `AAPL,MSFT,NVDA`).
2. For each ticker:
   - `run_id = create_run()` (status `pending`).
   - Prepare per-run results directory; store path in state.
   - Start thread -> status `in_progress`.
3. Graph executes, invoking callbacks to update execution tree & progress.
4. On completion -> status `completed`, decision persisted.
5. On exception -> status `error`, message persisted.
6. Optional cancellation sets flag; graph checks before each major agent step.

---
## 6. Results Persistence Enhancements  ✅ Implemented

### 6.1 Directory Schema
Current: `results/<TICKER>/<YYYY-MM-DD_HH.MM(/_n)?>/`

Implemented (seconds precision + RUN_ID marker file provided when multi-run):
```
results/
  AAPL/
    2025-09-30_14.07/              # as before
      message_tool.log
      reports/...
```

### 6.2 Write Operations
- Reuse existing directory creation function.
- Append writes remain unchanged (per-run log handle context-managed).

### 6.3 Failure Handling
- If run fails early, still ensure directory + `error.log` capturing traceback.

---
## 7. Callback & Progress Handling  ✅ Core Complete / Refinements Pending
Foundational changes implemented: legacy `update_execution_state` replaced by per-run update closures (`make_update_callback`) writing into `RunManager` and broadcasting. Remaining refinement (pending): deeper execution tree metadata / per-node timing & richer tool node rendering.

### 7.1 Factory Pattern
Replace global update with factory returning closure over `run_id`.
```python
def make_update_callback(run_id):
    def _update(state_fragment: dict):
        # Merge partial state into execution_tree nodes
        run = run_manager.get_run(run_id)
        if not run: return
        # Initialize tree if empty
        if not run['execution_tree']:
            tree = initialize_complete_execution_tree()
            run_manager.update_run(run_id, execution_tree=tree)
        # Update nodes + recompute progress
        progress = compute_progress(run['execution_tree'])
        run_manager.update_run(run_id, overall_progress=progress, updated_at=time.time())
        broadcast_ws({...payload with run_id...})
    return _update
```

### 7.2 Progress Computation
Same logic as single-run; encapsulate into `compute_progress(tree)` helper.

---
## 8. WebSocket Protocol Changes  ✅ Implemented (Backend)
The server now supports both aggregate and focused subscriptions.

### 8.1 Implemented Message Types
| Type | Context | Example Shape |
|------|---------|---------------|
| `init_all` | First message when client connects with no `run_id` | `{ "type": "init_all", "runs": [ {"run_id":..., "ticker":..., "status":..., "overall_progress":...}, ... ] }` |
| `status_update_aggregate` | Periodic/batched updates reflecting all active runs | `{ "type": "status_update_aggregate", "runs": { "<run_id>": {"ticker":..., "status":..., "overall_progress":...}, ... } }` |
| `init_run` | First message when client connects with `?run_id=...` | `{ "type": "init_run", "run_id": "...", "execution_tree": [...], "overall_progress": 0 }` |
| `status_update_run` | Incremental updates for a focused run | `{ "type": "status_update_run", "run_id": "...", "overall_progress": 42, "status": "in_progress" }` |
| (implicit final) | Final state uses same `status_update_run` with `status` = `completed|error|canceled` plus `final_decision` if completed | `{ "type": "status_update_run", "run_id": "...", "status": "completed", "final_decision": {...}, "overall_progress":100 }` |

Note: The backend currently sends full execution tree only in `init_run` (initial snapshot). Future enhancement: diff/patch updates to reduce payload size.

### 8.2 Subscription Modes
- Aggregate: `GET /ws` (no params) → receives `init_all` then periodic `status_update_aggregate`.
- Focused: `GET /ws?run_id=<run_id>` → receives `init_run` then `status_update_run` events.

### 8.3 Backward Compatibility
Legacy single-run clients still function if they ignore unknown message types; multi-run feature is gated by `ENABLE_MULTI_RUN` so disabling it reverts to single-run semantics.

---
## 9. REST API Additions  ✅ Implemented

| Endpoint | Method | Purpose | Notes |
|----------|--------|---------|-------|
| `/start-multi` | POST (form) | Launch multiple runs | Accepts `company_symbols` CSV plus existing single-run form fields. Enforces `MAX_TICKERS_PER_REQUEST` & `MAX_PARALLEL_RUNS`. |
| `/runs` | GET | List summary of all runs | Returns array of run summaries (run_id, ticker, status, overall_progress, timestamps). Optional future: `?status=` filter. |
| `/runs/{run_id}/status` | GET | Lightweight status snapshot | Omits full execution tree for efficiency. |
| `/runs/{run_id}/tree` | GET | Full execution tree | Mirrors legacy single-run structure. |
| `/runs/{run_id}/decision` | GET | Final decision (404 until ready) | Includes processed signal / decision artifacts. |
| `/runs/{run_id}/cancel` | POST | Cooperative cancellation | Sets cancellation flag; thread observes at checkpoints. |

Error format: `{ "error": "<message>" }` with appropriate HTTP codes (404 unknown run, 400 validation, 429 concurrency limit, 202 for accepted cancellation).

---
## 10. Frontend (HTMX + Tabs)

### 10.1 UI Additions
- Modify config form: allow comma-separated symbols.
- After POST to `/start-multi`, dynamically create a tab bar:
```html
<div id="run-tabs" class="tabs">
  <!-- populated dynamically -->
</div>
<div id="run-panels">
  <!-- one panel per run_id -->
</div>
```

### 10.2 Tab Content Structure
Each panel contains:
- Summary header (ticker, run_id, status, progress bar).
- Execution tree view (same markup reused, namespaced IDs w/ `data-run-id`).
- Live logs (optional tail of `message_tool.log`).
- Final decision markdown render container.

### 10.3 WebSocket Client Logic
Pseudocode:
```js
const sockets = {}; // single ws reused if aggregate
const ws = new WebSocket(`/ws`); // no run_id => aggregate
ws.onmessage = ev => {
  const msg = JSON.parse(ev.data);
  switch(msg.type){
    case 'status_update': updateRunUI(msg.run_id, msg); break;
    case 'final': renderDecision(msg.run_id, msg.final_decision); break;
    case 'error': showError(msg.run_id, msg.error); break;
  }
};
```

### 10.4 Namespacing DOM IDs
Functions should construct element IDs like: `progress-${run_id}`, `tree-${run_id}`.

### 10.5 Progressive Enhancement
If JS disabled: fallback list of runs via periodic HTMX `hx-get="/runs" hx-trigger="every 5s"`.

---
## 11. CLI Multi-Ticker Mode  ✅ Implemented

### 11.1 New Option
`python -m cli.main --tickers AAPL,MSFT,NVDA --parallel 3`

### 11.2 Implementation
- Parse list; create thread pool with `min(len(symbols), parallel)`.
- Each worker instantiates its own `TradingAgentsGraph`.
- Shared console table updated every time a run yields progress (optional: use `rich.Live`).

### 11.3 Output Artifacts
Same persistence logic; show final summary table with decisions.

---
## 12. Concurrency & Rate Limiting  ✅ Core Complete / Tiered Limits Pending
Status: Overall max parallel runs (`MAX_PARALLEL_RUNS`) and a global LLM semaphore implemented. Pending: provider/model tier limits & adaptive backoff metrics surfacing.

### 12.1 Configurable Limits
Env var or config: `MAX_PARALLEL_RUNS` (default 5). If exceeded -> 429 JSON error.

### 12.2 LLM Throttling
A semaphore enforces an upper bound on how many concurrent LLM (or data) calls run across all simultaneous instrument executions. Each thread (one per run) must acquire before invoking the remote model; if the limit is reached, the thread blocks briefly instead of flooding the provider (reducing rate‑limit errors and cost spikes).

Key ideas:

Global limit: Single semaphore shared by all runs (e.g. LLM_MAX_CONCURRENCY=8).
Optional per‑provider / per‑model limits layered on top of (or instead of) the global one.
Always release in a finally block so failures don’t leak permits.
Integrate with retry: acquire once, run all retry attempts inside (prevents bursts on quick failures). If you want higher throughput, acquire per attempt instead—tradeoff between fairness and throughput.
Make it configurable (env var + config override). If unset -> unlimited (no semaphore path).
Provide a thin context manager to avoid boilerplate.
Avoid deadlocks: do not nest acquisitions (pass through a flag if already inside).

Global semaphore around `safe_invoke_llm` calls:
```python
LLM_CONCURRENCY = int(os.getenv('LLM_MAX_CONCURRENCY', '8'))
llm_semaphore = threading.Semaphore(LLM_CONCURRENCY)

def safe_invoke_llm(...):
  with llm_semaphore:
    return _call_llm(...)
```


---
## 13. Cancellation Mechanism  ✅ Implemented

### 13.1 API
`POST /runs/{run_id}/cancel` sets `cancellation_flag=True` and returns 202.

### 13.2 Cooperative Checks
Insert checks in main propagation loop / between major agent phases:
```python
if run_manager.is_canceled(run_id):
    raise RunCanceled()
```
Catch `RunCanceled` -> mark status `canceled`.

---
## 14. Error Handling & Resilience
- All thread targets wrapped in try/except; errors propagate to run state + WebSocket.
- WebSocket broadcaster resilient to dropped connections (log + continue).
- If memory leak concerns: add pruning of completed runs after configurable timeout.

---
## 15. Testing Strategy  ✅ Baseline Implemented / Extended Coverage Pending
Implemented baseline: Unit tests for `RunManager` (create, list, limit, cancel, prune), semaphore behavior, results directory uniqueness + RUN_ID marker, REST multi-run endpoints, WebSocket aggregate + focused flows, cancel path, regression of legacy single-run. Pending: automated verification for log streaming gap recovery, diff/patch resync edge cases, timeline metrics integrity, UI smoke tests, and concurrency race edge cases.

### 15.1 Unit Tests
- `tests/test_run_manager.py`: creation, update, cancellation.
- `tests/test_multi_results_dirs.py`: ensure RUN_ID file created and unique paths.

### 15.2 Integration Tests
- Start 3 runs; poll `/runs` until all `completed`.
- Validate each decision file exists in `reports/`.
- WebSocket: mock client capturing messages; assert each run_id sequence contains `status_update` then `final`.

### 15.3 Concurrency Edge Cases
- Launch > `MAX_PARALLEL_RUNS` -> assert rejection.
- Trigger cancellation mid-run.

### 15.4 Regression
- Single legacy `/start-process` still functions.

---
## 16. Migration Steps (Incremental Delivery) – Progress Tracking
| Step | Description | Status |
|------|-------------|--------|
| 1 | Introduce `RunManager` | ✅ Done |
| 2 | Refactor single-run code to use run manager (flag-ready) | ✅ Done |
| 3 | Multi-run REST endpoints + WebSocket run_id support | ✅ Done |
| 4 | Frontend tab UI | ✅ Done |
| 5 | CLI parallel mode | ✅ Done |
| 6 | Persistence enhancement with `RUN_ID` file | ✅ Done |
| 7 | Cancellation + pruning | ✅ Done (helper + background scheduler + retention) |
| 8 | Tests & docs | ✅ Done (unit + integration tests; docs updated; plan synchronized) |

---
## 17. Rollback Plan
- Feature guarded by env flag `ENABLE_MULTI_RUN=1`.
- If instability occurs, disable flag -> system reverts to single-run behavior using first active run only.

---
## 18. Documentation Updates
- README: Add section "Multi-Instrument Execution" with usage examples.
- New doc (this file) linked from README and CONTRIBUTING.
- API examples for `/start-multi`, WebSocket usage.

---
## 19. Security & Isolation Considerations
- Input validation: sanitize ticker list (alphanumeric + optional dot).
- Prevent path traversal by controlling directory structure centrally.
- Limit max tickers per request (e.g., 10) to prevent accidental overload.

---
## 20. Enhancements & Retention

### 20.1 Automatic Pruning & Retention  ✅ Implemented
- Background daemon thread runs every `RUN_PRUNE_INTERVAL_SECONDS` (default 300s).
- In-memory run states older than `RUN_MAX_AGE_HOURS` are removed.
- Results directory retention rules:
  * Keep newest `RUN_RESULTS_MAX_PER_TICKER` (default 20) per ticker.
  * Remove directories older than `RUN_RESULTS_MAX_AGE_DAYS` (default 7) unless run still active.
  * Set `RUN_RESULTS_MAX_AGE_DAYS=0` to disable ALL deletions (count & age).
  * Legacy `RUN_RESULTS_MAX_AGE_HOURS` env is auto-converted (ceiling) if new var unset.

### 20.2 Recently Completed
- WebSocket diff/patch optimization: incremental `status_patch_run` messages (changed node statuses + seq) plus full snapshot on init.
- Resync protocol: client detects sequence gaps -> sends `{action:"resync"}`; server responds with `run_snapshot` restoring authoritative state; future patches resume from current seq.

### 20.3 Recently Completed (Decision Enrichment)
- Decision panel enrichment over WebSocket: include `final_decision` (structured) & rendered HTML/markdown when run completes.

### 20.3.1 Notes
- Implemented by augmenting `status_update_run` payload once run enters a terminal state (completed/error/canceled).
- Frontend injects sanitized `decision_html` into `.run-decision` per run tab.
- Idempotent: repeated terminal updates do not duplicate content.

### 20.4 Future Candidates (Revised)
- Execution tree deep detail view (expandable agent/tool subnodes with richer metadata).
- Decision panel enrichment (structured risk metrics, position delta rationale, confidence bands).
- Phase timeline / Gantt visualization leveraging captured phase durations.
- Granular patch streaming for large report/message content (reduce payload size >50%).
- Artifact compression & run index manifest (fast dashboard load, archive older runs).
- Provider/model-specific concurrency tiers (prevent single provider saturation).
- Log severity tagging, filtering & search (INFO/WARN/ERROR + keyword highlight).
- UI state persistence (expanded nodes, active item, config panel state, selected run) via localStorage.
- Accessibility & keyboard navigation improvements (ARIA roles for tree & tabs).

---
## 21. Acceptance Criteria Checklist – Current Status
- [x] Multiple tickers submitted -> each run executes concurrently.
- [x] Web UI shows a tab per run with independent progress bars updating in real time.
- [x] All artifacts saved under `results/<TICKER>/<YYYY-MM-DD_HH.MM.SS>/` (seconds + RUN_ID marker)
- [x] REST: `/runs` lists all runs; detailed status endpoints function.
- [x] WebSocket emits aggregate + per-run updates (`init_all`, `status_update_aggregate`, `init_run`, `status_update_run`).
- [x] Cancellation sets status to `canceled` and stops further progress updates.
- [x] Web UI gives option on each tab to cancel individual executions.
- [x] Tests cover manager, concurrency (semaphore), persistence, and integration (REST + WebSocket).
- [x] Final decision auto-renders in focused run tab upon completion (WebSocket message with `decision_html`).
 - [x] Streaming log lines appear in UI within <1s (target) via `log_append_run` messages.
 - [x] Log snapshot (`log_snapshot_run`) available on gap (auto) or manual request (`log_dump`).
 - [x] Ring buffer per run enforces max lines (config `LOG_BUFFER_MAX_LINES`); memory bound respected.
 - [x] Resync gap detection for logs triggers snapshot request automatically.

---
## 22. Glossary
- Instrument / Ticker: Stock symbol processed by a run.
- Run: One end-to-end propagation of the TradingAgents graph for a single instrument/date.
- Execution Tree: Structured representation of agent/tool phases and their statuses.

---
## 24. Completed Task: Streaming Message / Tool Log Lines over WebSocket

### Rationale
Provide near real-time visibility into agent message flow and tool usage without requiring filesystem access, improving debugging and UX.

### Implemented Approach
1. Per-run in-memory ring buffer (deque) guarded by `_log_lock`; size configurable via `LOG_BUFFER_MAX_LINES` (default 250).
2. New env flag `ENABLE_LOG_STREAM=1` activates logging; otherwise code paths are inert.
3. Incremental broadcast on each append: `{type:"log_append_run", run_id, lines:[<line>], seq}` where `seq` is per-run monotonic.
4. Client requests initial snapshot right after `init_run` when `log_stream:true` ⇒ `{action:"log_dump"}` → server responds `{type:"log_snapshot_run", run_id, lines:[...], seq}`.
5. Sequence gap detection in browser triggers automatic `{action:"log_dump"}` and replaces buffer contents.
6. UI panel adds collapsible "Live Log" per run with auto-scroll (only if near bottom) to avoid jumpiness.
7. Hooks currently emit lines on agent report completion and final decision availability; easily extensible to finer-grained events.

### Edge Considerations & Handling
- Backpressure: Missed increments recovered via snapshot; no server-side queue growth beyond ring buffer.
- Memory: O(runs * max_lines * avg_line_length); bounded by deque.
- Security: Only server-generated summary lines emitted (no direct user content), minimizing sanitization concerns.

### Success Criteria (Met)
- Log lines visible in UI < 1s after write (WebSocket push).
- No unbounded memory growth (bounded deque).
- Graceful recovery after missed messages via snapshot (`log_snapshot_run`).
- Sequence integrity: monotonic per-run `seq`, gap ⇒ snapshot.
- Configurable ring buffer size.
- Optional enable flag gating feature.

### Planned Next
Focus shifts to "Execution Tree Deep Rendering Refinement" (nested message/report nodes with expand/collapse + potential `content_patch_run`) now that streaming logs are in place.
- Partial phases: if a run errors mid-phase, include elapsed time until error for that phase.
- Concurrency: guard metrics structure with same lock as RunManager where needed.

### Success Criteria
- Endpoint returns in <10ms for <500 stored runs.
- Phase duration averages update after each run completion.
- No exceptions under concurrent run creation/updates during metrics fetch.
- Basic test validates JSON schema & computed averages.

---
This plan remains the authoritative, evolving blueprint; sections above updated to reflect completion of diff/patch + resync + decision enrichment, and selection of the metrics endpoint as the next engineering focus.
