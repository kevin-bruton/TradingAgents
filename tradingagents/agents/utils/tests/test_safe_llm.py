import time
import types
import pytest
from tradingagents.agents.utils.safe_llm import safe_invoke_llm, LLMRetryConfig, _compute_backoff

class DummyLLM:
    def __init__(self, fail_times=0, exception_cls=ValueError, response=None):
        self.fail_times = fail_times
        self.calls = 0
        self.exception_cls = exception_cls
        self.response = response or types.SimpleNamespace(content="ok", data={})

    def invoke(self, payload):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise self.exception_cls("transient json decode error: Expecting value: line 1 column 1 (char 0)")
        return self.response

def test_compute_backoff_monotonic():
    cfg = LLMRetryConfig(max_attempts=5, base_delay=0.1, max_delay=1.0, jitter=0.0)
    delays = [_compute_backoff(i, cfg) for i in range(1, 6)]
    assert delays == sorted(delays)
    assert delays[-1] <= cfg.max_delay

def test_safe_invoke_success_after_retries(monkeypatch):
    llm = DummyLLM(fail_times=2, exception_cls=ValueError)
    monkeypatch.setattr(time, "sleep", lambda s: None)
    result = safe_invoke_llm(llm, "hi", cfg=LLMRetryConfig(max_attempts=4, base_delay=0.01, max_delay=0.05))
    assert result.content == "ok"
    assert llm.calls == 3

def test_safe_invoke_exhausts_retries(monkeypatch):
    llm = DummyLLM(fail_times=5, exception_cls=ValueError)
    monkeypatch.setattr(time, "sleep", lambda s: None)
    with pytest.raises(ValueError):
        safe_invoke_llm(llm, "hi", cfg=LLMRetryConfig(max_attempts=3, base_delay=0.01, max_delay=0.05))
    assert llm.calls == 3

def test_jitter_range():
    cfg = LLMRetryConfig(max_attempts=2, base_delay=0.2, max_delay=0.2, jitter=0.5)
    d = _compute_backoff(1, cfg)
    assert 0.1 <= d <= 0.3
