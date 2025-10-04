import time
from tradingagents.utils.run_manager import run_manager, RunManager, generate_run_id

def test_generate_run_id_format():
    rid = generate_run_id("AAPL")
    assert rid.startswith("AAPL--")
    parts = rid.split("--")
    assert len(parts) == 3
    # timestamp portion
    ts = parts[1]
    # Basic shape check YYYY-MM-DD_HH.MM.SS
    date_part, time_part = ts.split('_')
    assert len(date_part.split('-')) == 3
    hh, mm, ss = time_part.split('.')
    assert len(hh) == 2 and len(mm) == 2 and len(ss) == 2


def test_run_manager_create_and_list(tmp_path):
    mgr = RunManager(max_parallel=2)
    rid1 = mgr.create_run("AAPL", str(tmp_path / "a"))
    rid2 = mgr.create_run("MSFT", str(tmp_path / "b"))
    runs = mgr.list_runs(summary_only=True)
    assert len(runs) == 2
    assert any(r["run_id"] == rid1 for r in runs)
    assert any(r["run_id"] == rid2 for r in runs)


def test_run_manager_parallel_limit(tmp_path):
    mgr = RunManager(max_parallel=1)
    mgr.create_run("AAPL", str(tmp_path / "a"))
    try:
        mgr.create_run("MSFT", str(tmp_path / "b"))
        assert False, "Expected RuntimeError due to parallel limit"
    except RuntimeError:
        pass


def test_run_manager_cancel(tmp_path):
    mgr = RunManager(max_parallel=2)
    rid = mgr.create_run("AAPL", str(tmp_path / "a"))
    assert not mgr.is_canceled(rid)
    mgr.cancel_run(rid)
    assert mgr.is_canceled(rid)
    run = mgr.get_run(rid)
    assert run["status"] == "canceled"


def test_prune(tmp_path):
    mgr = RunManager(max_parallel=2)
    rid = mgr.create_run("AAPL", str(tmp_path / "a"))
    # Force old timestamp
    mgr.update_run(rid, _preserve_timestamp=True, updated_at=time.time() - 48 * 3600)
    removed = mgr.prune(max_age_hours=24)
    assert removed == 1


def test_execution_tree_metadata_timing(tmp_path):
    """Smoke test: ensure initialized tree nodes have instrumentation fields and that timing populates on status updates.

    We simulate a run by creating a run and then injecting an execution tree and modifying a node's status.
    """
    from webapp.main import initialize_complete_execution_tree
    mgr = RunManager(max_parallel=1)
    rid = mgr.create_run("AAPL", str(tmp_path / "a"))
    tree = initialize_complete_execution_tree()
    # Inject tree
    mgr.update_run(rid, execution_tree=tree)
    # Pick first phase & agent
    phase = tree[0]
    assert phase.get("node_type") == "phase"
    assert "started_at" in phase and phase["started_at"] is None
    agent = phase["children"][0]
    assert agent.get("node_type") == "agent"
    # Simulate timing by updating fields
    now = time.time()
    agent["started_at"] = now
    agent["ended_at"] = now + 0.05
    agent["duration_ms"] = int((agent["ended_at"] - agent["started_at"]) * 1000)
    agent["status"] = "completed"
    mgr.update_run(rid, execution_tree=tree)
    run = mgr.get_run(rid)
    # Ensure persisted
    a2 = run["execution_tree"][0]["children"][0]
    assert a2["duration_ms"] >= 0
