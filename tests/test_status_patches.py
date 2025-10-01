import os, sys, importlib
import pytest

# Ensure feature flag enabled BEFORE importing webapp.main
os.environ['ENABLE_WS_PATCHES'] = '1'
os.environ.setdefault('ENABLE_CONTENT_PATCHES', '0')  # Not needed for these tests

# Force fresh import so conditional definitions are included
if 'webapp.main' in sys.modules:
    del sys.modules['webapp.main']
webapp_main = importlib.import_module('webapp.main')

# Convenience references (only present when ENABLE_WS_PATCHES=1 at import time)
_compute_patch = getattr(webapp_main, '_compute_patch')
_refresh_snapshot = getattr(webapp_main, '_refresh_snapshot')

@pytest.fixture(autouse=True)
def _clear_patch_state():
    # Reset internal patch tracking dict between tests to isolate sequences
    state_attr = getattr(webapp_main, '_run_patch_state', None)
    if state_attr is not None:
        state_attr.clear()
    yield
    if state_attr is not None:
        state_attr.clear()


def _make_tree(status_root='pending', child=None):
    tree = [{
        'id': 'root',
        'status': status_root,
        'children': []
    }]
    if child:
        tree[0]['children'].append(child)
    return tree


def test_initial_snapshot_no_patch():
    run_id = 'run_initial'
    seq, changed = _compute_patch(run_id, _make_tree())
    assert seq == 0
    assert changed == []  # first registration yields no patch

    # Second call with no changes still no patch, seq stays 0
    seq2, changed2 = _compute_patch(run_id, _make_tree())
    assert seq2 == 0
    assert changed2 == []


def test_status_patch_sequence_increments():
    run_id = 'run_seq'
    # Register
    _compute_patch(run_id, _make_tree(status_root='pending'))
    # Transition to in_progress
    seq1, changed1 = _compute_patch(run_id, _make_tree(status_root='in_progress'))
    assert seq1 == 1
    assert changed1 and changed1[0]['id'] == 'root'
    assert changed1[0]['status'] == 'in_progress'
    assert changed1[0]['status_icon'] == '⏳'

    # Transition to completed
    seq2, changed2 = _compute_patch(run_id, _make_tree(status_root='completed'))
    assert seq2 == 2
    assert changed2 and changed2[0]['status'] == 'completed'
    assert changed2[0]['status_icon'] == '✅'

    # No change -> no increment
    seq3, changed3 = _compute_patch(run_id, _make_tree(status_root='completed'))
    assert seq3 == 2
    assert changed3 == []


def test_new_node_registration_triggers_patch():
    run_id = 'run_new_node'
    _compute_patch(run_id, _make_tree())
    # Add a new child node -> should appear as changed
    child = {'id': 'child1', 'status': 'pending', 'children': []}
    seq, changed = _compute_patch(run_id, _make_tree(child=child))
    assert seq == 1
    assert any(c['id'] == 'child1' for c in changed)


def test_refresh_snapshot_no_seq_increment():
    run_id = 'run_resync'
    _compute_patch(run_id, _make_tree())  # register
    # Change root -> seq 1
    _compute_patch(run_id, _make_tree(status_root='in_progress'))
    # Add child -> seq 2
    child = {'id': 'child1', 'status': 'pending', 'children': []}
    _compute_patch(run_id, _make_tree(status_root='in_progress', child=child))

    # Simulate client detecting a gap and requesting a snapshot; server refreshes snapshot (no seq change)
    seq_before_refresh = 2
    seq_after_refresh = _refresh_snapshot(run_id, _make_tree(status_root='in_progress', child=child))
    assert seq_after_refresh == seq_before_refresh

    # Further change after refresh increments seq to 3
    child_completed = {'id': 'child1', 'status': 'completed', 'children': []}
    seq3, changed3 = _compute_patch(run_id, _make_tree(status_root='completed', child=child_completed))
    assert seq3 == 3
    # Both root or child could be reported (root status changed + child status changed). Ensure at least child status updated
    assert any(c['id'] == 'child1' and c['status'] == 'completed' for c in changed3)
