"""
End-to-end tests for the compiled LangGraph workflow.

Every other test file exercises nodes in isolation. That leaves the wiring untested,
and the wiring is where the expensive failures live: a node can be perfectly correct
while the state it writes never reaches the node that reads it.

The bug these tests were written for is exactly that shape. `advance_candidate` and
`editorial_judge_node` were reading and writing `evaluated_candidates` and
`forced_publish` while neither key was declared on `AgentState`. LangGraph builds one
channel per declared key and silently discards writes to anything else, so the
fallback that publishes the best near-miss could never fire - and every node involved
passed its own unit tests.

These run `graph.invoke()` with the LLM and the database stubbed, so they are fast,
deterministic, and need no API key.
"""

import pytest
from unittest.mock import MagicMock, patch

from backend.app.agent.persona.presets import DISTILL_PRESET
from backend.app.agent.tools.schema import TopicCandidate
from backend.app.agent.state import (
    AgentState,
    JudgeVerdict,
    EditorialScores,
    WriterContext,
    DraftPost,
    QAVerdict,
)


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

def candidate(idx: int) -> TopicCandidate:
    return TopicCandidate(
        id=f"c{idx}",
        title=f"Retrieval reliability weighting, part {idx}",
        summary="A benchmark presenting each question in four matched forms.",
        url=f"https://arxiv.org/abs/2608.0{idx}",
        source="arxiv",
        published_at="2026-08-08T10:00:00Z",
    )


def writer_context() -> WriterContext:
    return WriterContext(
        obvious_assumption="More retrieved context makes models more reliable.",
        interesting_turn="Which passages the model trusts matters more than how many it sees.",
        core_claim="Weighting passages by reliability recovers accuracy lost to misleading context.",
        mechanism="Each passage is scored for agreement with the rest of the retrieved set.",
        evidence=["Accuracy recovered from 61% to 78% on the misleading split."],
        limitations=["Tested only on English-language QA."],
        persona_relevance="Concrete mechanism inside a retrieval system.",
        why_now="Published this week.",
        sources=["https://arxiv.org/abs/2608.01"],
    )


def passing_verdict() -> JudgeVerdict:
    return JudgeVerdict(
        source_type="paper",
        disqualifier=None,
        summary="A retrieval weighting benchmark.",
        editorial_angle="Trust, not volume, is the bottleneck.",
        editorial_value="mechanism",
        scores=EditorialScores(
            evidence_strength=5, editorial_value=5, persona_fit=5,
            timeliness=4, explainability=5,
        ),
        credibility="high",
        trend_signal="Published this week.",
        decision="publish",
        reasoning="Concrete mechanism with verifiable evidence.",
        writer_context=writer_context(),
    )


def rejecting_verdict(score: int = 2) -> JudgeVerdict:
    """A rejection whose scores still differ, so 'best near-miss' is meaningful."""
    return JudgeVerdict(
        source_type="paper",
        disqualifier="low_editorial_value",
        summary="An incremental result.",
        editorial_angle="Not much of an angle.",
        editorial_value="mechanism",
        scores=EditorialScores(
            evidence_strength=score, editorial_value=score, persona_fit=score,
            timeliness=score, explainability=score,
        ),
        credibility="high",
        trend_signal=None,
        decision="reject",
        reasoning="Below the persona's editorial bar.",
        writer_context=None,
    )


def draft() -> DraftPost:
    return DraftPost(
        text=(
            "Retrieval systems are usually tuned for recall. This benchmark shows the "
            "binding constraint is elsewhere: when a misleading passage enters the set, "
            "the model treats it as equally trustworthy. Weighting each passage by its "
            "agreement with the rest recovered accuracy from 61% to 78%. "
            "#AI #Retrieval #MachineLearning"
        ),
        rationale_selected="Fits the persona's interest in retrieval mechanisms.",
        rationale_why_now="Published this week.",
        sources=["https://arxiv.org/abs/2608.01"],
    )


def failing_qa() -> QAVerdict:
    """QA that always asks for another revision."""
    return QAVerdict(
        voice_consistent=True,
        factually_grounded=False,
        non_repetitive=True,
        plain_language_clear=True,
        single_idea=True,
        verdict="revise",
        feedback="Not grounded in the source.",
    )


def passing_qa() -> QAVerdict:
    return QAVerdict(
        voice_consistent=True,
        factually_grounded=True,
        non_repetitive=True,
        plain_language_clear=True,
        single_idea=True,
        verdict="pass",
        feedback="Reads cleanly and stays on one idea.",
    )


def base_state(candidates, mode="topic") -> AgentState:
    return {
        "persona": DISTILL_PRESET,
        "agent_id": "agent-under-test",
        "candidates": candidates,
        "candidate_idx": 0,
        "current_candidate": None,
        "judge_verdict": None,
        "draft": None,
        "qa_verdict": None,
        "retry_count": 0,
        "node_error": None,
        "published_post": None,
        "rejected_count": 0,
        "rejected_this_cycle": [],
        "mode": mode,
        "coverage_trend": None,
        "cycle_outcome": "in_progress",
        "evaluated_candidates": [],
        "forced_publish": False,
    }


