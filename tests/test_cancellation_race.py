import os, sys, importlib, time
import pytest

os.environ['ENABLE_MULTI_RUN'] = '1'
os.environ['ENABLE_WS_PATCHES'] = '0'
os.environ['ENABLE_CONTENT_PATCHES'] = '0'

if 'webapp.main' in sys.modules:
    del sys.modules['webapp.main']
main = importlib.import_module('webapp.main')
from tradingagents.utils.run_manager import run_manager

@pytest.fixture(autouse=True)
def clear_runs():
    for r in list(run_manager.list_runs(summary_only=False)):
        run_manager._runs.pop(r['run_id'], None)  # type: ignore[attr-defined]
    yield
    for r in list(run_manager.list_runs(summary_only=False)):
        run_manager._runs.pop(r['run_id'], None)  # type: ignore[attr-defined]


def test_immediate_cancellation_before_progress():
    run_id = run_manager.create_run(ticker='MSFT', results_path='results/MSFT/test')
    # Immediately cancel before any execution tree updates (simulating race)
    canceled = run_manager.cancel_run(run_id)
    assert canceled, 'Cancellation should succeed'
    run = run_manager.get_run(run_id)
    assert run['status'] == 'canceled'
    # Metrics removed: no run_start field expected
    # Ensure idempotency: second cancel returns False
    assert not run_manager.cancel_run(run_id)


def test_cancellation_after_in_progress_transition():
    run_id = run_manager.create_run(ticker='GOOG', results_path='results/GOOG/test')
    # Simulate worker marking in_progress quickly
    run_manager.update_run(run_id, status='in_progress')
    # Cancel right after
    run_manager.cancel_run(run_id)
    run = run_manager.get_run(run_id)
    assert run['status'] == 'canceled'
    # In this path run_start would have been set later by metrics update in real worker; we accept None here
    # Ensure cancellation flag is set
    assert run['cancellation_flag'] is True
