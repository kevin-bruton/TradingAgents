import pytest
from tradingagents.utils import llm_client as lc

class DummyOpenAI:
    def __init__(self, base_url, api_key):
        self.base_url = base_url
        self.api_key = api_key

@pytest.fixture(autouse=True)
def patch_openai(monkeypatch):
    monkeypatch.setattr(lc, 'OpenAI', DummyOpenAI)

def test_detect_provider_from_backend_url_openrouter():
    config = {"backend_url": "https://openrouter.ai/api/v1"}
    assert lc._detect_provider(config) == 'openrouter'

def test_detect_provider_from_backend_url_ollama():
    config = {"backend_url": "http://localhost:11434/v1"}
    assert lc._detect_provider(config) == 'ollama'

def test_build_openai_client_openai_missing_key(monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    with pytest.raises(ValueError) as e:
        lc.build_openai_compatible_client({"llm_provider": "openai"})
    assert 'OPENAI_API_KEY' in str(e.value)

def test_build_openai_client_openrouter_missing_key(monkeypatch):
    monkeypatch.delenv('OPENROUTER_API_KEY', raising=False)
    with pytest.raises(ValueError) as e:
        lc.build_openai_compatible_client({"llm_provider": "openrouter"})
    assert 'OPENROUTER_API_KEY' in str(e.value)

def test_build_openai_client_ollama_no_key(monkeypatch):
    client, embedding = lc.build_openai_compatible_client({"llm_provider": "ollama"}, purpose='embeddings')
    assert isinstance(client, DummyOpenAI)
    assert client.base_url.startswith('http://localhost:11434')
    assert client.api_key is None
    assert embedding == 'nomic-embed-text'

def test_build_openai_client_openai_success(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'sk-test')
    client, embedding = lc.build_openai_compatible_client({"llm_provider": "openai"}, purpose='embeddings')
    assert client.api_key == 'sk-test'
    assert embedding == 'text-embedding-3-small'
