"""
Editorial core: the judge decides what deserves saying, the writer decides how to say it.

These tests cover the boundary between those two responsibilities and the deterministic
rules that override the model, since each of those rules exists because a live run
violated it.
"""

import pytest
from unittest.mock import MagicMock, patch

from backend.app.agent.persona.presets import DISTILL_PRESET
from backend.app.agent.tools.schema import TopicCandidate
from backend.app.agent.state import (
    JudgeVerdict,
    EditorialScores,
    WriterContext,
    DraftPost,
    QAVerdict,
)
from backend.app.agent.nodes.editorial_judge import editorial_judge_node
from backend.app.agent.nodes.writer import writer_node
from backend.app.agent.nodes.qa_judge import qa_judge_node


CANDIDATE = TopicCandidate(
    id="c1",
    title="Selective context preference optimization",
    summary="A benchmark presenting each question in four matched forms.",
    url="https://arxiv.org/abs/2608.06377",
    source="arxiv",
    published_at="2026-08-08T10:00:00Z",
)


def writer_context(**overrides) -> WriterContext:
    base = dict(
        obvious_assumption="More retrieved context makes models more reliable.",
        interesting_turn="The problem is which passages the model trusts, not how many it sees.",
        core_claim="Weighting passages by reliability recovers accuracy lost to misleading context.",
        mechanism="Each passage is scored before generation and low-scoring ones are dropped.",
        evidence=["Four matched conditions per question", "One extra forward pass per passage"],
        limitations=["The scorer shares blind spots with the generator"],
        persona_relevance="Fits the persona's interest in retrieval and model behaviour.",
        why_now="Published this week.",
        sources=["https://arxiv.org/abs/2608.06377"],
    )
    base.update(overrides)
    return WriterContext(**base)


def judge_verdict(decision="publish", scores=None, **overrides) -> JudgeVerdict:
    base = dict(
        source_type="paper",
        disqualifier=None,
        summary="A benchmark for selective trust in retrieved context.",
        editorial_angle="Retrieval quality is a trust problem, not a coverage problem.",
        editorial_value="mechanism",
        scores=EditorialScores(**(scores or dict(
            evidence_strength=4, editorial_value=4, persona_fit=4, timeliness=4, explainability=4
        ))),
        credibility="high",
        trend_signal="Published this week.",
        decision=decision,
        reasoning="Concrete mechanism with verifiable evidence.",
        writer_context=writer_context(),
    )
    base.update(overrides)
    return JudgeVerdict(**base)


def patch_llm(module_path: str, return_value):
    """Replace the structured model in one node with a fixed response."""
    mock = MagicMock()
    mock.invoke.return_value = return_value
    return patch(f"backend.app.agent.nodes.{module_path}.get_structured_llm", return_value=mock)


# --------------------------------------------------------------------------- judge


def test_editorial_judge_passes_a_strong_candidate():
    state = {"persona": DISTILL_PRESET, "agent_id": "", "current_candidate": CANDIDATE}
    with patch_llm("editorial_judge", judge_verdict()):
        result = editorial_judge_node(state)

    verdict = result["judge_verdict"]
    assert verdict.decision == "publish"
    assert verdict.writer_context is not None, "a passing verdict must hand the writer an angle"


@pytest.mark.parametrize("label,overrides,expected", [
    ("all clear", {}, "publish"),
    ("weak evidence", {"scores": dict(evidence_strength=1, editorial_value=4, persona_fit=4, timeliness=4, explainability=4)}, "reject"),
    ("nothing worth explaining", {"scores": dict(evidence_strength=4, editorial_value=1, persona_fit=4, timeliness=4, explainability=4)}, "reject"),
    ("wrong persona", {"scores": dict(evidence_strength=4, editorial_value=4, persona_fit=1, timeliness=4, explainability=4)}, "reject"),
    ("cannot be explained", {"scores": dict(evidence_strength=4, editorial_value=4, persona_fit=4, timeliness=4, explainability=1)}, "reject"),
    ("low credibility", {"credibility": "low"}, "reject"),
    ("disqualified", {"disqualifier": "pure_announcement"}, "reject"),
    ("no editorial value", {"editorial_value": "none"}, "reject"),
])
def test_thresholds_are_enforced_in_code(label, overrides, expected):
    """A model that says 'publish' while its own scores fail the bar is overruled."""
    state = {"persona": DISTILL_PRESET, "agent_id": "", "current_candidate": CANDIDATE}
    with patch_llm("editorial_judge", judge_verdict(decision="publish", **overrides)):
        result = editorial_judge_node(state)
    assert result["judge_verdict"].decision == expected, label