@pytest.fixture
def graph():
    """A freshly compiled graph, so state-schema changes are picked up per test."""
    from backend.app.agent.graph import build_agent_graph
    return build_agent_graph()


@pytest.fixture
def stub_persistence():
    """Keep the graph off SQLite and ChromaDB; publish returns a fake record."""
    saved = MagicMock()
    saved.id = "post-1"
    saved.text = draft().text
    saved.rationale = "Explains one mechanism with a measured result."
    saved.topic_title = "Retrieval reliability weighting"
    saved.created_at = "2026-08-08T10:00:00Z"

    with patch("backend.app.agent.nodes.publish.SessionLocal"), \
         patch("backend.app.agent.nodes.publish.MemoryRepository.save_post", return_value=saved) as save_post, \
         patch("backend.app.agent.nodes.rejection_logger.SessionLocal"), \
         patch("backend.app.agent.nodes.rejection_logger.MemoryRepository.save_rejection"), \
         patch("backend.app.agent.nodes.editorial_judge.SessionLocal"), \
         patch("backend.app.agent.nodes.editorial_judge.MemoryRepository.get_recent_posts", return_value=[]), \
         patch("backend.app.agent.nodes.qa_judge.SessionLocal"), \
         patch("backend.app.agent.nodes.qa_judge.MemoryRepository.get_recent_posts", return_value=[]), \
         patch("backend.app.agent.nodes.writer.SessionLocal"), \
         patch("backend.app.agent.nodes.writer.HybridRetriever.get_relevant_context", return_value=[]):
        # The memory lookups are stubbed empty rather than left live: they would open a
        # real SQLite file and load the embedding model, which is slow, and the few-shot
        # context they return has no bearing on the wiring these tests are about.
        yield save_post


# --------------------------------------------------------------------------- #
# The state schema itself
# --------------------------------------------------------------------------- #

def test_every_key_the_graph_writes_is_declared_on_agent_state():
    """
    Guards the class of bug described at the top of this file.

    A key written by a node but missing from AgentState is dropped without warning, so
    the failure shows up as unexplained behaviour rather than an error. Asserting the
    schema directly makes it a test failure instead.
    """
    from backend.app.agent.state import AgentState

    declared = set(AgentState.__annotations__)
    required = {
        "persona", "agent_id", "candidates", "candidate_idx", "current_candidate",
        "judge_verdict", "draft", "qa_verdict", "retry_count", "node_error",
        "published_post", "rejected_count", "rejected_this_cycle", "mode",
        "coverage_trend", "cycle_outcome",
        # Written by advance_candidate and editorial_judge_node.
        "evaluated_candidates", "forced_publish",
    }

    missing = required - declared
    assert not missing, (
        f"AgentState is missing {sorted(missing)}. LangGraph discards writes to "
        f"undeclared keys, so any node writing these is silently a no-op."
    )


# --------------------------------------------------------------------------- #
# Whole-cycle behaviour
# --------------------------------------------------------------------------- #

def test_cycle_publishes_when_a_candidate_passes(graph, stub_persistence):
    with patch("backend.app.agent.nodes.editorial_judge.get_structured_llm") as judge_llm, \
         patch("backend.app.agent.nodes.writer.get_structured_llm") as writer_llm, \
         patch("backend.app.agent.nodes.qa_judge.get_structured_llm") as qa_llm:

        judge_llm.return_value.invoke.return_value = passing_verdict()
        writer_llm.return_value.invoke.return_value = draft()
        qa_llm.return_value.invoke.return_value = passing_qa()

        final = graph.invoke(base_state([candidate(1)]))

    assert final["cycle_outcome"] == "published"
    assert final["published_post"] is not None
    stub_persistence.assert_called_once()


def test_evaluated_candidates_actually_reaches_the_next_node(graph, stub_persistence):
    """
    The regression test proper.

    Before the fix this list read back empty no matter how many candidates the judge
    scored, because the key was not a declared channel. Asserting on the final state
    catches that without needing to know how LangGraph stores it.
    """
    with patch("backend.app.agent.nodes.editorial_judge.get_structured_llm") as judge_llm, \
         patch("backend.app.agent.nodes.writer.get_structured_llm") as writer_llm, \
         patch("backend.app.agent.nodes.qa_judge.get_structured_llm") as qa_llm:

        judge_llm.return_value.invoke.side_effect = [
            rejecting_verdict(2), rejecting_verdict(4), rejecting_verdict(1),
        ]
        writer_llm.return_value.invoke.return_value = draft()
        qa_llm.return_value.invoke.return_value = passing_qa()

        final = graph.invoke(base_state([candidate(1), candidate(2), candidate(3)]))

    assert len(final["evaluated_candidates"]) == 3, (
        "The judge scored three candidates; the list the router reads should hold all "
        "three. An empty list here means state writes are being dropped."
    )


