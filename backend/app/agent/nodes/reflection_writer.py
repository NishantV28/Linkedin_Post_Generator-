import logging

from backend.app.agent.state import AgentState, DraftPost
from backend.app.agent.llm import get_structured_llm
from backend.app.agent.prompts.reflection import (
    REFLECTION_SYSTEM_PROMPT,
    REFLECTION_USER_PROMPT
)

logger = logging.getLogger("autonomous_agent.agent.nodes.reflection_writer")


def reflection_writer_node(state: AgentState) -> AgentState:
    """
    Write a post about the agent's own recent coverage rather than a new source.

    The pattern is detected deterministically upstream and passed in; this node only
    writes about it. Asking a model whether it notices a trend guarantees a yes.
    """
    persona = state["persona"]
    trend = state.get("coverage_trend")
    qa_verdict = state.get("qa_verdict")
    retry_count = state.get("retry_count", 0)

    if not trend:
        logger.warning("reflection_writer_node called without a detected trend.")
        state["node_error"] = "reflection_writer: no coverage trend in state"
        return state

    if qa_verdict and qa_verdict.verdict.lower() == "revise":
        retry_count += 1
        state["retry_count"] = retry_count

    try:
        voice = persona.voice_guidelines
        titles = trend["titles"]
        trend_titles = "\n".join(f"- {t}" for t in titles)

        system_msg = REFLECTION_SYSTEM_PROMPT.format(
            persona_name=persona.name,
            persona_domain=persona.domain,
            persona_bio=persona.bio,
            trend_count=len(titles),
            window_size=trend["window_size"],
            trend_titles=trend_titles,
            tone=voice.tone,
            sentence_rhythm=voice.sentence_rhythm,
            forbidden_phrases=", ".join(voice.forbidden_phrases) or "None",
        )

        revision = ""
        if qa_verdict and qa_verdict.verdict.lower() == "revise":
            revision = (
                f"\nREVISION REQUEST (attempt #{retry_count}): {qa_verdict.feedback}\n"
                "Fix the issues above in this new draft.\n"
            )

        user_msg = REFLECTION_USER_PROMPT.format(trend_detail=trend_titles) + revision

        structured_llm = get_structured_llm(DraftPost, temperature=0.6)
        draft: DraftPost = structured_llm.invoke([
            ("system", system_msg),
            ("user", user_msg)
        ])

        logger.info(f"Reflection draft generated across {len(titles)} related posts.")
        state["draft"] = draft

    except Exception as e:
        logger.error(f"Reflection writer failed: {e}", exc_info=True)
        state["draft"] = None
        state["node_error"] = f"reflection_writer: {e}"

    return state
