import logging
import math
from collections import Counter
from typing import List, Dict, Any, Tuple, Optional, Iterable
from sqlalchemy.orm import Session

from backend.app.memory.models import PostModel
from backend.app.memory.embeddings import embed
from backend.app.memory.vector_store import query_dense
from backend.app.memory.sparse_index import BM25Index, tokenize_text
from backend.app.agent.tools.schema import TopicCandidate

logger = logging.getLogger("autonomous_agent.memory.hybrid_retriever")

RRF_K = 60.0

# Duplicate-detection thresholds, calibrated on real candidate/post pairs using
# all-MiniLM-L6-v2 cosine distance:
#   identical text .......... 0.00
#   same topic, reworded .... 0.41 - 0.49
#   same subfield, new paper. 0.40
#   different AI topic ...... 0.63 - 0.86
#   unrelated ............... 0.90+
# Dense distance alone cannot separate "same paper reworded" from "different
# paper in the same subfield" - both land near 0.40 - so anything short of a
# near-identical match must be corroborated by shared *rare* vocabulary.
DENSE_NEAR_IDENTICAL = 0.25   # drop on semantics alone
DENSE_BORDERLINE = 0.55       # drop only with lexical corroboration
LEXICAL_CORROBORATION = 0.40  # IDF-weighted share of the candidate's distinctive terms

# Distance below which a candidate counts as "same subfield as the last post" for
# spacing purposes. Looser than the duplicate thresholds above: these are different
# topics, just adjacent ones.
TOPIC_SPACING_DISTANCE = 0.55


def _idf_weights(tokenized_docs: List[List[str]]) -> Dict[str, float]:
    """
    Smoothed IDF over a small corpus. Always positive, so generic terms merely
    weigh little rather than dropping out entirely.
    """
    n_docs = len(tokenized_docs)
    doc_freq: Counter = Counter()
    for tokens in tokenized_docs:
        doc_freq.update(set(tokens))
    return {term: math.log(1.0 + (n_docs + 1.0) / (freq + 0.5)) for term, freq in doc_freq.items()}


def _weighted_overlap(cand_tokens: Iterable[str], post_tokens: Iterable[str], idf: Dict[str, float]) -> float:
    """
    Fraction of the candidate's *distinctive* vocabulary already covered by a
    past post, weighting each term by IDF. Sharing "model" and "language" barely
    moves this; sharing "baichuan" moves it a lot.
    """
    cand_set, post_set = set(cand_tokens), set(post_tokens)
    if not cand_set:
        return 0.0
    default_idf = math.log(1.0 + 2.0 / 0.5)  # unseen term: treat as maximally rare
    total = sum(idf.get(t, default_idf) for t in cand_set)
    if total <= 0:
        return 0.0
    shared = sum(idf.get(t, default_idf) for t in cand_set & post_set)
    return shared / total

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
        corpus_texts: Optional[List[str]] = None
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Check whether a candidate topic duplicates something this agent already published.

        Combines two independent signals:
          * dense cosine distance  - "is this about the same thing?"
          * IDF-weighted lexical overlap - "does it name the same specific thing?"

        A near-identical semantic match is enough on its own. A merely similar one
        must also share the candidate's rare vocabulary, which is what separates a
        reworded repost from a genuinely new paper in the same subfield.

        `corpus_texts` (this cycle's other candidate titles) sharpens the IDF
        estimate; without it, IDF is derived from past posts alone.

        Returns (is_dup, reason, scores).
        """
        posts = db.query(PostModel).filter(PostModel.agent_id == agent_id).all()
        if not posts:
            return False, "No past posts in memory", {"dense_distance": None, "lexical_overlap": 0.0}

        query_text = f"{candidate.title} {candidate.summary}"
        cand_tokens = tokenize_text(query_text)

        # --- Dense signal -------------------------------------------------
        dense_matches = query_dense(agent_id=agent_id, embedding=embed(query_text), top_k=5)
        best_dense_id, best_dense_distance = None, 1.0
        if dense_matches:
            best = min(dense_matches, key=lambda m: m.get("distance", 1.0))
            best_dense_id, best_dense_distance = best["id"], best.get("distance", 1.0)

        # --- Lexical signal -----------------------------------------------
        post_tokens = {p.id: tokenize_text(f"{p.topic_title or ''} {p.text}") for p in posts}
        idf_corpus = list(post_tokens.values())
        if corpus_texts:
            idf_corpus += [tokenize_text(t) for t in corpus_texts]
        idf = _idf_weights(idf_corpus)

        best_lex_id, best_lexical_overlap = None, 0.0
        for post_id, tokens in post_tokens.items():
            overlap = _weighted_overlap(cand_tokens, tokens, idf)
            if overlap > best_lexical_overlap:
                best_lex_id, best_lexical_overlap = post_id, overlap

        scores = {
            "dense_distance": best_dense_distance,
            "dense_match_id": best_dense_id,
            "lexical_overlap": round(best_lexical_overlap, 4),
            "lexical_match_id": best_lex_id,
        }

        if best_dense_distance <= DENSE_NEAR_IDENTICAL:
            return True, (
                f"Semantic duplicate - near-identical to an existing post "
                f"(distance {best_dense_distance:.3f} <= {DENSE_NEAR_IDENTICAL})"
            ), scores

        if best_dense_distance <= DENSE_BORDERLINE and best_lexical_overlap >= LEXICAL_CORROBORATION:
            return True, (
                f"Duplicate - semantically close (distance {best_dense_distance:.3f}) and shares "
                f"{best_lexical_overlap:.0%} of its distinctive terms with an existing post"
            ), scores

        return False, (
            f"Novel (distance {best_dense_distance:.3f}, "
            f"lexical overlap {best_lexical_overlap:.0%})"
        ), scores

    @staticmethod
    def order_by_topic_spacing(
        candidates: List[TopicCandidate],
        agent_id: str,
        db: Session,
        spacing_distance: float = TOPIC_SPACING_DISTANCE,
    ) -> List[TopicCandidate]:
        """
        Push candidates that closely echo the most recent post to the back of the queue.

        Deduplication only catches repeats of the *same* topic. This addresses the
        softer problem of several consecutive posts from one narrow subfield, which
        makes a feed read as a monoculture even when every post is individually novel.

        Deliberately a reordering, not a filter: if nothing else clears the editorial
        bar, a closely-related topic is still published rather than the agent going
        silent. That matches "unless there's a genuine reason" in the persona brief.
        """
        if len(candidates) < 2:
            return candidates

        recent = (
            db.query(PostModel)
            .filter(PostModel.agent_id == agent_id)
            .order_by(PostModel.created_at.desc())
            .first()
        )
        if not recent:
            return candidates

        try:
            last_embedding = embed(f"{recent.topic_title or ''} {recent.text}")
        except Exception as err:
            logger.debug(f"Topic spacing skipped, embedding unavailable: {err}")
            return candidates

        import numpy as np

        last_vec = np.array(last_embedding)
        last_norm = np.linalg.norm(last_vec) or 1.0

        near, rest = [], []
        for cand in candidates:
            try:
                vec = np.array(embed(f"{cand.title} {cand.summary}"))
                distance = 1.0 - float(vec @ last_vec) / (float(np.linalg.norm(vec) or 1.0) * last_norm)
            except Exception:
                rest.append(cand)
                continue
            (near if distance <= spacing_distance else rest).append(cand)

        if near:
            logger.info(
                "Topic spacing: deferring %d candidate(s) closely related to the last post "
                "('%s')", len(near), (recent.topic_title or "")[:50]
            )
        return rest + near

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
