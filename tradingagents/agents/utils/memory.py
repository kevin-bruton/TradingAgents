import chromadb
import os
import threading
from typing import Optional

# ---------------------------------------------------------------------------
# Global embedding model singleton (thread-safe) to avoid concurrent model
# instantiation causing PyTorch meta tensor errors when multiple runs start
# simultaneously (e.g. multi-instrument webapp runs).
# ---------------------------------------------------------------------------
_EMBEDDING_MODEL_SINGLETON = None  # type: ignore
_EMBEDDING_MODEL_NAME: Optional[str] = None
_EMBEDDING_MODEL_LOCK = threading.Lock()

def _load_embedding_model(model_name: str = "all-MiniLM-L6-v2"):
    """Idempotently load and return a shared SentenceTransformer model.

    This guards against the race where multiple threads/processes try to
    construct the model at once, which can surface as:
        RuntimeError: Cannot copy out of meta tensor; no data!

    Strategy:
      1. Double-checked locking around a global singleton.
      2. Catch meta-tensor related RuntimeError and retry once serially.
      3. On persistent failure, return None so caller can fall back to
         ChromaDB default embeddings (keeping the app functional).
    """
    global _EMBEDDING_MODEL_SINGLETON, _EMBEDDING_MODEL_NAME
    if _EMBEDDING_MODEL_SINGLETON is not None:
        return _EMBEDDING_MODEL_SINGLETON

    with _EMBEDDING_MODEL_LOCK:
        if _EMBEDDING_MODEL_SINGLETON is not None:  # re-check
            return _EMBEDDING_MODEL_SINGLETON
        try:
            from sentence_transformers import SentenceTransformer  # local import
            try:
                # Force CPU unless user explicitly overrides via env; reduces
                # cross-device moves that can trigger meta tensor pathways.
                device = os.getenv("SENTENCE_TRANSFORMERS_DEVICE", "cpu")
                _EMBEDDING_MODEL_SINGLETON = SentenceTransformer(model_name, device=device)
                _EMBEDDING_MODEL_NAME = model_name
                return _EMBEDDING_MODEL_SINGLETON
            except RuntimeError as re:  # Handle meta tensor race
                if "meta tensor" in str(re).lower():
                    # Retry once after a short synchronized backoff
                    # (No sleep used here to keep deterministic; could add if needed.)
                    try:
                        _EMBEDDING_MODEL_SINGLETON = SentenceTransformer(model_name, device="cpu")
                        _EMBEDDING_MODEL_NAME = model_name
                        return _EMBEDDING_MODEL_SINGLETON
                    except Exception as re2:  # pragma: no cover - rare double failure
                        print(f"⚠️  Embedding model meta tensor retry failed: {re2}. Falling back to ChromaDB default embeddings.")
                        _EMBEDDING_MODEL_SINGLETON = None
                        return None
                else:
                    raise
        except ImportError:
            # sentence-transformers not installed; caller will fallback.
            return None

def _get_shared_embedding_model():  # convenience accessor
    return _EMBEDDING_MODEL_SINGLETON

