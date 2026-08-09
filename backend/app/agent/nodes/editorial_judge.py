import logging
from typing import List

from backend.app.agent.state import AgentState, JudgeVerdict
from backend.app.agent.llm import get_structured_llm
from backend.app.agent.persona.schema import EditorialThresholds
from backend.app.memory.db import SessionLocal
from backend.app.memory.repository import MemoryRepository
from backend.app.agent.prompts.editorial_judge import (
    EDITORIAL_JUDGE_SYSTEM_PROMPT,
    EDITORIAL_JUDGE_USER_PROMPT,
)

logger = logging.getLogger("autonomous_agent.agent.nodes.editorial_judge")


def _recent_posts_context(agent_id: str, limit: int) -> str:
    """
    Recent posts, for repetition checks across story, angle and theme.

    A new URL is not a new editorial idea, so the judge sees what was actually said
    rather than only the titles.
    """
    if not agent_id:
        return "None yet - this would be the first post."
    db = SessionLocal()
    try:
        posts = MemoryRepository.get_recent_posts(db, agent_id, limit=limit)
        if not posts:
            return "None yet - this would be the first post."
        return "\n\n".join(
            f"[{p.created_at}] {p.topic_title or '(untitled)'}\n{(p.text or '')[:400]}"
            for p in posts
        )
    except Exception as err:  # memory must never block judging
        logger.debug(f"Could not load recent posts for the judge: {err}")
        return "Unavailable."
    finally:
        db.close()


def failed_thresholds(verdict: JudgeVerdict, thresholds: EditorialThresholds) -> List[str]:
    """
    Every reason this candidate falls short of the persona's publishing bar.

    Enforced here rather than trusted from `decision`, because a model will otherwise
    say "publish" while its own scores say the opposite.
    """
    s = verdict.scores
    failures: List[str] = []

    if verdict.disqualifier:
        failures.append(f"disqualified: {verdict.disqualifier}")
    if verdict.credibility == "low":
        failures.append("credibility is low")
    if verdict.editorial_value == "none":
        failures.append("no editorial value")

    for label, score, minimum in (
        ("evidence_strength", s.evidence_strength, thresholds.min_evidence_strength),
        ("editorial_value", s.editorial_value, thresholds.min_editorial_value),
        ("persona_fit", s.persona_fit, thresholds.min_persona_fit),
        ("explainability", s.explainability, thresholds.min_explainability),
    ):
        if score < minimum:
            failures.append(f"{label} {score} < {minimum}")

    return failures


def editorial_judge_node(state: AgentState) -> AgentState:
    """
    Decide whether a candidate deserves publishing, and if so settle the angle.

    This node owns the question "what deserves to be said?". The writer owns "how do we
    explain it?" and receives the answer as writer_context rather than re-reading the
    raw source and choosing for itself.
    """
    cand = state.get("current_candidate")
    persona = state["persona"]

    if not cand:
        logger.warning("No candidate provided to editorial_judge_node.")
        state["judge_verdict"] = None
        return state

    try:
        structured_llm = get_structured_llm(JudgeVerdict, temperature=0.2)
        thresholds = persona.editorial_thresholds

        system_msg = EDITORIAL_JUDGE_SYSTEM_PROMPT.format(
            persona_name=persona.name,
            persona_domain=persona.domain,
            persona_bio=persona.bio,
            core_question=persona.voice_guidelines.core_question or "What does this actually change?",
            stable_interests=", ".join(persona.stable_interests) or "None",
            min_evidence_strength=thresholds.min_evidence_strength,
            min_editorial_value=thresholds.min_editorial_value,
            min_persona_fit=thresholds.min_persona_fit,
            min_explainability=thresholds.min_explainability,
        )

        user_msg = EDITORIAL_JUDGE_USER_PROMPT.format(
            title=cand.title,
            url=cand.url,
            source_type=cand.source,
            source_name=cand.source,
            published_at=cand.published_at,
            discovered_at=getattr(cand, "discovered_at", "this cycle"),
            content=cand.summary,
            recent_posts=_recent_posts_context(
                state.get("agent_id", ""), persona.memory.recent_posts_for_context
            ),
        )

        verdict: JudgeVerdict = structured_llm.invoke([
            ("system", system_msg),
            ("user", user_msg),
        ])

        # The persona's bar is enforced in code. A model that scores a candidate below
        # the threshold and still says "publish" is overruled.
        failures = failed_thresholds(verdict, thresholds)
        if failures and verdict.decision == "publish":
            logger.info(f"Overruling model 'publish' for '{cand.title[:45]}...': {'; '.join(failures)}")
            verdict.decision = "reject"
            verdict.reasoning = (
                f"{verdict.reasoning} [Below {persona.name}'s publishing bar: {'; '.join(failures)}.]"
            )

        # A passing verdict without a handoff would leave the writer to invent its own
        # angle, which is the failure mode this split exists to prevent.
        if verdict.decision == "publish" and verdict.writer_context is None:
            logger.warning(f"'{cand.title[:45]}...' passed without writer_context; rejecting.")
            verdict.decision = "reject"
            verdict.reasoning = f"{verdict.reasoning} [No editorial handoff produced.]"

        # Sources come from the judge's verified context, never from the candidate pool.
        if verdict.writer_context is not None and not verdict.writer_context.sources:
            verdict.writer_context.sources = [cand.url] if cand.url else []

        s = verdict.scores
        logger.info(
            f"Editorial Judge for '{cand.title[:45]}...': {verdict.decision.upper()} "
            f"(evidence={s.evidence_strength}, value={s.editorial_value}, fit={s.persona_fit}, "
            f"timely={s.timeliness}, explain={s.explainability}, cred={verdict.credibility}"
            + (f", disqualifier={verdict.disqualifier}" if verdict.disqualifier else "")
            + ")"
        )

        state["judge_verdict"] = verdict

    except Exception as e:
        # An API failure is not an editorial decision. Recording it as one fabricates
        # scores, pollutes the public rejection log, and hides outages.
        logger.error(f"Editorial judge could not evaluate '{cand.title[:45]}...': {e}", exc_info=True)
        state["judge_verdict"] = None
        state["node_error"] = f"editorial_judge: {e}"

    return state
