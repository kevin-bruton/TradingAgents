import pytest
from json import JSONDecodeError
from tradingagents.agents.utils.llm_resilience import invoke_with_retries

class DummyChain:
    def __init__(self, fail_times=0, exception=None):
        self.fail_times = fail_times
        self.calls = 0
        self.exception = exception or JSONDecodeError('msg', 'doc', 0)

    def invoke(self, messages):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise self.exception
        return {"ok": True, "messages": messages}

def test_invoke_with_retries_success_after_json_decode(monkeypatch):
    chain = DummyChain(fail_times=2)
    result = invoke_with_retries(chain, ["hi"], {"llm_max_retries": 4, "llm_retry_backoff": 0})
    assert result["ok"] is True
    assert chain.calls == 3

def test_invoke_with_retries_non_transient_abort():
    chain = DummyChain(fail_times=1, exception=ValueError("permanent failure"))
    with pytest.raises(ValueError):
        invoke_with_retries(chain, ["hi"], {"llm_max_retries": 3, "llm_retry_backoff": 0})
    assert chain.calls == 1
