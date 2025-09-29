import chromadb
import os

class FinancialSituationMemory:
    def __init__(self, name, config, persist_directory="./memory_store"):
        # Use local embeddings for all providers - no external API dependency
        self.use_local_embeddings = config.get("use_local_embeddings", True)
        
        if self.use_local_embeddings:
            try:
                from sentence_transformers import SentenceTransformer
                # Use a good general-purpose model for financial text
                self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
                self.embedding_type = "local"
                print(f" Using local embeddings with sentence-transformers for {name}") # ✅
            except ImportError:
                print("⚠️  sentence-transformers not found. Install with: pip install sentence-transformers")
                print("Falling back to ChromaDB's default embeddings...")
                self.embedding_model = None
                self.embedding_type = "chromadb_default"
        else:
            # Legacy API-based embeddings (kept for backward compatibility)
            from openai import OpenAI
            if config["backend_url"] == "http://localhost:11434/v1":
                self.embedding = "nomic-embed-text"
                self.client = OpenAI(base_url=config["backend_url"])
            else:
                self.embedding = "text-embedding-3-small"
                if "openrouter.ai" in config["backend_url"]:
                    openai_api_key = os.getenv("OPENAI_API_KEY")
                    if not openai_api_key:
                        raise ValueError("❌ OPENAI_API_KEY required for API-based embeddings with OpenRouter")
                    self.client = OpenAI(api_key=openai_api_key)
                else:
                    api_key = None
                    if config.get("llm_provider") == "openai":
                        api_key = os.getenv("OPENAI_API_KEY")
                    self.client = OpenAI(base_url=config["backend_url"], api_key=api_key)
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
