import logging
from backend.app.agent.state import AgentState
from backend.app.memory.db import SessionLocal
from backend.app.memory.repository import MemoryRepository

logger = logging.getLogger("autonomous_agent.agent.nodes.rejection_logger")

def log_candidate_rejection(state: AgentState, reason_prefix: str = "") -> AgentState:
    """
    Persists rejected topic metadata and judge scoring breakdown to SQLite rejected_topics table.
    """
    cand = state["current_candidate"]
    agent_id = state.get("agent_id", "")
    judge_verdict = state.get("judge_verdict")

    if not cand or not agent_id:
        return state

    reason = f"{reason_prefix} {judge_verdict.reasoning if judge_verdict else 'Topic rejected'}"
    scores = {}
    if judge_verdict:
        scores = {
            "relevance": judge_verdict.relevance,
            "novelty": judge_verdict.novelty,
            "credibility": judge_verdict.credibility,
            "timeliness": judge_verdict.timeliness,
            "decision": judge_verdict.decision
        }

    db = SessionLocal()
    try:
        MemoryRepository.save_rejection(
            db=db,
            agent_id=agent_id,
            title=cand.title,
            source_url=cand.url,
            reason=reason.strip(),
            judge_scores=scores
        )
        logger.info(f"Logged rejection for '{cand.title[:45]}...' (Reason: {reason[:60]}...)")
        state["rejected_count"] = state.get("rejected_count", 0) + 1
    except Exception as e:
        logger.error(f"Error logging rejection: {e}", exc_info=True)
    finally:
        db.close()

    return state
