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

    with patch("backend.app.agent.nodes.editorial_judge.get_llm") as mock_get_llm:
        mock_llm = MagicMock()
        mock_structured = MagicMock()
        mock_structured.invoke.return_value = mock_verdict
        mock_llm.with_structured_output.return_value = mock_structured
        mock_get_llm.return_value = mock_llm

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

    with patch("backend.app.agent.nodes.writer.get_llm") as mock_get_llm:
        mock_llm = MagicMock()
        mock_structured = MagicMock()
        mock_structured.invoke.return_value = mock_draft
        mock_llm.with_structured_output.return_value = mock_structured
        mock_get_llm.return_value = mock_llm

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
        "draft": DraftPost(
            text="High signal technical post about model architectures.",
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

    with patch("backend.app.agent.nodes.qa_judge.get_llm") as mock_get_llm:
        mock_llm = MagicMock()
        mock_structured = MagicMock()
        mock_structured.invoke.return_value = mock_qa
        mock_llm.with_structured_output.return_value = mock_structured
        mock_get_llm.return_value = mock_llm

        res_state = qa_judge_node(state)
        assert res_state["qa_verdict"] is not None
        assert res_state["qa_verdict"].verdict == "pass"
