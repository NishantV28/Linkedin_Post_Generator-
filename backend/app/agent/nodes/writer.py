import logging
from backend.app.agent.state import AgentState, DraftPost
from backend.app.agent.llm import get_llm
from backend.app.memory.db import SessionLocal
from backend.app.memory.hybrid_retriever import HybridRetriever
from backend.app.agent.prompts.writer import (
    WRITER_SYSTEM_PROMPT,
    WRITER_USER_PROMPT
)

logger = logging.getLogger("autonomous_agent.agent.nodes.writer")

def writer_node(state: AgentState) -> AgentState:
    """
    Generates or revises a persona-voiced LinkedIn post draft using ChatOpenAI with structured output.
    Uses hybrid-retrieved past posts for few-shot style anchoring.
    """
    cand = state["current_candidate"]
    persona = state["persona"]
    judge_verdict = state.get("judge_verdict")
    qa_verdict = state.get("qa_verdict")
    retry_count = state.get("retry_count", 0)

    if not cand:
        logger.warning("No candidate provided to writer_node.")
        return state

    try:
        # Retrieve topically relevant past posts for few-shot style anchoring
        few_shot_context = "No previous posts in memory (first post for persona)."
        try:
            db = SessionLocal()
            relevant_posts = HybridRetriever.get_relevant_context(
                agent_id=state.get("agent_id", "default"),
                query_text=f"{cand.title} {cand.summary}",
                db=db,
                top_k=2
            )
            db.close()

            if relevant_posts:
                anchor_snippets = []
                for idx, p in enumerate(relevant_posts, 1):
                    anchor_snippets.append(f"Anchor #{idx}:\nText: {p['text']}\nRationale: {p.get('rationale', 'N/A')}")
                few_shot_context = "\n\n".join(anchor_snippets)
        except Exception as err:
            logger.debug(f"Could not retrieve few-shot context from memory: {err}")

        # Build prompt inputs
        voice = persona.voice_guidelines
        forbidden_str = ", ".join(voice.forbidden_phrases) if voice.forbidden_phrases else "None"
        judge_reasoning = judge_verdict.reasoning if judge_verdict else "Approved candidate."

        revision_section = ""
        if qa_verdict and qa_verdict.verdict == "revise":
            revision_section = f"REVISION REQUEST (Attempt #{retry_count}):\nPrevious QA Feedback: {qa_verdict.feedback}\nPlease fix the issues above in this new draft."

        system_msg = WRITER_SYSTEM_PROMPT.format(
            persona_name=persona.name,
            persona_domain=persona.domain,
            persona_bio=persona.bio,
            tone=voice.tone,
            sentence_rhythm=voice.sentence_rhythm,
            forbidden_phrases=forbidden_str,
            few_shot_context=few_shot_context
        )

        user_msg = WRITER_USER_PROMPT.format(
            title=cand.title,
            summary=cand.summary,
            source=cand.source,
            url=cand.url,
            judge_reasoning=judge_reasoning,
            revision_feedback_section=revision_section
        )

        llm = get_llm(temperature=0.7)
        structured_llm = llm.with_structured_output(DraftPost)

        draft: DraftPost = structured_llm.invoke([
            ("system", system_msg),
            ("user", user_msg)
        ])

        logger.info(f"Writer node generated draft for '{cand.title[:45]}...' ({len(draft.text)} chars)")
        state["draft"] = draft

    except Exception as e:
        logger.error(f"Error in writer_node LLM invocation: {e}", exc_info=True)
        # Basic fallback draft if LLM fails
        state["draft"] = DraftPost(
            text=f"Interesting developments in {persona.domain}: {cand.title}. {cand.summary[:150]}... Read more: {cand.url}",
            rationale_selected=f"Selected for relevance to {persona.domain}.",
            rationale_why_now="Timely technical update."
        )

    return state