def test_passing_without_a_handoff_is_rejected():
    """Without writer_context the writer would invent its own angle."""
    state = {"persona": DISTILL_PRESET, "agent_id": "", "current_candidate": CANDIDATE}
    with patch_llm("editorial_judge", judge_verdict(writer_context=None)):
        result = editorial_judge_node(state)
    assert result["judge_verdict"].decision == "reject"


# -------------------------------------------------------------------------- writer


def test_writer_renders_the_judges_angle():
    draft = DraftPost(
        text="A post about trusting retrieved passages.",
        rationale_selected="Fits retrieval interests.",
        rationale_why_now="Published this week.",
        sources=["https://wrong.example/invented"],
    )
    state = {
        "persona": DISTILL_PRESET, "agent_id": "", "current_candidate": CANDIDATE,
        "judge_verdict": judge_verdict(), "qa_verdict": None, "retry_count": 0,
    }
    with patch_llm("writer", draft):
        result = writer_node(state)

    assert result["draft"] is not None
    # Sources are the judge's verified list, never whatever the writer produced.
    assert result["draft"].sources == ["https://arxiv.org/abs/2608.06377"]


def test_writer_refuses_to_run_without_an_editorial_handoff():
    state = {
        "persona": DISTILL_PRESET, "agent_id": "", "current_candidate": CANDIDATE,
        "judge_verdict": judge_verdict(writer_context=None), "qa_verdict": None, "retry_count": 0,
    }
    result = writer_node(state)
    assert result["draft"] is None
    assert "writer_context" in result["node_error"]


# ------------------------------------------------------------------------------ QA


# Deliberately unrelated to the persona's worked example: reusing its subject matter
# trips the borrowed-phrase rule, which is itself the behaviour that rule exists to stop.
GOOD_DRAFT = (
    "Batch schedulers for model serving are normally tuned around throughput. The "
    "assumption is that packing more requests together always pays. This work measures "
    "what happens at the tail instead. Once a batch mixes short and long prompts, the "
    "short ones wait for the longest member to finish. Median latency looks healthy "
    "while the slowest tenth degrades badly. Their change is to group requests by "
    "expected output length before batching. Prompts of similar length run together, so "
    "no request waits behind work that takes ten times longer. The scheduler needs a "
    "length estimate up front, which they take from a small classifier over the prompt. "
    "That estimate is wrong often enough to matter, and every miss puts one slow request "
    "back into a fast batch."
)


def qa_state(text):
    return {
        "persona": DISTILL_PRESET, "agent_id": "", "current_candidate": CANDIDATE,
        "judge_verdict": judge_verdict(),
        "draft": DraftPost(text=text, rationale_selected="r", rationale_why_now="w",
                           sources=["https://arxiv.org/abs/2608.06377"]),
    }


def approving_verdict():
    return QAVerdict(
        voice_consistent=True, factually_grounded=True, non_repetitive=True,
        plain_language_clear=True, single_idea=True, verdict="pass", feedback="Looks good.",
    )


def test_qa_passes_a_clean_draft():
    with patch_llm("qa_judge", approving_verdict()):
        result = qa_judge_node(qa_state(GOOD_DRAFT))
    assert result["qa_verdict"].verdict == "pass"


@pytest.mark.parametrize("label,text,expected_in_feedback", [
    ("em-dash", GOOD_DRAFT + " The result is clear—for now.", "em-dash"),
    ("overlong sentence",
     GOOD_DRAFT + " " + " ".join(["word"] * 40) + ".", "over 25 words"),
    ("parenthetical gloss",
     GOOD_DRAFT + " It relies on RAG (a system that fetches external text to help answer).",
     "brackets"),
    ("appended takeaway",
     GOOD_DRAFT + "\n\nThe takeaway: trust beats coverage.", "closing takeaway"),
    ("too short", "A short note about retrieval that says very little at all.", "too thin"),
])
def test_deterministic_rules_override_an_approving_model(label, text, expected_in_feedback):
    """Each of these rules exists because a live draft violated it."""
    with patch_llm("qa_judge", approving_verdict()):
        result = qa_judge_node(qa_state(text))

    verdict = result["qa_verdict"]
    assert verdict.verdict == "revise", label
    assert expected_in_feedback in verdict.feedback, f"{label}: {verdict.feedback}"


def test_failed_model_checks_are_all_reported_together():
    """
    Reporting one fault at a time made the writer fix it and reintroduce another,
    burning every revision without converging.
    """
    failing = QAVerdict(
        voice_consistent=True, factually_grounded=False, non_repetitive=True,
        plain_language_clear=False, single_idea=False, verdict="revise",
        feedback="Several problems.",
    )
    with patch_llm("qa_judge", failing):
        result = qa_judge_node(qa_state(GOOD_DRAFT))

    feedback = result["qa_verdict"].feedback
    assert "specialist language" in feedback
    assert "more than one idea" in feedback
    assert "does not support" in feedback
