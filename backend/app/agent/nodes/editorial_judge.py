import logging
from backend.app.agent.state import AgentState, JudgeVerdict
from backend.app.agent.llm import get_llm
from backend.app.agent.prompts.editorial_judge import (
    EDITORIAL_JUDGE_SYSTEM_PROMPT,
    EDITORIAL_JUDGE_USER_PROMPT
)

logger = logging.getLogger("autonomous_agent.agent.nodes.editorial_judge")

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
            min_credibility=thresholds.min_credibility
        )

        user_msg = EDITORIAL_JUDGE_USER_PROMPT.format(
            source=cand.source,
            title=cand.title,
            summary=cand.summary,
            url=cand.url,
            published_at=cand.published_at,
            recent_post_titles="None in memory yet."
        )

        verdict: JudgeVerdict = structured_llm.invoke([
            ("system", system_msg),
            ("user", user_msg)
        ])

        logger.info(
            f"Editorial Judge Verdict for '{cand.title[:45]}...': {verdict.decision.upper()} "
            f"(Rel={verdict.relevance}, Nov={verdict.novelty}, Cred={verdict.credibility})"
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
