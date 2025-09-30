# Multi-Instrument (Simultaneous) Execution Architecture & Implementation Plan

> Goal: Extend current single-instrument TradingAgents execution (CLI + Web) to support concurrent, isolated runs for multiple tickers ("instruments") executing in parallel, each with independent state, progress tracking, logging, and persisted results.

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

### 4.1 `run_id` Format
`<TICKER>--<YYYY-MM-DD_HH.MM.SS>` e.g. `AAPL--2025-09-22_10.00.00` — sortable, human readable, collision resistant.

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

### 4.3 `RunManager` API
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
## 6. Results Persistence Enhancements

### 6.1 Directory Schema
Current: `results/<TICKER>/<YYYY-MM-DD_HH.MM(/_n)?>/`

Proposed (retain compatibility, add run id marker file):
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
## 7. Callback & Progress Handling

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
## 8. WebSocket Protocol Changes

### 8.1 Messages
| Type | When | Payload |
|------|------|---------|
| `init_all` | Client first connect (no filter) | `{ runs: { run_id: {ticker,status,overall_progress} } }` |
| `init` | Client connects with `run_id` | `{ run_id, execution_tree, overall_progress }` |
| `status_update` | Any run changes | `{ run_id, overall_progress, execution_tree (optional partial or full) }` |
| `final` | Run completes | `{ run_id, status:'completed', final_decision }` |
| `error` | Run errors | `{ run_id, status:'error', error }` |
| `canceled` | Run canceled | `{ run_id, status:'canceled' }` |

### 8.2 Subscription Filtering
`/ws?run_id=<id>` for a focused stream; no param = aggregate feed.

### 8.3 Backward Compatibility
If frontend still expects single-run shape, a compatibility mode can map the first active run to legacy DOM IDs (optional fallback – Phase 2).

---
## 9. REST API Additions

| Endpoint | Method | Purpose | Params |
|----------|--------|---------|--------|
| `/start-multi` | POST | Launch multiple runs | `company_symbols` (CSV), plus existing config fields |
| `/runs` | GET | List all runs | optional `status` filter |
| `/runs/{run_id}/status` | GET | Detailed state snapshot |  |
| `/runs/{run_id}/cancel` | POST | Cooperative cancel |  |
| `/runs/{run_id}/tree` | GET | Execution tree (full) |  |
| `/runs/{run_id}/decision` | GET | Final decision (if done) |  |

All responses JSON; errors use consistent structure `{ "error": "message" }`.

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
## 11. CLI Multi-Ticker Mode

### 11.1 New Option
`python -m cli.main --tickers AAPL,MSFT,NVDA --parallel 3`

### 11.2 Implementation
- Parse list; create thread pool with `min(len(symbols), parallel)`.
- Each worker instantiates its own `TradingAgentsGraph`.
- Shared console table updated every time a run yields progress (optional: use `rich.Live`).

### 11.3 Output Artifacts
Same persistence logic; show final summary table with decisions.

---
## 12. Concurrency & Rate Limiting

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
## 13. Cancellation Mechanism

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
## 15. Testing Strategy

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
## 16. Migration Steps (Incremental Delivery)
1. Introduce `RunManager` (no functional change yet).
2. Refactor single-run code to use run manager with exactly one run.
3. Add multi-run endpoints + WebSocket run_id support.
4. Implement frontend tab UI.
5. Add CLI parallel mode.
6. Enhance persistence with `RUN_ID` file.
7. Add cancellation + pruning.
8. Write tests & docs.

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
## 20. Enhancements
- Add streaming of "Messages" sections over WS instead of on-demand fetch.

---
## 21. Acceptance Criteria Checklist
- [ ] Multiple tickers submitted -> each run executes concurrently.
- [ ] Web UI shows a tab per run with independent progress bars updating in real time.
- [ ] All artifacts saved under `results/<TICKER>/<YYYY-MM-DD_HH.MM.SS>/`.
- [ ] REST: `/runs` lists all runs; detailed status endpoints function.
- [ ] WebSocket emits `status_update` + `final` per run.
- [ ] Cancellation sets status to `canceled` and stops further progress updates.
- [ ] Web UI gives option on each tab to cancel individual executions.
- [ ] Tests cover manager, concurrency, and persistence.

---
## 22. Glossary
- Instrument / Ticker: Stock symbol processed by a run.
- Run: One end-to-end propagation of the TradingAgents graph for a single instrument/date.
- Execution Tree: Structured representation of agent/tool phases and their statuses.

---
## 24. Ready for Implementation
This plan is designed to integrate with existing modules with minimal disruption while enabling scalable parallel analyses.
