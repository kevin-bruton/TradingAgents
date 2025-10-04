import pytest
from tradingagents.utils import llm_client as lc

class DummyOpenAI:
    def __init__(self, base_url, api_key):
        self.base_url = base_url
        self.api_key = api_key

@pytest.fixture(autouse=True)
def patch_openai(monkeypatch):
    monkeypatch.setattr(lc, 'OpenAI', DummyOpenAI)


def test_build_client_openrouter_success(monkeypatch):
    monkeypatch.setenv('OPENROUTER_API_KEY', 'or-key')
    client, emb = lc.build_openai_compatible_client({"llm_provider": "openrouter"}, purpose='embeddings')
    assert isinstance(client, DummyOpenAI)
    assert client.api_key == 'or-key'
    assert 'openrouter' in client.base_url or 'api.openai.com' in client.base_url  # openrouter may redirect via base_url inference
    assert emb == lc.DEFAULT_EMBEDDING_MODEL['openrouter']


def test_build_client_unknown_provider_defaults_openai(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'openai-key')
    client, emb = lc.build_openai_compatible_client({"llm_provider": "unknown_vendor"}, purpose='embeddings')
    assert client.api_key == 'openai-key'
    assert emb == lc.DEFAULT_EMBEDDING_MODEL['openai']


def test_build_client_ollama_default_base(monkeypatch):
    client, emb = lc.build_openai_compatible_client({"llm_provider": "ollama"}, purpose='embeddings')
    assert client.base_url.startswith('http://localhost:11434')
    assert client.api_key is None
    assert emb == lc.DEFAULT_EMBEDDING_MODEL['ollama']
