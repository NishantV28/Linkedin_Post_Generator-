import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import pytest
import json
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.memory.models import Base, PostModel, AgentModel
from backend.app.memory.embeddings import embed, embed_batch
from backend.app.memory.vector_store import add_post_vector, query_dense
from backend.app.memory.sparse_index import BM25Index, tokenize_text
from backend.app.memory.hybrid_retriever import reciprocal_rank_fusion, HybridRetriever
from backend.app.agent.tools.schema import TopicCandidate
from backend.app.memory.repository import MemoryRepository

TEST_DB_URL = "sqlite:///:memory:"
engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

def test_embeddings_generation():
    text = "Attention is all you need for transformer architectures."
    vector = embed(text)
    assert isinstance(vector, list)
    assert len(vector) == 384  # all-MiniLM-L6-v2 dimension is 384

    batch_vectors = embed_batch(["Text 1", "Text 2"])
    assert len(batch_vectors) == 2
    assert len(batch_vectors[0]) == 384

def test_vector_store_operations():
    import chromadb
    # Use in-memory (ephemeral) client for isolation in tests
    client = chromadb.EphemeralClient()
    collection = client.get_or_create_collection("test_agent", metadata={"hnsw:space": "cosine"})

    post_id = "post_vec_1"
    text = "Deep RL reasoning strategies for agent systems."
    vector = embed(text)

    collection.upsert(
        ids=[post_id],
        documents=[text],
        embeddings=[vector],
        metadatas=[{"agent_id": "test_agent_vstore_1"}]
    )

    query_vec = embed("RL reasoning strategies")
    results = collection.query(query_embeddings=[query_vec], n_results=1, include=["documents", "distances"])
    assert len(results["ids"][0]) > 0
    assert results["ids"][0][0] == post_id
    assert results["distances"][0][0] < 0.5

def test_sparse_bm25_indexing():
    docs = [
        {"id": "doc_1", "text": "Transformer scaling laws and pretraining tricks.", "topic_title": "LLM Scaling"},
        {"id": "doc_2", "text": "Adversarial prompt injection defenses in LLM security.", "topic_title": "Prompt Injection"}
    ]
    index = BM25Index(docs)
    results = index.query_sparse("prompt injection security", top_k=5)
    assert len(results) > 0
    assert results[0][0] == "doc_2"

def test_rrf_fusion_logic():
    dense_res = [
        {"id": "doc_A", "distance": 0.1},
        {"id": "doc_B", "distance": 0.4}
    ]
    sparse_res = [
        ("doc_B", 5.2),
        ("doc_A", 1.1)
    ]
    fused = reciprocal_rank_fusion(dense_res, sparse_res, top_k=2)
    assert len(fused) == 2
    assert "rrf_score" in fused[0]

def test_hybrid_deduplication():
    import chromadb
    import backend.app.memory.vector_store as vs_module

    # Patch global _client singleton to use ephemeral (in-memory) DB for isolation
    vs_module._client = chromadb.EphemeralClient()

    db = TestingSessionLocal()
    agent_id = "test_agent_dedup_1"

    # Seed a post
    MemoryRepository.save_post(
        db=db,
        agent_id=agent_id,
        text="Self-critique reasoning model strategy for intermediate step verification.",
        rationale="Selected for novel reasoning.",
        sources=["https://arxiv.org/abs/2401.00000"],
        topic_title="Self Critique Reasoning"
    )

    # 1. Test duplicate candidate
    dup_cand = TopicCandidate(
        id="cand_dup",
        title="Self Critique Reasoning Models",
        summary="A new paper on self critique reasoning strategies for intermediate step verification.",
        url="https://arxiv.org/abs/2401.00000",
        source="arxiv",
        published_at="2026-08-08T10:00:00Z"
    )
    is_dup, reason, scores = HybridRetriever.is_duplicate(dup_cand, agent_id=agent_id, db=db)
    assert is_dup is True
    assert "duplicate" in reason.lower()

    # 2. Test novel candidate
    novel_cand = TopicCandidate(
        id="cand_novel",
        title="Quantum Hardware Architectures",
        summary="Superconducting qubits operating at sub-kelvin temperatures for error mitigation.",
        url="https://arxiv.org/abs/2401.99999",
        source="arxiv",
        published_at="2026-08-08T10:00:00Z"
    )
    is_dup_novel, reason_novel, _ = HybridRetriever.is_duplicate(novel_cand, agent_id=agent_id, db=db)
    assert is_dup_novel is False
    db.close()

    # Reset singleton so other tests / scripts use persistent client
    vs_module._client = None

