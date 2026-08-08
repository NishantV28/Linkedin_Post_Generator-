import logging
from typing import List, Optional
from sentence_transformers import SentenceTransformer

logger = logging.getLogger("autonomous_agent.memory.embeddings")

_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
_model_instance: Optional[SentenceTransformer] = None

def get_embedding_model() -> SentenceTransformer:
    """Lazy singleton loader for sentence-transformers model."""
    global _model_instance
    if _model_instance is None:
        logger.info(f"Loading embedding model '{_MODEL_NAME}' into memory...")
        _model_instance = SentenceTransformer(_MODEL_NAME)
        logger.info("Embedding model loaded successfully.")
    return _model_instance

def embed(text: str) -> List[float]:
    """Generate dense embedding vector for a single text string."""
    model = get_embedding_model()
    vector = model.encode(text, convert_to_numpy=True, normalize_embeddings=True)
    return vector.tolist()

def embed_batch(texts: List[str]) -> List[List[float]]:
    """Generate dense embedding vectors for a list of text strings."""
    if not texts:
        return []
    model = get_embedding_model()
    vectors = model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)
    return vectors.tolist()
