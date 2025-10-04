import os, sys, importlib
import re
from fastapi.testclient import TestClient

# Enable multi-run + patches + logs (simulate full feature set)
os.environ['ENABLE_MULTI_RUN'] = '1'
os.environ['ENABLE_WS_PATCHES'] = '1'
os.environ['ENABLE_CONTENT_PATCHES'] = '1'
os.environ['ENABLE_LOG_STREAM'] = '1'

if 'webapp.main' in sys.modules:
    del sys.modules['webapp.main']
main = importlib.import_module('webapp.main')
from tradingagents.utils.run_manager import run_manager

client = TestClient(main.app)


def test_index_page_loads_and_contains_expected_multi_run_elements():
    r = client.get('/')
    assert r.status_code == 200
    html = r.text
    # Smoke markers: configuration form + multi-run symbols input + execution tree container
    assert 'Multi-Run Configuration' in html
    assert 'multi_company_symbols' in html
    assert 'execution-tree-container' in html
    # Ensure websocket helper present
    assert 'function websocketUrl(' in html


def test_run_creation_and_internal_flags():
    run_id = run_manager.create_run(ticker='TSLA', results_path='results/TSLA/test')
    run = run_manager.get_run(run_id)
    assert run is not None
    # Confirm feature flag globals reflect expected truthiness
    assert getattr(main, 'ENABLE_WS_PATCHES') is True
    assert getattr(main, 'ENABLE_CONTENT_PATCHES') is True
    assert getattr(main, 'ENABLE_LOG_STREAM') is True
    # Execution tree initially empty
    assert run['execution_tree'] == []
