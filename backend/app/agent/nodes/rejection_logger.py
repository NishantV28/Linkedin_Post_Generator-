import logging
from typing import Any, Dict, Tuple

from backend.app.agent.state import AgentState
from backend.app.memory.db import SessionLocal
from backend.app.memory.repository import MemoryRepository

logger = logging.getLogger("autonomous_agent.agent.nodes.rejection_logger")


def _describe_rejection(state: AgentState) -> Tuple[str, str, Dict[str, Any]]:
    """
    Work out which stage rejected this candidate, and report *that stage's* reasoning.

    Reporting the editorial judge's text for a QA rejection produces entries that
    contradict themselves - a topic marked rejected whose reason ends "leading to a
    pass" - and these are served publicly by /api/agent/rejected.
    """
    judge_verdict = state.get("judge_verdict")
    qa_verdict = state.get("qa_verdict")

    editorial_scores: Dict[str, Any] = {}
    if judge_verdict:
        editorial_scores = {
            "evidence_strength": judge_verdict.scores.evidence_strength,
            "editorial_value_score": judge_verdict.scores.editorial_value,
            "persona_fit": judge_verdict.scores.persona_fit,
            "timeliness": judge_verdict.scores.timeliness,
            "explainability": judge_verdict.scores.explainability,
            "credibility": judge_verdict.credibility,
            "editorial_value": judge_verdict.editorial_value,
            "disqualifier": judge_verdict.disqualifier,
            "decision": judge_verdict.decision,
        }

    # A QA verdict only exists once editorial review has passed, so its presence
    # with a non-pass result identifies the rejecting stage.
    if qa_verdict and qa_verdict.verdict.lower() != "pass":
        return (
            "[QA Judge Rejected after revision limit]",
            qa_verdict.feedback or "Draft did not meet quality standards after revision.",
            {
                "stage": "qa",
                "voice_consistent": qa_verdict.voice_consistent,
                "factually_grounded": qa_verdict.factually_grounded,
                "non_repetitive": qa_verdict.non_repetitive,
                "verdict": qa_verdict.verdict,
                "editorial_scores": editorial_scores,
            },
        )

    reasoning = judge_verdict.reasoning if judge_verdict else "Topic rejected."
    return (
        "[Editorial Judge Rejected]",
        reasoning,
        {"stage": "editorial", **editorial_scores},
    )


def log_candidate_rejection(state: AgentState) -> AgentState:
    """
    Persist the current candidate's rejection with the rejecting stage's own reasoning,
    and record it on the state so a later published post can cite what it passed over.
    """
    cand = state.get("current_candidate")
    agent_id = state.get("agent_id", "")

    if not cand or not agent_id:
        return state

    prefix, reasoning, scores = _describe_rejection(state)
    reason = f"{prefix} {reasoning}".strip()

    db = SessionLocal()
    try:
        MemoryRepository.save_rejection(
            db=db,
            agent_id=agent_id,
            title=cand.title,
            source_url=cand.url,
            reason=reason,
            judge_scores=scores
        )
        logger.info(f"Logged rejection for '{cand.title[:45]}...' (Reason: {reasoning[:60]}...)")
        state["rejected_count"] = state.get("rejected_count", 0) + 1

        # Kept for the published post's "chosen over" rationale.
        considered = list(state.get("rejected_this_cycle") or [])
        considered.append({
            "title": cand.title,
            "stage": scores.get("stage", "editorial"),
            "reason": reasoning,
        })
        state["rejected_this_cycle"] = considered

    except Exception as e:
        logger.error(f"Error logging rejection: {e}", exc_info=True)
    finally:
        db.close()

    return state
