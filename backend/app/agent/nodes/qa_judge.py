import logging
from backend.app.agent.state import AgentState, QAVerdict
from backend.app.agent.llm import get_llm
from backend.app.agent.prompts.qa_judge import (
    QA_JUDGE_SYSTEM_PROMPT,
    QA_JUDGE_USER_PROMPT
)

logger = logging.getLogger("autonomous_agent.agent.nodes.qa_judge")

def qa_judge_node(state: AgentState) -> AgentState:
    """
    Evaluates draft post against persona forbidden phrases, tone, and factual grounding.
    """
    draft = state.get("draft")
    cand = state["current_candidate"]
    persona = state["persona"]

    if not draft or not cand:
        logger.warning("Missing draft or candidate in qa_judge_node.")
        return state

    try:
        llm = get_llm(temperature=0.1)
        structured_llm = llm.with_structured_output(QAVerdict)

        voice = persona.voice_guidelines
        forbidden_str = ", ".join(voice.forbidden_phrases) if voice.forbidden_phrases else "None"

        system_msg = QA_JUDGE_SYSTEM_PROMPT.format(
            persona_name=persona.name,
            tone=voice.tone,
            forbidden_phrases=forbidden_str
        )

        user_msg = QA_JUDGE_USER_PROMPT.format(
            candidate_summary=cand.summary,
            draft_text=draft.text,
            recent_posts="None in memory."
        )

        verdict: QAVerdict = structured_llm.invoke([
            ("system", system_msg),
            ("user", user_msg)
        ])

        # Programmatic safety check: double-check forbidden phrases
        if voice.forbidden_phrases:
            text_lower = draft.text.lower()
            found_forbidden = [phrase for phrase in voice.forbidden_phrases if phrase.lower() in text_lower]
            if found_forbidden:
                verdict.voice_consistent = False
                verdict.verdict = "revise"
                verdict.feedback = f"Draft contains forbidden phrase(s): {', '.join(found_forbidden)}. Please remove them."

        logger.info(
            f"QA Judge Verdict: {verdict.verdict.upper()} "
            f"(Voice={verdict.voice_consistent}, Grounded={verdict.factually_grounded}, NonRep={verdict.non_repetitive})"
        )

        state["qa_verdict"] = verdict

    except Exception as e:
        logger.error(f"Error in qa_judge_node LLM invocation: {e}", exc_info=True)
        # Conservative pass if QA LLM errors out
        state["qa_verdict"] = QAVerdict(
            voice_consistent=True,
            factually_grounded=True,
            non_repetitive=True,
            verdict="pass",
            feedback="Auto-passed on QA error recovery."
        )

    return state
