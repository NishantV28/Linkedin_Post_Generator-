import logging
from backend.app.agent.state import AgentState, DraftPost
from backend.app.agent.llm import get_llm
from backend.app.memory.db import SessionLocal
from backend.app.memory.hybrid_retriever import HybridRetriever
from backend.app.agent.persona.voice import ensure_closing_line_separation
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

    # Count the revision here rather than in the router: LangGraph rebuilds state
    # for conditional-edge functions, so mutations made there are never persisted.
    if qa_verdict and qa_verdict.verdict.lower() == "revise":
        retry_count += 1
        state["retry_count"] = retry_count

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

        structure_str = "\n".join(
            f"{i}. {beat}" for i, beat in enumerate(voice.post_structure, 1)
        ) or "1. Lead with the substance.\n2. Explain the one thing that matters.\n3. Stop."

        # Before any real posts exist the worked example is the only voice anchor there is.
        if few_shot_context.startswith("No previous posts") and voice.worked_example:
            few_shot_context = f"No posts published yet. Match the tone of the example above."

        revision_section = ""
        if qa_verdict and qa_verdict.verdict.lower() == "revise":
            revision_section = f"REVISION REQUEST (Attempt #{retry_count}):\nPrevious QA Feedback: {qa_verdict.feedback}\nPlease fix the issues above in this new draft."

        system_msg = WRITER_SYSTEM_PROMPT.format(
            persona_name=persona.name,
            persona_domain=persona.domain,
            persona_bio=persona.bio,
            core_question=voice.core_question or "What does this actually change?",
            post_structure=structure_str,
            worked_example=voice.worked_example or "(no example available)",
            tone=voice.tone,
            sentence_rhythm=voice.sentence_rhythm,
            signature_tell=voice.signature_tell or "None",
            stable_interests=", ".join(persona.stable_interests) or "None",
            forbidden_phrases=forbidden_str,
            few_shot_context=few_shot_context
        )

        user_msg = WRITER_USER_PROMPT.format(
            title=cand.title,
            summary=cand.summary,
            source=cand.source,
            url=cand.url,
            published_at=cand.published_at,
            judge_reasoning=judge_reasoning,
            revision_feedback_section=revision_section
        )

        llm = get_llm(temperature=0.7)
        structured_llm = llm.with_structured_output(DraftPost)

        draft: DraftPost = structured_llm.invoke([
            ("system", system_msg),
            ("user", user_msg)
        ])

        if persona.voice_guidelines.requires_standalone_closing_line:
            draft.text = ensure_closing_line_separation(draft.text)

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
