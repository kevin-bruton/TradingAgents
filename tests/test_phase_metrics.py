import os, sys, importlib, time
import pytest

# Enable multi-run & patches so metrics logic triggers on updates
os.environ['ENABLE_MULTI_RUN'] = '1'
os.environ['ENABLE_WS_PATCHES'] = '1'
os.environ['ENABLE_CONTENT_PATCHES'] = '0'

if 'webapp.main' in sys.modules:
    del sys.modules['webapp.main']
main = importlib.import_module('webapp.main')
_update_run_metrics = getattr(main, '_update_run_metrics')
PHASE_IDS = getattr(main, 'PHASE_IDS')
from tradingagents.utils.run_manager import run_manager

@pytest.fixture(autouse=True)
def clear_runs():
    for r in list(run_manager.list_runs(summary_only=False)):
        run_manager._runs.pop(r['run_id'], None)  # type: ignore[attr-defined]
    yield
    for r in list(run_manager.list_runs(summary_only=False)):
        run_manager._runs.pop(r['run_id'], None)  # type: ignore[attr-defined]


def _phase(id_, status, child_status=None):
    children = []
    if child_status is not None:
        children.append({'id': id_.replace('_phase','_agent'), 'status': child_status, 'children': []})
    return {'id': id_, 'status': status, 'children': children}


def test_phase_metrics_ordering_and_presence():
    # create_run returns a generated run_id
    run_id = run_manager.create_run(ticker='AAPL', results_path='results/AAPL/test')

    # Build initial execution tree: all phases pending
    tree = [_phase(pid, 'pending') for pid in PHASE_IDS]
    run_manager.update_run(run_id, execution_tree=tree)
    _update_run_metrics(run_id, tree)

    # Transition first phase to in_progress then completed (with child) to set start/end
    tree[0] = _phase(PHASE_IDS[0], 'in_progress', child_status='in_progress')
    run_manager.update_run(run_id, execution_tree=tree, status='in_progress')
    _update_run_metrics(run_id, tree)
    time.sleep(0.01)  # ensure timestamp differentiation
    tree[0] = _phase(PHASE_IDS[0], 'completed', child_status='completed')
    run_manager.update_run(run_id, execution_tree=tree)
    _update_run_metrics(run_id, tree)

    # Transition second phase through same
    tree[1] = _phase(PHASE_IDS[1], 'in_progress', child_status='in_progress')
    run_manager.update_run(run_id, execution_tree=tree)
    _update_run_metrics(run_id, tree)
    time.sleep(0.01)
    tree[1] = _phase(PHASE_IDS[1], 'completed', child_status='completed')
    run_manager.update_run(run_id, execution_tree=tree)
    _update_run_metrics(run_id, tree)

    run = run_manager.get_run(run_id)
    metrics = run.get('metrics', {})
    assert metrics.get('run_start') is not None, 'run_start should be set when status became in_progress'
    phases = metrics.get('phases', {})

    # Check first two phases have start & end, ordering correct; others may still be None
    for idx in (0,1):
        pid = PHASE_IDS[idx]
        pm = phases.get(pid)
        assert pm is not None, f'metrics entry missing for {pid}'
        assert pm['start'] is not None, f'start missing for {pid}'
        assert pm['end'] is not None, f'end missing for {pid}'
        assert pm['start'] <= pm['end'], f'start > end for {pid}'

    # Later phases should have placeholders but no start yet
    for pid in PHASE_IDS[2:]:
        pm = phases.get(pid)
        if pm:  # created lazily only when phase leaves pending
            assert not (pm['start'] or pm['end']), f'{pid} should not have timings yet'

    # Ensure different phases have non-identical timestamps (ordering signal)
    p0, p1 = phases[PHASE_IDS[0]], phases[PHASE_IDS[1]]
    assert p0['end'] <= p1['end'] or p0['start'] <= p1['start']
