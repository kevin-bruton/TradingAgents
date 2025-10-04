import os
import time
import json
import pytest
from fastapi.testclient import TestClient

os.environ['ENABLE_MULTI_RUN'] = '1'
os.environ['MAX_PARALLEL_RUNS'] = '4'

from webapp.main import app  # noqa: E402

client = TestClient(app)

FORM = {
    'llm_provider': 'openai',
    'quick_think_llm': 'gpt-4o-mini',
    'deep_think_llm': 'gpt-4o',
    'max_debate_rounds': '1',
    'cost_per_trade': '0.1',
    'analysis_date': '2025-09-30'
}


def start_runs(symbols):
    data = {'company_symbols': symbols, **FORM}
    r = client.post('/start-multi', data=data)
    assert r.status_code == 200
    return [x['run_id'] for x in r.json()['runs']]


def test_websocket_aggregate_and_focused():
    run_ids = start_runs('AAPL,MSFT')

    # Aggregate connection
    with client.websocket_connect('/ws') as ws:
        init_msg = ws.receive_json()
        assert init_msg['type'] == 'init_all'
        assert isinstance(init_msg['runs'], list)
        assert any(r['run_id'] in run_ids for r in init_msg['runs'])
        # send ping
        ws.send_json({'action': 'ping'})
        pong = ws.receive_json()
        assert pong['type'] == 'pong'

    # Focused connection for first run
    first = run_ids[0]
    with client.websocket_connect(f'/ws?run_id={first}') as ws2:
        init_run = ws2.receive_json()
        assert init_run['type'] == 'init_run'
        assert init_run['run_id'] == first
        assert 'execution_tree' in init_run
        # If tree not empty, try fetching content of first node
        exec_tree = init_run['execution_tree']
        if exec_tree:
            target_id = exec_tree[0]['id']
            ws2.send_json({'action': 'get_content', 'item_id': target_id})
            msg = ws2.receive_json()
            # Could be content or ack/error if empty placeholder
            assert msg['type'] in ('content', 'error')
        # Ping
        ws2.send_json({'action': 'ping'})
        pong2 = ws2.receive_json()
        assert pong2['type'] == 'pong'


def test_websocket_unknown_run():
    with client.websocket_connect('/ws?run_id=NON_EXISTENT_RUN') as ws:
        msg = ws.receive_json()
        # Server responds with error then closes logically (loop returns)
        assert msg['type'] == 'error'
