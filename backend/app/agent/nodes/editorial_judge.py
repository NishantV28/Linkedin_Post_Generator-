import logging
from typing import List, Tuple

from backend.app.agent.state import AgentState, JudgeVerdict
from backend.app.agent.llm import get_llm
from backend.app.agent.persona.schema import EditorialThresholds
from backend.app.memory.db import SessionLocal
from backend.app.memory.repository import MemoryRepository
from backend.app.agent.prompts.editorial_judge import (
    EDITORIAL_JUDGE_SYSTEM_PROMPT,
    EDITORIAL_JUDGE_USER_PROMPT
)

logger = logging.getLogger("autonomous_agent.agent.nodes.editorial_judge")

RECENT_TITLES_FOR_CONTEXT = 8


def _recent_titles(agent_id: str) -> str:
    """Recently published titles, so the judge can reject repeats the embeddings missed."""
    if not agent_id:
        return "None yet - this would be the first post."
    db = SessionLocal()
    try:
        posts = MemoryRepository.get_recent_posts(db, agent_id, limit=RECENT_TITLES_FOR_CONTEXT)
        if not posts:
            return "None yet - this would be the first post."
        return "\n".join(f"- {p.topic_title or '(untitled)'}" for p in posts)
    except Exception as err:  # memory must never block judging
        logger.debug(f"Could not load recent titles for anti-repetition context: {err}")
        return "Unavailable."
    finally:
        db.close()


def _failed_thresholds(verdict: JudgeVerdict, thresholds: EditorialThresholds) -> List[str]:
    """Which of the persona's minimum scores this candidate misses."""
    checks: List[Tuple[str, float, float]] = [
        ("relevance", verdict.relevance, thresholds.min_relevance),
        ("novelty", verdict.novelty, thresholds.min_novelty),
        ("credibility", verdict.credibility, thresholds.min_credibility),
        ("timeliness", verdict.timeliness, thresholds.min_timeliness),
    ]
    return [f"{name} {score} < {minimum}" for name, score, minimum in checks if score < minimum]

def editorial_judge_node(state: AgentState) -> AgentState:
    """
    Evaluates current candidate topic against persona thresholds using LLM structured output.
    """
    cand = state["current_candidate"]
    persona = state["persona"]
    
    if not cand:
        logger.warning("No candidate provided to editorial_judge_node.")
        state["judge_verdict"] = None
        return state

    try:
        llm = get_llm(temperature=0.2)
        structured_llm = llm.with_structured_output(JudgeVerdict)

        # Build prompt inputs
        stable_interests_str = ", ".join(persona.stable_interests)
        thresholds = persona.editorial_thresholds

        system_msg = EDITORIAL_JUDGE_SYSTEM_PROMPT.format(
            persona_name=persona.name,
            persona_domain=persona.domain,
            persona_bio=persona.bio,
            stable_interests=stable_interests_str,
            min_relevance=thresholds.min_relevance,
            min_novelty=thresholds.min_novelty,
            min_credibility=thresholds.min_credibility,
            min_timeliness=thresholds.min_timeliness
        )

        user_msg = EDITORIAL_JUDGE_USER_PROMPT.format(
            source=cand.source,
            title=cand.title,
            summary=cand.summary,
            url=cand.url,
            published_at=cand.published_at,
            recent_post_titles=_recent_titles(state.get("agent_id", ""))
        )

        verdict: JudgeVerdict = structured_llm.invoke([
            ("system", system_msg),
            ("user", user_msg)
        ])

        # The persona's thresholds are enforced here, not trusted to the model. An LLM
        # that scores a candidate below the bar and still says "pass" is overruled.
        failures = _failed_thresholds(verdict, thresholds)
        if failures and verdict.decision.lower() == "pass":
            logger.info(
                f"Overruling model 'pass' for '{cand.title[:45]}...': {'; '.join(failures)}"
            )
            verdict.decision = "reject"
            verdict.reasoning = (
                f"{verdict.reasoning} "
                f"[Below {persona.name}'s publishing bar: {'; '.join(failures)}.]"
            )

        logger.info(
            f"Editorial Judge Verdict for '{cand.title[:45]}...': {verdict.decision.upper()} "
            f"(Rel={verdict.relevance}, Nov={verdict.novelty}, "
            f"Cred={verdict.credibility}, Time={verdict.timeliness})"
        )

        state["judge_verdict"] = verdict

    except Exception as e:
        logger.error(f"Error in editorial_judge_node LLM invocation: {e}", exc_info=True)
        # Fallback conservative rejection if LLM fails
        state["judge_verdict"] = JudgeVerdict(
            relevance=1,
            novelty=1,
            credibility=1,
            timeliness=1,
            decision="reject",
            reasoning=f"Evaluation failed due to runtime error: {str(e)}"
        )

    return state
