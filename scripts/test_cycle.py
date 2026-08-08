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
from backend.app.agent.graph import agent_graph
from backend.app.core.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("test_cycle")

def run_phase3_cycle_test():
    print("=" * 75)
    print("       AUTONOMOUS AI PERSONA AGENT — PHASE 3 LANGGRAPH CORE HARNESS")
    print("=" * 75)

    # Check API key configuration
    groq_key = settings.GROQ_API_KEY or os.environ.get("GROQ_API_KEY")
    openai_key = settings.OPENAI_API_KEY or os.environ.get("OPENAI_API_KEY")

    if (not groq_key or groq_key == "your_groq_api_key_here") and (not openai_key or openai_key == "your_openai_api_key_here"):
        print("\n[WARNING] No active LLM API Key detected in .env!")
        print("Please add GROQ_API_KEY=gsk_... or OPENAI_API_KEY=sk-... to your .env file to run live LLM calls.")
        print("=" * 75)
        return

    provider_name = "Groq API" if (groq_key and groq_key != "your_groq_api_key_here") else "OpenAI API"
    model_name = settings.LLM_MODEL or ("llama-3.3-70b-versatile" if provider_name == "Groq API" else "gpt-4o-mini")
    print(f"Using Provider: {provider_name} | Model: {model_name}")

    # 1. Initialize SQLite tables
    init_db()
    db = SessionLocal()

    try:
        # 2. Get or create agent in DB
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

        # 3. Discover live candidates across HN, arXiv, GitHub, Web search
        print(f"\n1. DISCOVERING LIVE CANDIDATES FOR PERSONA '{DISTILL_PRESET.name}'...")
        raw_candidates = discover_all_candidates(DISTILL_PRESET)
        print(f"---> Total Raw Candidates Discovered: {len(raw_candidates)}")

        # 4. Filter via Hybrid Deduplication
        print("\n2. DEDUPLICATING CANDIDATES AGAINST PAST MEMORY...")
        surviving_candidates = []
        for cand in raw_candidates:
            is_dup, reason, _ = HybridRetriever.is_duplicate(cand, agent_id=agent.id, db=db)
            if not is_dup:
                surviving_candidates.append(cand)
            else:
                print(f"  [DEDUP DROPPED] '{cand.title[:50]}...' -> {reason}")

        print(f"---> Novel Candidates Ready for Editorial Evaluation: {len(surviving_candidates)}")

        if not surviving_candidates:
            print("\nNo novel candidates survived deduplication. Cycle complete.")
            return

        # 5. Invoke LangGraph Core Agent Graph
        print("\n3. EXECUTING LANGGRAPH AGENT CORE (EDITORIAL JUDGE -> WRITER -> QA JUDGE -> PUBLISH)...")
        initial_state = {
            "persona": DISTILL_PRESET,
            "agent_id": agent.id,
            "candidates": surviving_candidates,
            "candidate_idx": 0,
            "current_candidate": None,
            "judge_verdict": None,
            "draft": None,
            "qa_verdict": None,
            "retry_count": 0,
            "published_post": None,
            "rejected_count": 0,
            "cycle_outcome": "init"
        }

        final_state = agent_graph.invoke(initial_state)

        # 6. Display Cycle Summary & Results
        print("\n" + "=" * 75)
        print("                          CYCLE EXECUTION SUMMARY")
        print("=" * 75)
        print(f"  Cycle Outcome          : {final_state.get('cycle_outcome', 'unknown').upper()}")
        print(f"  Candidates Processed   : {final_state.get('candidate_idx', 0) + 1}")
        print(f"  Topics Rejected        : {final_state.get('rejected_count', 0)}")

        published = final_state.get("published_post")
        if published:
            print("\n" + "-" * 75)
            print("                       PUBLISHED POST IN FEED")
            print("-" * 75)
            print(f"POST ID    : {published['id']}")
            print(f"TITLE      : {published['topic_title']}")
            print(f"CREATED AT : {published['created_at']}")
            print(f"SOURCES    : {published['sources']}")
            print("\nPOST TEXT  :")
            print(published['text'])
            print("\nPUBLISHING RATIONALE :")
            print(published['rationale'])
            print("-" * 75)

        # Print Rejected Topics Audit Log from SQLite
        rejected_list = MemoryRepository.get_rejected_topics(db, agent_id=agent.id, limit=5)
        if rejected_list:
            print("\n" + "-" * 75)
            print("                 RECENT REJECTED TOPICS (SQLITE AUDIT LOG)")
            print("-" * 75)
            for r in rejected_list:
                print(f"  • Title : '{r.title[:55]}...'")
                print(f"    Reason: {r.reason}")
                print(f"    Scores: {r.judge_scores_json}")
                print()

        print("=" * 75)

    finally:
        db.close()

if __name__ == "__main__":
    run_phase3_cycle_test()
