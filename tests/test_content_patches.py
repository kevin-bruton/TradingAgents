import os, sys, importlib
import pytest

# Enable flags before import
os.environ['ENABLE_WS_PATCHES'] = '1'
os.environ['ENABLE_CONTENT_PATCHES'] = '1'

if 'webapp.main' in sys.modules:
    del sys.modules['webapp.main']
main = importlib.import_module('webapp.main')
_compute_content_patches = getattr(main, '_compute_content_patches')

@pytest.fixture(autouse=True)
def _clear_content_state():
    state = getattr(main, '_content_patch_state', None)
    if state is not None:
        state.clear()
    yield
    if state is not None:
        state.clear()


def _tree(content_a="Line1\n", content_b="Alpha\n"):
    return [
        {"id": "phase_a", "status": "in_progress", "children": [
            {"id": "agent_a_messages", "status": "in_progress", "children": [], "content": content_a}
        ]},
        {"id": "phase_b", "status": "pending", "children": [
            {"id": "agent_b_report", "status": "pending", "children": [], "content": content_b}
        ]},
    ]


def test_initial_registration_no_patches():
    seq, patches = _compute_content_patches('runX', _tree())
    assert seq == 0
    assert patches == []


def test_append_mode_detected():
    run_id = 'run_append'
    _compute_content_patches(run_id, _tree(content_a="A\n"))  # register
    # Append new text to messages node
    seq, patches = _compute_content_patches(run_id, _tree(content_a="A\nMore\n"))
    assert seq == 1
    assert len(patches) == 1
    p = patches[0]
    assert p['id'] == 'agent_a_messages'
    assert p['mode'] == 'append' and p['text'] == 'More\n'


def test_replace_mode_when_prefix_not_matching():
    run_id = 'run_replace'
    _compute_content_patches(run_id, _tree(content_a="Hello\n"))
    # Change to entirely different content (not a pure append)
    seq, patches = _compute_content_patches(run_id, _tree(content_a="Different Start\n"))
    assert seq == 1
    assert len(patches) == 1
    rp = patches[0]
    assert rp['mode'] == 'replace'
    assert 'content' in rp and rp['content'].startswith('Different')


def test_multiple_nodes_and_sequence_increment_once():
    run_id = 'run_multi'
    _compute_content_patches(run_id, _tree(content_a="AA\n", content_b="BB\n"))
    # Modify both nodes: one append, one replace
    seq, patches = _compute_content_patches(run_id, _tree(content_a="AA\nCC\n", content_b="Changed\n"))
    assert seq == 1
    ids = {p['id'] for p in patches}
    assert {'agent_a_messages', 'agent_b_report'} <= ids
    modes = {p['id']: p['mode'] for p in patches}
    # messages node appended, report replaced (prefix mismatch)
    assert modes['agent_a_messages'] == 'append'
    assert modes['agent_b_report'] == 'replace'


def test_no_change_no_seq_bump():
    run_id = 'run_no_change'
    _compute_content_patches(run_id, _tree())
    seq1, patches1 = _compute_content_patches(run_id, _tree())
    assert seq1 == 0 and patches1 == []
    # After an append sequence increments once; next identical call no bump
    _compute_content_patches(run_id, _tree(content_a="Line1\n"))  # baseline already
    seq2, patches2 = _compute_content_patches(run_id, _tree(content_a="Line1\nLine2\n"))
    assert seq2 == 1 and patches2
    seq3, patches3 = _compute_content_patches(run_id, _tree(content_a="Line1\nLine2\n"))
    assert seq3 == 1 and patches3 == []