class FinancialSituationMemory:
    def __init__(self, name, config, persist_directory="./memory_store"):
        # Use local embeddings for all providers - no external API dependency
        self.use_local_embeddings = config.get("use_local_embeddings", True)
        
        if self.use_local_embeddings:
            # Attempt to obtain (or lazily create) the shared embedding model
            self.embedding_model = _load_embedding_model('all-MiniLM-L6-v2')
            if self.embedding_model is not None:
                self.embedding_type = "local"
                # Only print once per process for clarity
                if _EMBEDDING_MODEL_NAME and name == "bull_memory":
                    print(f" Using shared local embeddings model '{_EMBEDDING_MODEL_NAME}' (singleton) for memory instances")
            else:
                print("⚠️  sentence-transformers unavailable or failed to initialize safely. Falling back to ChromaDB's default embeddings...")
                self.embedding_type = "chromadb_default"
                self.embedding_model = None
        else:
            # Centralized API-based client creation
            from tradingagents.utils.llm_client import build_openai_compatible_client
            self.client, embedding_model_hint = build_openai_compatible_client(config, purpose="embeddings")
            # If local Ollama, override embedding model name accordingly
            if config.get("backend_url") == "http://localhost:11434/v1":
                self.embedding = "nomic-embed-text"
            else:
                # Use hint if provided, fallback to previous default
                self.embedding = embedding_model_hint or "text-embedding-3-small"
            self.embedding_type = "api"
        
        self.chroma_client = chromadb.PersistentClient(path=persist_directory)
        
        # Create collection with or without custom embedding function
        if self.embedding_type == "chromadb_default":
            # Let ChromaDB handle embeddings with its default function
            self.situation_collection = self.chroma_client.get_or_create_collection(name=name)
        else:
            # We'll handle embeddings ourselves
            self.situation_collection = self.chroma_client.get_or_create_collection(
                name=name,
                metadata={"hnsw:space": "cosine"}  # Use cosine similarity
            )


    def get_embedding(self, text):
        """Get embedding for a text using local or API-based models"""
        try:
            if self.embedding_type == "local":
                # Use local sentence-transformers model
                embedding = self.embedding_model.encode(text, convert_to_tensor=False)
                return embedding.tolist() if hasattr(embedding, 'tolist') else embedding
            
            elif self.embedding_type == "chromadb_default":
                # ChromaDB will handle embeddings automatically, return None
                return None
            
            else:  # API-based embeddings
                response = self.client.embeddings.create(
                    model=self.embedding, input=text
                )
                if hasattr(response, 'data') and len(response.data) > 0:
                    return response.data[0].embedding
                else:
                    raise ValueError(f"Unexpected response format from embeddings API: {type(response)}")
                    
        except Exception as e:
            raise RuntimeError(f"Failed to get embedding for text: {str(e)}")

    def add_situations(self, situations_and_advice):
        """Add financial situations and their corresponding advice. Parameter is a list of tuples (situation, rec)"""

        situations = []
        advice = []
        ids = []
        embeddings = []

        offset = self.situation_collection.count()

        for i, (situation, recommendation) in enumerate(situations_and_advice):
            situations.append(situation)
            advice.append(recommendation)
            ids.append(str(offset + i))
            
            # Only compute embeddings if not using ChromaDB's default
            if self.embedding_type != "chromadb_default":
                embeddings.append(self.get_embedding(situation))

        # Add to collection with or without custom embeddings
        if self.embedding_type == "chromadb_default":
            # Let ChromaDB compute embeddings automatically
            self.situation_collection.add(
                documents=situations,
                metadatas=[{"recommendation": rec} for rec in advice],
                ids=ids,
            )
        else:
            # Use our custom embeddings
            self.situation_collection.add(
                documents=situations,
                metadatas=[{"recommendation": rec} for rec in advice],
                embeddings=embeddings,
                ids=ids,
            )

    def get_memories(self, current_situation, n_matches=1):
        """Find matching recommendations using local or API-based embeddings"""
        
        if self.embedding_type == "chromadb_default":
            # Use ChromaDB's built-in embeddings - query with text directly
            results = self.situation_collection.query(
                query_texts=[current_situation],
                n_results=n_matches,
                include=["metadatas", "documents", "distances"],
            )
        else:
            # Use our custom embeddings
            query_embedding = self.get_embedding(current_situation)
            results = self.situation_collection.query(
                query_embeddings=[query_embedding],
                n_results=n_matches,
                include=["metadatas", "documents", "distances"],
            )

        matched_results = []
        for i in range(len(results["documents"][0])):
            matched_results.append(
                {
                    "matched_situation": results["documents"][0][i],
                    "recommendation": results["metadatas"][0][i]["recommendation"],
                    "similarity_score": 1 - results["distances"][0][i],
                }
            )

        return matched_results


if __name__ == "__main__":
    # Define the directory where memory will be stored
    PERSIST_DIRECTORY = "./memory_store"
    print(f"Memory will be persisted to: {os.path.abspath(PERSIST_DIRECTORY)}\n")

    # Example usage
    config_example = {"use_local_embeddings": True, "backend_url": ""}
    # Initialize memory with a name and the persistence directory
    matcher = FinancialSituationMemory(
        name="persistent_example_memory", 
        config=config_example, 
        persist_directory=PERSIST_DIRECTORY
    )

    # Check if memory is already populated
    if matcher.situation_collection.count() == 0:
        print("Memory is empty. Populating with example data...")
        # Example data
        example_data = [
            (
                "High inflation rate with rising interest rates and declining consumer spending",
                "Consider defensive sectors like consumer staples and utilities. Review fixed-income portfolio duration.",
            ),
            (
                "Tech sector showing high volatility with increasing institutional selling pressure",
                "Reduce exposure to high-growth tech stocks. Look for value opportunities in established tech companies with strong cash flows.",
            ),
            (
                "Strong dollar affecting emerging markets with increasing forex volatility",
                "Hedge currency exposure in international positions. Consider reducing allocation to emerging market debt.",
            ),
            (
                "Market showing signs of sector rotation with rising yields",
                "Rebalance portfolio to maintain target allocations. Consider increasing exposure to sectors benefiting from higher rates.",
            ),
        ]
        # Add the example situations and recommendations
        matcher.add_situations(example_data)
        print("Example data added to persistent memory.\n")
    else:
        print("Memory already contains data from a previous run.\n")

    # --- Inspecting the entire memory store ---
    print("--- Dumping all contents of the memory store ---")
    all_items = matcher.situation_collection.get(include=["metadatas", "documents"])
    
    if not all_items or not all_items.get("ids"):
        print("Memory store is empty.")
    else:
        for i, item_id in enumerate(all_items["ids"]):
            situation = all_items["documents"][i]
            recommendation = all_items["metadatas"][i].get("recommendation", "N/A")
            print(f"ID: {item_id}")
            print(f"  Situation: {situation}")
            print(f"  Recommendation/Lesson: {recommendation}\n")
    print("--- End of memory dump ---")

    # Example query to show it still works
    print("\n--- Running an example query ---")
    current_situation = """
    Market showing increased volatility in tech sector, with institutional investors 
    reducing positions and rising interest rates affecting growth stock valuations
    """
    print(f"Querying for situation: {current_situation.strip()}\n")

    try:
        recommendations = matcher.get_memories(current_situation, n_matches=1)
        if recommendations:
            rec = recommendations[0]
            print(f"Most similar match found:")
            print(f"  Similarity Score: {rec['similarity_score']:.2f}")
            print(f"  Matched Situation: {rec['matched_situation']}")
            print(f"  Retrieved Recommendation: {rec['recommendation']}\n")
        else:
            print("No similar situations found in memory.")

    except Exception as e:
        print(f"Error during recommendation: {str(e)}")
