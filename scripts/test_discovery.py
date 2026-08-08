import os
import sys
import logging

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.app.memory.db import init_db, SessionLocal
from backend.app.memory.models import AgentModel
from backend.app.agent.persona.presets import DISTILL_PRESET
from backend.app.agent.tools.discovery import discover_all_candidates
from backend.app.memory.hybrid_retriever import HybridRetriever
from backend.app.memory.repository import MemoryRepository

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("test_discovery")

def run_discovery_test():
    print("=" * 70)
    print("      AUTONOMOUS AI PERSONA AGENT — PHASE 2 DISCOVERY & DEDUP HARNESS")
    print("=" * 70)

    # 1. Initialize SQLite tables
    init_db()
    db = SessionLocal()

    try:
        # 2. Get or create Distill agent in DB
        agent = db.query(AgentModel).filter(AgentModel.name == DISTILL_PRESET.name).first()
        if not agent:
            agent = AgentModel(
                name=DISTILL_PRESET.name,
                domain=DISTILL_PRESET.domain,
                persona_json=DISTILL_PRESET.model_dump_json(),
                active=True,
                cycle_count=0
            )
            db.add(agent)
            db.commit()
            db.refresh(agent)
            print(f"Created sample agent '{agent.name}' (ID: {agent.id})")
        else:
            print(f"Loaded existing agent '{agent.name}' (ID: {agent.id})")

        # Optionally seed 1 past post to demonstrate deduplication on second run
        recent_posts = MemoryRepository.get_recent_posts(db, agent.id, limit=1)
        if not recent_posts:
            print("\n[Seeding memory with initial sample post for dedup testing...]")
            MemoryRepository.save_post(
                db=db,
                agent_id=agent.id,
                text="Another paper claims better reasoning. But the interesting part isn't the benchmark score. It's the training strategy — the model learns to critique its own intermediate steps.",
                rationale="Selected for novel self-critique reasoning strategy.",
                sources=["https://arxiv.org/abs/2401.00000"],
                topic_title="Self-Critique Reasoning Models in AI"
            )

        # 3. Execute Candidate Discovery across HN, arXiv, GitHub, and Web
        print(f"\n1. RUNNING CANDIDATE DISCOVERY FOR PERSONA '{DISTILL_PRESET.name}'...")
        raw_candidates = discover_all_candidates(DISTILL_PRESET)

        print(f"\n---> Total Raw Candidates Discovered: {len(raw_candidates)}")
        for idx, cand in enumerate(raw_candidates, 1):
            print(f"  [{idx}] [{cand.source.upper()}] {cand.title[:65]}... ({cand.url})")

        # 4. Execute Hybrid Dense + BM25 Deduplication
        print(f"\n2. RUNNING HYBRID DENSE + BM25 DEDUPLICATION EVALUATION...")
        surviving_candidates = []
        dropped_count = 0

        for cand in raw_candidates:
            is_dup, reason, scores = HybridRetriever.is_duplicate(
                candidate=cand,
                agent_id=agent.id,
                db=db,
                dense_distance_threshold=0.35
            )

            dense_dist_str = f"{scores['dense_distance']:.4f}" if scores.get("dense_distance") is not None else "N/A"
            rrf_score_str = f"{scores['rrf_score']:.4f}"

            if is_dup:
                dropped_count += 1
                print(f"  [DROPPED - DUP] Source: {cand.source.upper()} | Title: '{cand.title[:45]}...'")
                print(f"                  Reason: {reason}")
                print(f"                  Dense Distance: {dense_dist_str} | RRF Score: {rrf_score_str}")
                MemoryRepository.save_rejection(
                    db=db,
                    agent_id=agent.id,
                    title=cand.title,
                    source_url=cand.url,
                    reason=f"Phase 2 Dedup: {reason}",
                    judge_scores=scores
                )
            else:
                surviving_candidates.append(cand)
                print(f"  [ACCEPTED - NOVEL] Source: {cand.source.upper()} | Title: '{cand.title[:45]}...'")
                print(f"                     Dense Distance: {dense_dist_str} | RRF Score: {rrf_score_str}")

        # 5. Summary metrics
        print("\n" + "=" * 70)
        print("                        DISCOVERY & DEDUP SUMMARY")
        print("=" * 70)
        print(f"  Raw Candidates Discovered : {len(raw_candidates)}")
        print(f"  Duplicates Dropped        : {dropped_count}")
        print(f"  Surviving Novel Candidates: {len(surviving_candidates)}")
        print("=" * 70)

    finally:
        db.close()

if __name__ == "__main__":
    run_discovery_test()
