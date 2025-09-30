import types
import builtins
import pytest
from tradingagents.agents.utils.memory import FinancialSituationMemory

class DummySentenceTransformer:
    def __init__(self, name):
        self.name = name
    def encode(self, text, convert_to_tensor=False):
        return [float(len(text))]

def test_memory_add_and_query(tmp_path, monkeypatch):
    monkeypatch.setitem(__import__('sys').modules, 'sentence_transformers', types.SimpleNamespace(SentenceTransformer=DummySentenceTransformer))
    mem = FinancialSituationMemory(name="test_mem", config={"use_local_embeddings": True}, persist_directory=str(tmp_path))
    mem.add_situations([
        ("high inflation and rate hikes", "prefer defensive sectors"),
        ("tech volatility and rising yields", "trim high growth allocate to value"),
    ])
    res = mem.get_memories("tech volatility", n_matches=1)
    assert res
    rec = res[0]
    assert {"matched_situation", "recommendation", "similarity_score"}.issubset(rec)
    assert 0 <= rec["similarity_score"] <= 1

def test_memory_chromadb_default(tmp_path, monkeypatch):
    real_import = builtins.__import__
    def fake_import(name, *args, **kwargs):
        if name == 'sentence_transformers':
            raise ModuleNotFoundError
        return real_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', fake_import)
    mem = FinancialSituationMemory(name="test_mem2", config={"use_local_embeddings": True}, persist_directory=str(tmp_path))
    assert mem.embedding_type in {"chromadb_default", "local"}
    if mem.embedding_type == "chromadb_default":
        if hasattr(mem.situation_collection, "_embedding_function"):
            mem.situation_collection._embedding_function = lambda input: [[0.0] * 8 for _ in input]  # type: ignore[attr-defined]
        elif hasattr(mem.situation_collection, "embedding_function"):
            mem.situation_collection.embedding_function = lambda input: [[0.0] * 8 for _ in input]  # type: ignore[attr-defined]
    mem.add_situations([("s1", "r1"), ("s2", "r2")])
    assert mem.situation_collection.count() >= 2
