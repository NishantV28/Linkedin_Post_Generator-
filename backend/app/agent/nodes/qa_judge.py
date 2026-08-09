import logging

from backend.app.agent.state import AgentState, QAVerdict
from backend.app.agent.llm import get_structured_llm
from backend.app.agent.persona.voice import (
    borrowed_phrases,
    closing_takeaway,
    em_dashes,
    overlong_sentences,
    parenthetical_definitions,
    scaffolding_leaks,
)
from backend.app.memory.db import SessionLocal
from backend.app.memory.repository import MemoryRepository
from backend.app.agent.prompts.qa_judge import (
    QA_JUDGE_SYSTEM_PROMPT,
    QA_JUDGE_USER_PROMPT,
)

logger = logging.getLogger("autonomous_agent.agent.nodes.qa_judge")


def _recent_post_texts(agent_id: str, limit: int) -> str:
    """Recent post bodies, so the repetition check has something to compare against."""
    if not agent_id:
        return "None yet - this would be the first post."
    db = SessionLocal()
    try:
        posts = MemoryRepository.get_recent_posts(db, agent_id, limit=limit)
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


def _editorial_context(state: AgentState) -> str:
    """The factual boundary the draft must stay inside."""
    verdict = state.get("judge_verdict")
    trend = state.get("coverage_trend")

    if verdict and verdict.writer_context:
        c = verdict.writer_context
        evidence = "\n".join(f"- {e}" for e in c.evidence) or "- none"
        limitations = "\n".join(f"- {l}" for l in c.limitations) or "- none"
        return (
            f"Editorial angle: {verdict.editorial_angle}\n"
            f"Core claim: {c.core_claim}\n"
            f"Mechanism: {c.mechanism}\n"
            f"Evidence:\n{evidence}\n"
            f"Limitations:\n{limitations}\n"
            f"Why now: {c.why_now or 'no timeliness evidence supplied'}"
        )

    # A reflection has no source candidate; its claims are grounded in the agent's own
    # published history instead.
    if trend:
        titles = "\n".join(f"- {t}" for t in trend["titles"])
        return (
            "This is a reflection on the persona's own recent coverage. It must not "
            f"misrepresent these posts:\n{titles}"
        )

    return "No editorial context available."


def qa_judge_node(state: AgentState) -> AgentState:
    """
    Gate a draft on voice, grounding, repetition, plain language and single-idea focus.

    Deterministic rules are applied in code and override the model verdict; the model
    judges only what cannot be decided by inspecting the text.
    """
    draft = state.get("draft")
    persona = state["persona"]

    if not draft:
        logger.warning("Missing draft in qa_judge_node.")
        return state

    try:
        voice = persona.voice_guidelines
        structured_llm = get_structured_llm(QAVerdict, temperature=0.1)

        system_msg = QA_JUDGE_SYSTEM_PROMPT.format(
            persona_name=persona.name,
            tone=voice.tone,
            sentence_rhythm=voice.sentence_rhythm,
            forbidden_phrases=", ".join(voice.forbidden_phrases) or "None",
            core_question=voice.core_question or "What does this actually change?",
        )

        user_msg = QA_JUDGE_USER_PROMPT.format(
            editorial_context=_editorial_context(state),
            draft_text=draft.text,
            recent_posts=_recent_post_texts(
                state.get("agent_id", ""), persona.memory.recent_posts_for_context
            ),
        )

        verdict: QAVerdict = structured_llm.invoke([
            ("system", system_msg),
            ("user", user_msg),
        ])

        # Deterministic style rules. These cannot drift between runs, so they override
        # the model rather than relying on it to notice.
        problems = []
        text = draft.text

        found_forbidden = [p for p in voice.forbidden_phrases if p.lower() in text.lower()]
        if found_forbidden:
            problems.append(f"contains forbidden phrase(s): {', '.join(found_forbidden)}")

        if voice.forbid_em_dashes and em_dashes(text):
            problems.append("uses an em-dash. Use commas, periods or ordinary connecting words")

        long_ones = overlong_sentences(text, voice.max_sentence_words)
        if long_ones:
            problems.append(
                f"has {len(long_ones)} sentence(s) over {voice.max_sentence_words} words. "
                f"Split them, starting with: {long_ones[0][:70]}..."
            )

        if voice.forbid_parenthetical_definitions:
            glosses = parenthetical_definitions(text)
            if glosses:
                problems.append(
                    f"defines jargon in brackets: {glosses[0]}. Rewrite the term in plain "
                    f"words instead of glossing it"
                )

        if voice.forbid_closing_takeaway:
            endings = closing_takeaway(text)
            if endings:
                problems.append(
                    f"appends a closing takeaway: {endings[0]}. End when the mechanism is "
                    f"explained; the point being made is the ending"
                )

        leaks = scaffolding_leaks(text)
        if leaks:
            problems.append(
                f"narrates its own structure: {leaks[0]}. The beats are how the post is "
                f"built, not words in it"
            )

        lifted = borrowed_phrases(text, voice.worked_example or "")
        if lifted:
            problems.append(
                f"copies wording from the style example: {lifted[0]}. The example shows "
                f"shape, not sentences to reuse"
            )

        words = len(text.split())
        if voice.min_post_words and words < voice.min_post_words:
            problems.append(
                f"is too thin at {words} words (target {voice.min_post_words}-"
                f"{voice.max_post_words}). Explain the mechanism further"
            )
        elif voice.max_post_words and words > voice.max_post_words:
            problems.append(
                f"runs long at {words} words (maximum {voice.max_post_words}). Cut whichever "
                f"sentence carries the least new information"
            )

        # Collect every reason to revise into one message. Replacing the model's
        # feedback with the programmatic findings made the writer fix one fault and
        # reintroduce another each round until the revision limit ran out.
        reasons = []
        model_failures = {
            "plain_language_clear": "uses specialist language a general reader cannot follow",
            "single_idea": "explains more than one idea, or drifts from the selected angle",
            "factually_grounded": "makes a claim the judge's context does not support",
            "non_repetitive": "repeats a recent post's story, angle or theme",
        }
        for field, description in model_failures.items():
            if not getattr(verdict, field):
                reasons.append(description)
        if verdict.verdict == "revise" and verdict.feedback and not reasons:
            reasons.append(verdict.feedback.rstrip("."))
        reasons.extend(problems)

        if reasons:
            if problems:
                verdict.voice_consistent = False
            verdict.verdict = "revise"
            detail = f" Reviewer notes: {verdict.feedback}" if verdict.feedback else ""
            verdict.feedback = (
                "Draft " + "; also ".join(reasons)
                + ". Fix ALL of these in one rewrite - correcting one and reintroducing "
                  "another wastes the revision." + detail
            )

        logger.info(
            f"QA Judge: {verdict.verdict.upper()} (voice={verdict.voice_consistent}, "
            f"grounded={verdict.factually_grounded}, nonrep={verdict.non_repetitive}, "
            f"plain={verdict.plain_language_clear}, one_idea={verdict.single_idea})"
        )

        state["qa_verdict"] = verdict

    except Exception as e:
        # Fail closed. Auto-passing on error published an unreviewed draft, which is
        # the opposite of what a quality gate is for.
        logger.error(f"QA judge could not review the draft: {e}", exc_info=True)
        state["qa_verdict"] = None
        state["node_error"] = f"qa_judge: {e}"

    return state
