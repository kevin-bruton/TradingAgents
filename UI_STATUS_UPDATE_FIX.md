# UI Status Update Fix - Summary

## Problem
After starting the execution process, the status of nodes in the left panel menu items would update during execution, but would stop updating when the process finished (completed, errored, or canceled). The final status was not being reflected in the UI even though the reports had been generated and the process had finished.

**Additional Issue**: The fix initially only worked for the **active tab**. Inactive tabs (other runs not currently selected) still had the same problem.

## Root Cause

### Issue 1: Missing Final Broadcasts
The issue was in `/Users/kevin.bruton/repo2/TradingAgents/webapp/main.py`:

1. **During Execution**: The `make_update_callback()` function properly broadcasts status updates via WebSocket during the propagation phase. This callback is invoked by the graph during execution.

2. **After Execution Completes**: When the execution finishes (successfully, with error, or canceled), the code only updated the `run_manager` state but **never broadcast** the final status to connected WebSocket clients:
   - Line ~1471: `run_manager.update_run(run_id, status="completed", ...)` - no broadcast
   - Line ~1592: `run_manager.update_run(run_id, status="error", ...)` - no broadcast  
   - Line ~1453: `run_manager.update_run(run_id, status="canceled", ...)` - no broadcast

3. The `update_run()` method in `run_manager.py` only updates the in-memory state - it does NOT trigger any WebSocket broadcasts.

### Issue 2: Inactive Tabs Not Updating
The WebSocket system uses two types of broadcasts:
- **`status_update_run`**: Specific updates for one run (handled by active tab's focused connection)
- **`status_update_aggregate`**: Updates for ALL runs (handled by the global connection)

The initial fix only sent `status_update_run` messages, which only updated the active tab. Inactive tabs rely on the aggregate broadcast from `_broadcast_status_locked_unlocked()` to receive updates about all runs.

## Solution
Added explicit WebSocket broadcasts after each terminal state update, including **both** the specific run update AND the aggregate update for all tabs.

### 1. Completion Path (Line ~1477)
After `run_manager.update_run(run_id, status="completed", ...)`, added:
```python
async def _emit_final():
    run = run_manager.get_run(run_id)
    if not run:
        return
    payload = {
        "type": "status_update_run",
        "run_id": run_id,
        "status": "completed",
        "overall_progress": 100,
        "ticker": run["ticker"],
    }
    # Include final decision and patches if enabled
    if ENABLE_WS_PATCHES:
        seq, changed = _compute_patch(run_id, run.get("execution_tree", []))
        if changed:
            await manager.broadcast_json(patch_payload)
    await manager.broadcast_json(payload)
    # Also broadcast aggregate update to ensure ALL tabs (inactive ones too) get updated
    await _broadcast_status_locked_unlocked()
asyncio.run_coroutine_threadsafe(_emit_final(), MAIN_EVENT_LOOP)
```

### 2. Error Path (Line ~1599)
After `run_manager.update_run(run_id, status="error", ...)`, added:
```python
async def _emit_error():
    run = run_manager.get_run(run_id)
    if not run:
        return
    payload = {
        "type": "status_update_run",
        "run_id": run_id,
        "status": "error",
        "overall_progress": 100,
        "ticker": run["ticker"],
        "error": str(e),
    }
    # Include patches if enabled
    if ENABLE_WS_PATCHES:
        seq, changed = _compute_patch(run_id, run.get("execution_tree", []))
        if changed:
            await manager.broadcast_json(patch_payload)
    await manager.broadcast_json(payload)
    # Also broadcast aggregate update to ensure ALL tabs (inactive ones too) get updated
    await _broadcast_status_locked_unlocked()
asyncio.run_coroutine_threadsafe(_emit_error(), MAIN_EVENT_LOOP)
```

### 3. Cancellation Path (Line ~1454)
After `run_manager.update_run(run_id, status="canceled", ...)`, added:
```python
async def _emit_canceled():
    run = run_manager.get_run(run_id)
    if not run:
        return
    payload = {
        "type": "status_update_run",
        "run_id": run_id,
        "status": "canceled",
        "overall_progress": run["overall_progress"],
        "ticker": run["ticker"],
    }
    # Include patches if enabled
    if ENABLE_WS_PATCHES:
        seq, changed = _compute_patch(run_id, run.get("execution_tree", []))
        if changed:
            await manager.broadcast_json(patch_payload)
    await manager.broadcast_json(payload)
    # Also broadcast aggregate update to ensure ALL tabs (inactive ones too) get updated
    await _broadcast_status_locked_unlocked()
asyncio.run_coroutine_threadsafe(_emit_canceled(), MAIN_EVENT_LOOP)
```

## How It Works
1. When execution finishes, we now explicitly create broadcast messages with the final status
2. **First**, a specific `status_update_run` message is sent to all connected WebSocket clients
3. **Then**, an aggregate `status_update_aggregate` message is sent with status for ALL runs
4. The frontend JavaScript in `websocket.js` handles both message types:
   - `status_update_run`: Updates the specific run (line 47-48)
   - `status_update_aggregate`: Updates all runs including inactive tabs (line 38-45)
5. The `updateRunTab()` function in `runs.js` updates the UI with the final status
6. If patches are enabled, we also send final status patches to update individual node statuses

## Testing
To verify the fix works:
1. Start multiple trading agent executions (2 or more runs)
2. Switch to a different tab (make one run inactive)
3. Wait for the inactive run to complete
4. Verify that:
   - **Active tab**: Shows status as "(completed)" or "(error)", nodes update, progress bar shows 100%
   - **Inactive tabs**: Also show the correct final status without needing to click on them
   - All reports are accessible
   - Node statuses in the tree update correctly

## Related Files
- `/Users/kevin.bruton/repo2/TradingAgents/webapp/main.py` - Backend WebSocket broadcasting (FIXED)
- `/Users/kevin.bruton/repo2/TradingAgents/webapp/static/js/websocket.js` - Frontend message handling
- `/Users/kevin.bruton/repo2/TradingAgents/webapp/static/js/runs.js` - UI update functions
- `/Users/kevin.bruton/repo2/TradingAgents/tradingagents/utils/run_manager.py` - Run state management

## Date
2025-10-02 (Initial fix)
2025-10-03 (Updated to fix inactive tabs)
