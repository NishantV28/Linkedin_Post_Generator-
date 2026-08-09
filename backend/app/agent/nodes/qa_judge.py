import logging
from backend.app.agent.state import AgentState, QAVerdict
from backend.app.agent.llm import get_structured_llm
from backend.app.agent.persona.voice import (
    borrowed_phrases,
    has_standalone_closing_line,
    scaffolding_leaks,
)
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
    cand = state.get("current_candidate")
    persona = state["persona"]
    trend = state.get("coverage_trend")

    if not draft:
        logger.warning("Missing draft in qa_judge_node.")
        return state

    # Grounding is chosen by the cycle's mode, not by whether a candidate happens to
    # be present. Preferring the candidate meant a reflection could be graded against
    # an unrelated paper, and QA feedback then pushed the writer into covering it.
    is_reflection = state.get("mode") == "reflection"

    if cand is not None and not is_reflection:
        grounding = cand.summary
        subject = cand.title
    elif trend:
        grounding = (
            "The agent's own recent posts, which this reflection must not "
            "misrepresent:\n" + "\n".join(f"- {t}" for t in trend["titles"])
        )
        subject = "reflection on recent coverage"
    else:
        logger.warning("Missing candidate and coverage trend in qa_judge_node.")
        return state

    try:
        structured_llm = get_structured_llm(QAVerdict, temperature=0.1)

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
            candidate_summary=grounding,
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

        lifted = borrowed_phrases(draft.text, voice.worked_example or "")
        if lifted:
            quoted = "; ".join(f'"{p}"' for p in lifted[:3])
            problems.append(
                f"copies wording from the style example ({quoted}) - the example shows the "
                f"shape of a post, not sentences to reuse. Write these in your own words "
                f"about this specific source"
            )

        leaks = scaffolding_leaks(draft.text)
        if leaks:
            quoted = "; ".join(f'"{l}"' for l in leaks[:3])
            problems.append(
                f"narrates its own structure ({quoted}). The beats are how you build the "
                f"post, not words to write down - the reader should never see them. Say the "
                f"thing itself instead of announcing which beat you are on"
            )

        words = len(draft.text.split())
        if voice.min_post_words and words < voice.min_post_words:
            problems.append(
                f"is too thin at {words} words (target {voice.min_post_words}-"
                f"{voice.max_post_words}). Add the mechanism in plain language, what it "
                f"changes for someone building on this, or the catch - not more adjectives"
            )
        elif voice.max_post_words and words > voice.max_post_words:
            problems.append(
                f"runs long at {words} words (target {voice.min_post_words}-"
                f"{voice.max_post_words}). Cut whichever paragraph carries the least new information"
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

        # Plain language is a hard gate: this persona's entire value is translation, so
        # an untranslated post has failed even when everything else is correct.
        if not verdict.plain_language_clear and verdict.verdict.lower() == "pass":
            verdict.verdict = "revise"
            verdict.feedback = (
                "Draft uses specialist language a general reader cannot follow. "
                + (verdict.feedback or "")
            ).strip()

        logger.info(
            f"QA Judge Verdict: {verdict.verdict.upper()} "
            f"(Voice={verdict.voice_consistent}, Grounded={verdict.factually_grounded}, "
            f"NonRep={verdict.non_repetitive}, PlainLanguage={verdict.plain_language_clear})"
        )

        state["qa_verdict"] = verdict

    except Exception as e:
        # Fail closed. Auto-passing on error meant an API blip published an unreviewed
        # draft - the opposite of what a quality gate is for.
        logger.error(f"QA judge could not review draft for '{subject[:45]}...': {e}", exc_info=True)
        state["qa_verdict"] = None
        state["node_error"] = f"qa_judge: {e}"

    return state
