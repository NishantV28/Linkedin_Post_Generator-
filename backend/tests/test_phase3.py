import pytest
import os
import sys
from unittest.mock import MagicMock, patch

from backend.app.agent.persona.presets import DISTILL_PRESET
from backend.app.agent.tools.schema import TopicCandidate
from backend.app.agent.state import JudgeVerdict, DraftPost, QAVerdict
from backend.app.agent.nodes.editorial_judge import editorial_judge_node
from backend.app.agent.nodes.writer import writer_node
from backend.app.agent.nodes.qa_judge import qa_judge_node

def test_editorial_judge_node_pass():
    cand = TopicCandidate(
        id="cand_1",
        title="Scalable MatMul-free Language Modeling",
        summary="Novel research removing matrix multiplication from LLM architectures.",
        url="https://arxiv.org/abs/2406.02528",
        source="arxiv",
        published_at="2026-08-08T10:00:00Z"
    )

    state = {
        "persona": DISTILL_PRESET,
        "agent_id": "test_agent_p3",
        "current_candidate": cand,
        "candidates": [cand],
        "candidate_idx": 0
    }

    mock_verdict = JudgeVerdict(
        relevance=9,
        novelty=9,
        credibility=9,
        timeliness=8,
        decision="pass",
        reasoning="High quality paper aligning with persona domain."
    )

    with patch("backend.app.agent.nodes.editorial_judge.get_structured_llm") as mock_get_structured:
        mock_structured = MagicMock()
        mock_structured.invoke.return_value = mock_verdict
        mock_get_structured.return_value = mock_structured

        res_state = editorial_judge_node(state)
        assert res_state["judge_verdict"] is not None
        assert res_state["judge_verdict"].decision == "pass"
        assert res_state["judge_verdict"].relevance == 9

def test_writer_node_generation():
    cand = TopicCandidate(
        id="cand_2",
        title="Self-Critique Reasoning Models",
        summary="A new self-critique strategy for step verification in LLMs.",
        url="https://arxiv.org/abs/2401.00000",
        source="arxiv",
        published_at="2026-08-08T10:00:00Z"
    )

    state = {
        "persona": DISTILL_PRESET,
        "agent_id": "test_agent_p3",
        "current_candidate": cand,
        "judge_verdict": JudgeVerdict(
            relevance=9, novelty=9, credibility=9, timeliness=9,
            decision="pass", reasoning="Great paper."
        )
    }

    mock_draft = DraftPost(
        text="Self-critique reasoning represents a fundamental shift in LLM alignment. Rather than relying purely on benchmark gaming...",
        rationale_selected="Selected for novel reasoning strategy.",
        rationale_why_now="Timely research published today."
    )

    with patch("backend.app.agent.nodes.writer.get_structured_llm") as mock_get_structured:
        mock_structured = MagicMock()
        mock_structured.invoke.return_value = mock_draft
        mock_get_structured.return_value = mock_structured

        res_state = writer_node(state)
        assert res_state["draft"] is not None
        assert "Self-critique reasoning" in res_state["draft"].text
        assert res_state["draft"].rationale_selected != ""

def test_qa_judge_node_eval():
    cand = TopicCandidate(
        id="cand_3",
        title="Sample Paper",
        summary="Sample summary",
        url="https://arxiv.org/abs/2401.00000",
        source="arxiv",
        published_at="2026-08-08T10:00:00Z"
    )

    state = {
        "persona": DISTILL_PRESET,
        "agent_id": "test_agent_p3",
        "current_candidate": cand,
        # Must satisfy the persona's structural rules, and must not reuse wording from
        # the worked example, or the programmatic voice checks in qa_judge_node
        # override the mocked verdict.
        "draft": DraftPost(
            text=(
                "The release notes lead with a 12% latency drop, which is the least "
                "useful number here.\n\n"
                "What changed is where the KV cache lives. Instead of holding every layer "
                "in device memory, the runtime keeps a working set and streams the rest "
                "from host RAM on demand. Throughput barely moves, but the memory ceiling "
                "stops being a hard wall.\n\n"
                "That shifts who can run this. A 70B model on a single 24GB card was a "
                "packaging problem before, not a compute one. If the streaming path holds "
                "up under batch load, a lot of deployments that were priced out of "
                "multi-GPU boxes become viable on one.\n\n"
                "The unanswered part is contention. Every benchmark in the notes is "
                "single-request. Nobody has shown what happens when eight sessions fight "
                "over the same host bandwidth.\n\n"
                "Memory ceilings are a scheduling problem now, not a hardware one."
            ),
            rationale_selected="Relevant",
            rationale_why_now="Now"
        )
    }

    mock_qa = QAVerdict(
        voice_consistent=True,
        factually_grounded=True,
        non_repetitive=True,
        verdict="pass",
        feedback="Looks good."
    )

    with patch("backend.app.agent.nodes.qa_judge.get_structured_llm") as mock_get_structured:
        mock_structured = MagicMock()
        mock_structured.invoke.return_value = mock_qa
        mock_get_structured.return_value = mock_structured

        res_state = qa_judge_node(state)
        assert res_state["qa_verdict"] is not None
        assert res_state["qa_verdict"].verdict == "pass"


