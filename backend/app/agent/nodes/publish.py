import logging
from backend.app.agent.state import AgentState
from backend.app.memory.db import SessionLocal
from backend.app.memory.repository import MemoryRepository

logger = logging.getLogger("autonomous_agent.agent.nodes.publish")

# Enough to show the judgment was real without turning the rationale into a list.
MAX_CITED_ALTERNATIVES = 3


def _summarise_reason(reason: str, limit: int = 160) -> str:
    """First sentence of a rejection reason, trimmed for use inside the rationale."""
    first = reason.strip().split(". ")[0].rstrip(".")
    return first if len(first) <= limit else first[:limit].rstrip() + "..."


def _build_rationale(draft, state: AgentState) -> str:
    """
    Assemble the published rationale.

    The brief asks for why the topic was selected, why it is relevant now, and why it
    was chosen over other candidates. The third part is built from the candidates this
    cycle actually rejected, so the claim is backed by real decisions.
    """
    parts = [
        f"Selection Rationale: {draft.rationale_selected}",
        f"Why Now: {draft.rationale_why_now}",
    ]

    passed_over = state.get("rejected_this_cycle") or []
    if passed_over:
        cited = passed_over[-MAX_CITED_ALTERNATIVES:]
        lines = "\n".join(
            f"  - {item['title'][:110]} - {_summarise_reason(item['reason'])}"
            for item in cited
        )
        others = len(passed_over) - len(cited)
        suffix = f" ({others} further candidate{'s' if others != 1 else ''} also rejected.)" if others > 0 else ""
        parts.append(
            f"Chosen Over: {len(passed_over)} other candidate(s) were evaluated and "
            f"rejected this cycle.{suffix}\n{lines}"
        )
    else:
        parts.append(
            "Chosen Over: no other candidate was rejected this cycle - "
            "this was the first topic to clear the publishing bar."
        )

    return "\n".join(parts)

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

    full_rationale = _build_rationale(draft, state)
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
