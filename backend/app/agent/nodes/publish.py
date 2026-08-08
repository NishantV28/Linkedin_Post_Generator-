import logging
from backend.app.agent.state import AgentState
from backend.app.memory.db import SessionLocal
from backend.app.memory.repository import MemoryRepository

logger = logging.getLogger("autonomous_agent.agent.nodes.publish")

def publish_node(state: AgentState) -> AgentState:
    """
    Persists accepted post to SQLite relational memory and ChromaDB vector store.
    """
    draft = state.get("draft")
    cand = state["current_candidate"]
    agent_id = state.get("agent_id", "")

    if not draft or not cand or not agent_id:
        logger.error("Publish node missing required state data (draft, candidate, or agent_id).")
        state["cycle_outcome"] = "publish_error"
        return state

    full_rationale = f"Selection Rationale: {draft.rationale_selected}\nWhy Now: {draft.rationale_why_now}"
    sources = [cand.url] if cand.url else []

    db = SessionLocal()
    try:
        post_record = MemoryRepository.save_post(
            db=db,
            agent_id=agent_id,
            text=draft.text,
            rationale=full_rationale,
            sources=sources,
            topic_title=cand.title
        )

        logger.info(f"SUCCESS: Published post '{post_record.id}' for agent '{agent_id}' to SQLite + ChromaDB.")
        state["published_post"] = {
            "id": post_record.id,
            "text": post_record.text,
            "rationale": post_record.rationale,
            "sources": sources,
            "topic_title": post_record.topic_title,
            "created_at": str(post_record.created_at)
        }
        state["cycle_outcome"] = "published"

    except Exception as e:
        logger.error(f"Error publishing post to memory repository: {e}", exc_info=True)
        state["cycle_outcome"] = "publish_error"
    finally:
        db.close()

    return state
