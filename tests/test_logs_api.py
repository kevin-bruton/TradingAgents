import os
import time
import json
import threading
from fastapi.testclient import TestClient

# Ensure feature flags
os.environ.setdefault("ENABLE_MULTI_RUN", "1")
os.environ.setdefault("ENABLE_LOG_STREAM", "1")

from webapp.main import app, log_run, ENABLE_LOG_STREAM  # type: ignore
from tradingagents.utils.run_manager import run_manager

def _create_dummy_run(ticker="TEST"):
    run_id = run_manager.create_run(ticker, results_path="<pending>")
    run_manager.update_run(run_id, execution_tree=[], status="in_progress")
    return run_id

client = TestClient(app)


def test_logs_basic_filtering():
    if not ENABLE_LOG_STREAM:
        return  # skip if log streaming disabled
    run_id = _create_dummy_run()
    # Emit several severities
    log_run(run_id, "system init", severity="INFO", source="system")
    log_run(run_id, "debug detail", severity="DEBUG", source="system")
    log_run(run_id, "agent finished", severity="INFO", source="agent", agent_id="market_analyst")
    log_run(run_id, "warn condition", severity="WARN", source="system")
    log_run(run_id, "fatal crash", severity="ERROR", source="system")
    time.sleep(0.05)

    # Threshold INFO should exclude DEBUG
    resp = client.get(f"/runs/{run_id}/logs?severity=INFO")
    assert resp.status_code == 200
    data = resp.json()
    msgs = [e["message"] for e in data["entries"]]
    assert "debug detail" not in msgs
    assert "system init" in msgs
    assert any(m.startswith("fatal crash") for m in msgs)

    # Explicit list severity=DEBUG,ERROR should include debug + error only
    resp = client.get(f"/runs/{run_id}/logs?severity=DEBUG,ERROR")
    data = resp.json()
    msgs = [e["message"] for e in data["entries"]]
    assert "debug detail" in msgs
    assert "system init" not in msgs
    assert "fatal crash" in msgs

    # Source filter agent
    resp = client.get(f"/runs/{run_id}/logs?sources=agent")
    data = resp.json()
    msgs = [e["message"] for e in data["entries"]]
    assert msgs == ["agent finished"]

    # Query search
    resp = client.get(f"/runs/{run_id}/logs?q=warn")
    data = resp.json()
    msgs = [e["message"] for e in data["entries"]]
    assert msgs == ["warn condition"]


def test_logs_pagination_after_seq():
    if not ENABLE_LOG_STREAM:
        return
    run_id = _create_dummy_run("SEQ")
    for i in range(5):
        log_run(run_id, f"line {i}", severity="INFO", source="system")
    time.sleep(0.02)
    first = client.get(f"/runs/{run_id}/logs?limit=2").json()
    assert len(first["entries"]) == 2
    last_seq = first["entries"][-1]["seq"]
    nxt = client.get(f"/runs/{run_id}/logs?after_seq={last_seq}&limit=10").json()
    assert all(e["seq"] > last_seq for e in nxt["entries"])  # strictly greater


def test_logs_download_plain_text():
    if not ENABLE_LOG_STREAM:
        return
    run_id = _create_dummy_run("DL")
    log_run(run_id, "download test", severity="INFO", source="system")
    resp = client.get(f"/runs/{run_id}/logs/download")
    assert resp.status_code == 200
    assert "download test" in resp.text