def test_all_candidates_rejected_still_publishes_the_best_near_miss(graph, stub_persistence):
    """
    The behaviour the missing keys disabled: rather than ending a cycle empty-handed,
    the strongest rejected candidate is written up instead.
    """
    with patch("backend.app.agent.nodes.editorial_judge.get_structured_llm") as judge_llm, \
         patch("backend.app.agent.nodes.writer.get_structured_llm") as writer_llm, \
         patch("backend.app.agent.nodes.qa_judge.get_structured_llm") as qa_llm:

        # The middle candidate scores highest, so picking it proves the sort ran
        # rather than the code simply taking the first or last entry.
        judge_llm.return_value.invoke.side_effect = [
            rejecting_verdict(2), rejecting_verdict(4), rejecting_verdict(1),
        ]
        writer_llm.return_value.invoke.return_value = draft()
        qa_llm.return_value.invoke.return_value = passing_qa()

        final = graph.invoke(base_state([candidate(1), candidate(2), candidate(3)]))

    assert final["forced_publish"] is True
    assert final["cycle_outcome"] == "published"
    assert final["current_candidate"].id == "c2", (
        "The highest-scoring rejected candidate should be the one force-published."
    )


def test_cycle_with_no_candidates_ends_cleanly(graph, stub_persistence):
    final = graph.invoke(base_state([]))

    assert final["cycle_outcome"] == "no_candidates"
    assert final["published_post"] is None
    stub_persistence.assert_not_called()


def test_infrastructure_failure_aborts_rather_than_recording_a_rejection(graph, stub_persistence):
    """
    A provider outage is not an editorial decision. It must abort the cycle, not leave
    a rejected_topics row implying the persona judged and declined the topic.
    """
    with patch("backend.app.agent.nodes.editorial_judge.get_structured_llm") as judge_llm:
        judge_llm.return_value.invoke.side_effect = RuntimeError("rate limit")

        final = graph.invoke(base_state([candidate(1)]))

    assert final["node_error"] is not None
    assert final["cycle_outcome"].startswith("aborted")
    assert final["published_post"] is None
    stub_persistence.assert_not_called()


def test_qa_revision_loop_is_bounded(graph, stub_persistence):
    """
    QA that never passes must stop asking for rewrites rather than loop forever.
    Without the retry_count cap this is an unbounded spend of writer and QA calls on
    a single candidate.
    """
    with patch("backend.app.agent.nodes.editorial_judge.get_structured_llm") as judge_llm, \
         patch("backend.app.agent.nodes.writer.get_structured_llm") as writer_llm, \
         patch("backend.app.agent.nodes.qa_judge.get_structured_llm") as qa_llm:

        judge_llm.return_value.invoke.return_value = passing_verdict()
        writer_llm.return_value.invoke.return_value = draft()
        qa_llm.return_value.invoke.return_value = failing_qa()

        final = graph.invoke(base_state([candidate(1)]), {"recursion_limit": 60})

    from backend.app.agent.graph import MAX_REVISIONS
    assert final["retry_count"] <= MAX_REVISIONS
    # It terminated rather than hitting the recursion limit.
    assert final["cycle_outcome"] != "in_progress"


def test_a_forced_publish_skips_qa_and_lands_as_a_pending_draft(graph, stub_persistence):
    """
    Documents a deliberate but sharp-edged behaviour, so it cannot change unnoticed.

    When a cycle would otherwise end empty-handed, the strongest candidate is pushed
    through - and `route_after_qa` lets it past the QA gate on the way. So a post that
    QA rejected three times still gets written to the database.

    What keeps that acceptable is the review queue: it is saved as `pending`, so it
    reaches nobody until a human approves it. If the approval step is ever removed,
    this test should start failing loudly rather than quietly publishing unchecked
    text under someone's name.
    """
    with patch("backend.app.agent.nodes.editorial_judge.get_structured_llm") as judge_llm, \
         patch("backend.app.agent.nodes.writer.get_structured_llm") as writer_llm, \
         patch("backend.app.agent.nodes.qa_judge.get_structured_llm") as qa_llm:

        judge_llm.return_value.invoke.return_value = passing_verdict()
        writer_llm.return_value.invoke.return_value = draft()
        qa_llm.return_value.invoke.return_value = failing_qa()

        final = graph.invoke(base_state([candidate(1)]), {"recursion_limit": 60})

    assert final["forced_publish"] is True
    assert final["published_post"] is not None

    # save_post was called without an explicit status, so the model default applies.
    _, kwargs = stub_persistence.call_args
    assert "status" not in kwargs or kwargs["status"] == "pending", (
        "A post that failed QA must not be saved as approved."
    )