@pytest.mark.parametrize("scores,expected", [
    (dict(relevance=9, novelty=8, credibility=9, timeliness=8), "pass"),
    (dict(relevance=9, novelty=8, credibility=9, timeliness=3), "reject"),   # stale
    (dict(relevance=9, novelty=8, credibility=5, timeliness=8), "reject"),   # weak source
    (dict(relevance=4, novelty=8, credibility=9, timeliness=8), "reject"),   # off-topic
])
def test_editorial_judge_enforces_thresholds(scores, expected):
    """Persona thresholds are enforced in code; a model 'pass' below the bar is overruled."""
    cand = TopicCandidate(
        id="cand_t", title="Some paper", summary="s",
        url="https://arxiv.org/abs/2309.10305", source="arxiv",
        published_at="2023-09-19T00:00:00Z"
    )
    state = {"persona": DISTILL_PRESET, "agent_id": "", "current_candidate": cand}

    model_verdict = JudgeVerdict(**scores, decision="pass", reasoning="Model reasoning.")

    with patch("backend.app.agent.nodes.editorial_judge.get_structured_llm") as mock_get_structured:
        mock_structured = MagicMock()
        mock_structured.invoke.return_value = model_verdict
        mock_get_structured.return_value = mock_structured

        res_state = editorial_judge_node(state)

    assert res_state["judge_verdict"].decision == expected


def test_qa_judge_enforces_persona_structure():
    """A draft the LLM approves is still rejected if it breaks the persona's structure."""
    cand = TopicCandidate(
        id="cand_4",
        title="Sample Paper",
        summary="Sample summary",
        url="https://arxiv.org/abs/2401.00001",
        source="arxiv",
        published_at="2026-08-08T10:00:00Z"
    )

    # Flat summary with no standalone closing line - the failure mode observed in
    # live runs before the persona structure was enforced.
    state = {
        "persona": DISTILL_PRESET,
        "agent_id": "test_agent_p3",
        "current_candidate": cand,
        "draft": DraftPost(
            text=(
                "Just saw the Baichuan 2 paper. It is an open large-scale language model. "
                "It adds another openly available model to the ecosystem, which helps keep "
                "research reproducible and accessible."
            ),
            rationale_selected="Relevant",
            rationale_why_now="Now"
        )
    }

    approving_verdict = QAVerdict(
        voice_consistent=True,
        factually_grounded=True,
        non_repetitive=True,
        verdict="pass",
        feedback="Looks good."
    )

    with patch("backend.app.agent.nodes.qa_judge.get_structured_llm") as mock_get_structured:
        mock_structured = MagicMock()
        mock_structured.invoke.return_value = approving_verdict
        mock_get_structured.return_value = mock_structured

        res_state = qa_judge_node(state)

    verdict = res_state["qa_verdict"]
    assert verdict.verdict == "revise", "structure violation must override the LLM verdict"
    assert verdict.voice_consistent is False
    assert "standalone closing line" in verdict.feedback


def test_qa_judge_rejects_wording_copied_from_the_style_example():
    """The worked example demonstrates shape; reusing its sentences is not the voice."""
    cand = TopicCandidate(
        id="cand_5", title="Sample", summary="s",
        url="https://news.ycombinator.com/item?id=1", source="hn",
        published_at="2026-08-08T10:00:00Z"
    )

    # Observed in a live run: three of four sentences lifted from the example, which
    # also made the post factually wrong - the source was a forum thread, not a paper,
    # and no benchmark score was involved.
    state = {
        "persona": DISTILL_PRESET,
        "agent_id": "test_agent_p3",
        "current_candidate": cand,
        "draft": DraftPost(
            text=(
                "A new decoding paper landed this week and the framing is familiar.\n\n"
                "The mechanism: the model scores its own intermediate steps and can "
                "abandon a chain halfway. The authors report this on three benchmarks "
                "with consistent gains, and the implementation is a few hundred lines on "
                "top of a standard sampler.\n\n"
                "What that buys you is fewer wasted tokens per solved problem, which "
                "matters more for cost than for accuracy. The reported numbers are modest "
                "but the direction is clear enough that it is worth watching whether it "
                "survives contact with the larger models people actually deploy.\n\n"
                "The open question is whether the scorer stays reliable once the "
                "generator is stronger than it is, which nobody has demonstrated yet.\n\n"
                "Cheaper supervision beats a bigger model."
            ),
            rationale_selected="Relevant",
            rationale_why_now="Now"
        )
    }

    approving_verdict = QAVerdict(
        voice_consistent=True, factually_grounded=True, non_repetitive=True,
        verdict="pass", feedback="Looks good."
    )

    with patch("backend.app.agent.nodes.qa_judge.get_structured_llm") as mock_get_structured:
        mock_structured = MagicMock()
        mock_structured.invoke.return_value = approving_verdict
        mock_get_structured.return_value = mock_structured

        res_state = qa_judge_node(state)

    verdict = res_state["qa_verdict"]
    assert verdict.verdict == "revise"
    assert "style example" in verdict.feedback
