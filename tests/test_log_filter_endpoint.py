import pytest
from fastapi.testclient import TestClient
from webapp.main import app, ENABLE_MULTI_RUN

# These tests assume multi-run enabled; skip if not.
pytestmark = pytest.mark.skipif(not ENABLE_MULTI_RUN, reason="Multi-run feature disabled")

client = TestClient(app)

# NOTE: We don't have a fixture to create runs here; minimally assert 404 for unknown run and param parsing works.

def test_logs_unknown_run():
    r = client.get('/runs/does-not-exist/logs')
    assert r.status_code == 404

# If we had a run_manager fixture we could inject logs then assert filtering; placeholder structure for future expansion.
