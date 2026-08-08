import os
import logging
import chromadb
from typing import List, Dict, Any, Optional

logger = logging.getLogger("autonomous_agent.memory.vector_store")

_CHROMA_PATH = os.path.abspath("./chroma_data")
_client: Optional[chromadb.PersistentClient] = None

def get_chroma_client() -> chromadb.PersistentClient:
    global _client
    if _client is None:
        os.makedirs(_CHROMA_PATH, exist_ok=True)
        logger.info(f"Initializing ChromaDB PersistentClient at '{_CHROMA_PATH}'...")
        _client = chromadb.PersistentClient(path=_CHROMA_PATH)
    return _client

def get_agent_collection(agent_id: str):
    """Retrieve or create Chroma collection for a specific agent."""
    client = get_chroma_client()
    collection_name = f"agent_{agent_id.replace('-', '_')}"
    return client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"}
    )

def add_post_vector(agent_id: str, post_id: str, text: str, embedding: List[float], metadata: Optional[Dict[str, Any]] = None):
    """Add or update a post vector in ChromaDB."""
    collection = get_agent_collection(agent_id)
    meta = metadata or {}
    meta["agent_id"] = agent_id

    collection.upsert(
        ids=[post_id],
        documents=[text],
        embeddings=[embedding],
        metadatas=[meta]
    )
    logger.debug(f"Upserted vector for post {post_id} into collection agent_{agent_id}")

def query_dense(agent_id: str, embedding: List[float], top_k: int = 5) -> List[Dict[str, Any]]:
    """
    Query ChromaDB for dense cosine similarity matches.
    Returns list of dicts with keys: 'id', 'distance', 'document', 'metadata'.
    """
    collection = get_agent_collection(agent_id)
    count = collection.count()
    if count == 0:
        return []

    actual_k = min(top_k, count)
    results = collection.query(
        query_embeddings=[embedding],
        n_results=actual_k,
        include=["documents", "distances", "metadatas"]
    )

    formatted = []
    if results and results.get("ids") and len(results["ids"]) > 0:
        ids = results["ids"][0]
        distances = results["distances"][0]
        documents = results["documents"][0]
        metadatas = results["metadatas"][0]

        for idx in range(len(ids)):
            formatted.append({
                "id": ids[idx],
                "distance": distances[idx],
                "document": documents[idx],
                "metadata": metadatas[idx]
            })

    return formatted
