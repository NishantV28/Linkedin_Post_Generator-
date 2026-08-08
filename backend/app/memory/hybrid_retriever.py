import logging
from typing import List, Dict, Any, Tuple, Optional
from sqlalchemy.orm import Session

from backend.app.memory.models import PostModel
from backend.app.memory.embeddings import embed
from backend.app.memory.vector_store import query_dense
from backend.app.memory.sparse_index import BM25Index
from backend.app.agent.tools.schema import TopicCandidate

logger = logging.getLogger("autonomous_agent.memory.hybrid_retriever")

RRF_K = 60.0

def reciprocal_rank_fusion(
    dense_results: List[Dict[str, Any]],
    sparse_results: List[Tuple[str, float]],
    top_k: int = 5
) -> List[Dict[str, Any]]:
    """
    Fuse dense vector rankings and sparse BM25 rankings via Reciprocal Rank Fusion.
    RRF_score(d) = 1/(k + dense_rank) + 1/(k + sparse_rank)
    """
    rrf_scores: Dict[str, float] = {}
    dense_map: Dict[str, Dict[str, Any]] = {}

    # Dense ranking
    for rank, item in enumerate(dense_results, start=1):
        post_id = item["id"]
        dense_map[post_id] = item
        rrf_scores[post_id] = rrf_scores.get(post_id, 0.0) + (1.0 / (RRF_K + rank))

    # Sparse ranking
    for rank, (post_id, _score) in enumerate(sparse_results, start=1):
        rrf_scores[post_id] = rrf_scores.get(post_id, 0.0) + (1.0 / (RRF_K + rank))

    sorted_ids = sorted(rrf_scores.keys(), key=lambda pid: rrf_scores[pid], reverse=True)

    fused = []
    for pid in sorted_ids[:top_k]:
        dense_item = dense_map.get(pid, {})
        fused.append({
            "id": pid,
            "rrf_score": rrf_scores[pid],
            "dense_distance": dense_item.get("distance", 1.0),
            "document": dense_item.get("document", "")
        })

    return fused


class HybridRetriever:
    """Hybrid (Dense + BM25) retriever for deduplication and context retrieval."""

    @staticmethod
    def is_duplicate(
        candidate: TopicCandidate,
        agent_id: str,
        db: Session,
        dense_distance_threshold: float = 0.35
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Check if candidate topic is a duplicate of any existing published post for this agent.
        Returns (is_dup: bool, reason: str, scores: dict).
        """
        # Fetch published posts for sparse indexing
        posts = db.query(PostModel).filter(PostModel.agent_id == agent_id).all()
        if not posts:
            return False, "No past posts in memory", {"dense_distance": None, "rrf_score": 0.0}

        query_text = f"{candidate.title} {candidate.summary}"
        cand_embedding = embed(query_text)

        # Dense retrieval via ChromaDB
        dense_matches = query_dense(agent_id=agent_id, embedding=cand_embedding, top_k=5)

        # Sparse retrieval via BM25
        post_docs = [{"id": p.id, "text": p.text, "topic_title": p.topic_title or ""} for p in posts]
        bm25_index = BM25Index(post_docs)
        sparse_matches = bm25_index.query_sparse(query_text, top_k=5)

        # RRF Fusion
        fused = reciprocal_rank_fusion(dense_matches, sparse_matches, top_k=5)

        if not fused:
            return False, "No match found", {"dense_distance": None, "rrf_score": 0.0}

        top_match = fused[0]
        top_dense_distance = top_match.get("dense_distance", 1.0)
        top_rrf_score = top_match.get("rrf_score", 0.0)

        # Deduplication condition:
        # 1. Cosine distance below threshold (semantic similarity)
        # OR 2. High RRF score from both dense and sparse alignment
        if top_dense_distance <= dense_distance_threshold:
            return True, f"Semantic duplicate detected (dense distance {top_dense_distance:.4f} <= {dense_distance_threshold})", {
                "matched_post_id": top_match["id"],
                "dense_distance": top_dense_distance,
                "rrf_score": top_rrf_score
            }

        if top_rrf_score > 0.031:  # Significant RRF score threshold (both dense & sparse top-3)
            return True, f"Lexical/Semantic fused duplicate detected (RRF score {top_rrf_score:.4f})", {
                "matched_post_id": top_match["id"],
                "dense_distance": top_dense_distance,
                "rrf_score": top_rrf_score
            }

        return False, "Candidate topic is sufficiently novel", {
            "top_match_id": top_match["id"],
            "dense_distance": top_dense_distance,
            "rrf_score": top_rrf_score
        }

    @staticmethod
    def get_relevant_context(agent_id: str, query_text: str, db: Session, top_k: int = 3) -> List[Dict[str, Any]]:
        """
        Retrieve topically relevant past posts for few-shot prompt context (used by writer node in Phase 3).
        """
        posts = db.query(PostModel).filter(PostModel.agent_id == agent_id).all()
        if not posts:
            return []

        embedding = embed(query_text)
        dense_matches = query_dense(agent_id=agent_id, embedding=embedding, top_k=top_k * 2)

        post_docs = [{"id": p.id, "text": p.text, "topic_title": p.topic_title or ""} for p in posts]
        bm25_index = BM25Index(post_docs)
        sparse_matches = bm25_index.query_sparse(query_text, top_k=top_k * 2)

        fused = reciprocal_rank_fusion(dense_matches, sparse_matches, top_k=top_k)

        post_map = {p.id: p for p in posts}
        results = []
        for item in fused:
            pid = item["id"]
            if pid in post_map:
                p = post_map[pid]
                results.append({
                    "id": p.id,
                    "text": p.text,
                    "topic_title": p.topic_title,
                    "rationale": p.rationale,
                    "rrf_score": item["rrf_score"]
                })
        return results
