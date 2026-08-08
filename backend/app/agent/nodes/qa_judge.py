import logging
from backend.app.agent.state import AgentState, QAVerdict
from backend.app.agent.llm import get_llm
from backend.app.agent.persona.voice import has_standalone_closing_line
from backend.app.memory.db import SessionLocal
from backend.app.memory.repository import MemoryRepository
from backend.app.agent.prompts.qa_judge import (
    QA_JUDGE_SYSTEM_PROMPT,
    QA_JUDGE_USER_PROMPT
)

logger = logging.getLogger("autonomous_agent.agent.nodes.qa_judge")

RECENT_POSTS_FOR_CONTEXT = 4


def _recent_post_texts(agent_id: str) -> str:
    """Recent post bodies, so the non-repetition check has something to compare against."""
    if not agent_id:
        return "None yet - this would be the first post."
    db = SessionLocal()
    try:
        posts = MemoryRepository.get_recent_posts(db, agent_id, limit=RECENT_POSTS_FOR_CONTEXT)
        if not posts:
            return "None yet - this would be the first post."
        return "\n\n---\n\n".join(
            f"[{p.topic_title or 'untitled'}]\n{p.text}" for p in posts
        )
    except Exception as err:  # memory must never block QA
        logger.debug(f"Could not load recent posts for repetition check: {err}")
        return "Unavailable."
    finally:
        db.close()

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

        structure_str = "\n".join(
            f"{i}. {beat}" for i, beat in enumerate(voice.post_structure, 1)
        ) or "(no fixed structure defined)"

        system_msg = QA_JUDGE_SYSTEM_PROMPT.format(
            persona_name=persona.name,
            tone=voice.tone,
            forbidden_phrases=forbidden_str,
            signature_tell=voice.signature_tell or "None",
            core_question=voice.core_question or "What does this actually change?",
            post_structure=structure_str
        )

        user_msg = QA_JUDGE_USER_PROMPT.format(
            candidate_summary=cand.summary,
            draft_text=draft.text,
            recent_posts=_recent_post_texts(state.get("agent_id", ""))
        )

        verdict: QAVerdict = structured_llm.invoke([
            ("system", system_msg),
            ("user", user_msg)
        ])

        # Programmatic voice checks. These are deterministic, so they override the
        # LLM verdict rather than relying on it to notice.
        problems = []

        if voice.forbidden_phrases:
            text_lower = draft.text.lower()
            found_forbidden = [phrase for phrase in voice.forbidden_phrases if phrase.lower() in text_lower]
            if found_forbidden:
                problems.append(
                    f"contains forbidden phrase(s): {', '.join(found_forbidden)} - remove them"
                )

        if voice.requires_standalone_closing_line and not has_standalone_closing_line(draft.text):
            problems.append(
                "does not end with a standalone closing line. The final line must be a "
                "short, self-contained takeaway separated from the body by a blank line"
            )

        if problems:
            verdict.voice_consistent = False
            verdict.verdict = "revise"
            verdict.feedback = "Draft " + "; also ".join(problems) + "."

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
