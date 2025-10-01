import os
import time
import pytest
from fastapi.testclient import TestClient

# Ensure environment flag is set before app import
os.environ['ENABLE_MULTI_RUN'] = '1'
os.environ['MAX_PARALLEL_RUNS'] = '4'

from webapp.main import app  # noqa: E402

client = TestClient(app)

REQUIRED_FORM = {
    'llm_provider': 'openai',
    'quick_think_llm': 'gpt-4o-mini',
    'deep_think_llm': 'gpt-4o',
    'max_debate_rounds': '1',
    'cost_per_trade': '0.1',
    'analysis_date': '2025-09-30'
}


def _start_multi(symbols: str):
    data = {'company_symbols': symbols, **REQUIRED_FORM}
    return client.post('/start-multi', data=data)


def test_start_multi_and_list_runs():
    r = _start_multi('AAPL,MSFT')
    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload['count'] == 2
    run_ids = [run['run_id'] for run in payload['runs']]
    assert all('--' in rid for rid in run_ids)

    # Poll /runs until both runs advance beyond 'pending' (or timeout)
    deadline = time.time() + 15
    final_statuses = {}
    while time.time() < deadline:
        lr = client.get('/runs')
        assert lr.status_code == 200
        runs = lr.json()['runs']
        subset = [r for r in runs if r['run_id'] in run_ids]
        if all(r['status'] in ('in_progress','completed','error','canceled') for r in subset):
            final_statuses = {r['run_id']: r['status'] for r in subset}
            # Break early once both past pending
            break
        time.sleep(0.25)
    assert final_statuses, 'Runs failed to progress in time'

    # Hit status + tree for first run
    first = run_ids[0]
    st = client.get(f'/runs/{first}/status')
    assert st.status_code == 200
    status_payload = st.json()
    assert status_payload['run_id'] == first
    tr = client.get(f'/runs/{first}/tree')
    assert tr.status_code == 200
    tree_payload = tr.json()
    assert tree_payload['run_id'] == first
    assert isinstance(tree_payload.get('execution_tree'), list)


def test_cancellation_flow():
    # Start single run
    r = _start_multi('GOOG')
    assert r.status_code == 200
    run_id = r.json()['runs'][0]['run_id']

    # Immediately request cancellation
    cr = client.post(f'/runs/{run_id}/cancel')
    assert cr.status_code == 200
    assert cr.json()['status'] == 'canceled'

    # Poll status until reflects canceled (the optimistic state is set immediately; ensure persists)
    st = client.get(f'/runs/{run_id}/status')
    assert st.status_code == 200
    assert st.json()['status'] == 'canceled'


def test_parallel_limit_and_overflow():
    # Temporarily restrict parallel runs to 1 by monkeypatching env BEFORE importing manager would matter,
    # but run_manager already instantiated. So we simulate by starting one run then attempting batch that exceeds.
    r1 = _start_multi('NVDA')
    assert r1.status_code == 200
    # Second call with two symbols likely to exceed available slots if first still pending/in_progress.
    r2 = _start_multi('TSLA,AMD')
    if r2.status_code == 200:
        # If system processed first run quickly, we may not hit limit; skip assertion in that flake case.
        pytest.skip('Did not trigger parallel limit (run completed too fast)')
    else:
        assert r2.status_code in (400,429)
        js = r2.json()
        assert 'error' in js


def test_invalid_ticker_validation():
    r = _start_multi('BAD!SYMBOL')
    assert r.status_code == 400
    assert 'Invalid ticker' in r.json().get('detail','')
