from typing import TypedDict, List, Optional, Dict, Any
from pydantic import BaseModel, Field
from backend.app.agent.persona.schema import PersonaConfig
from backend.app.agent.tools.schema import TopicCandidate

class JudgeVerdict(BaseModel):
    """Structured output for Editorial Judge LLM node."""
    relevance: int = Field(..., ge=1, le=10, description="Relevance score to persona stable interests (1-10)")
    novelty: int = Field(..., ge=1, le=10, description="Novelty and insight depth score (1-10)")
    credibility: int = Field(..., ge=1, le=10, description="Source credibility score (1-10)")
    timeliness: int = Field(..., ge=1, le=10, description="Timeliness / why now score (1-10)")
    decision: str = Field(..., description="'pass' if candidate clears all persona thresholds, else 'reject'")
    reasoning: str = Field(..., description="Detailed explanation of scoring breakdown and decision rationale")

class DraftPost(BaseModel):
    """Structured output for Post Writer LLM node."""
    text: str = Field(..., description="The complete, persona-voiced LinkedIn post text")
    rationale_selected: str = Field(..., description="Clear explanation of why this topic was selected")
    rationale_why_now: str = Field(..., description="Why this topic is important right now")

class QAVerdict(BaseModel):
    """Structured output for QA Judge LLM node."""
    voice_consistent: bool = Field(..., description="True if draft matches tone, rhythm, and avoids forbidden words")
    factually_grounded: bool = Field(..., description="True if claims are grounded in source candidate summary")
    non_repetitive: bool = Field(..., description="True if draft avoids repeating recent memory posts")
    plain_language_clear: bool = Field(
        ...,
        description=(
            "True only if a smart reader with no background in this specific subfield could "
            "follow what changed. False if any specialist term is used without being translated "
            "the moment it appears, or if the closing line only makes sense to a specialist."
        )
    )
    verdict: str = Field(..., description="'pass' to publish, or 'revise' to request a writer retry")
    feedback: str = Field(..., description="Specific feedback to guide revision if verdict is 'revise'")

class AgentState(TypedDict):
    """LangGraph state schema for single cycle execution."""
    persona: PersonaConfig
    agent_id: str
    candidates: List[TopicCandidate]
    candidate_idx: int
    current_candidate: Optional[TopicCandidate]
    judge_verdict: Optional[JudgeVerdict]
    draft: Optional[DraftPost]
    qa_verdict: Optional[QAVerdict]
    retry_count: int
    # Set when a node fails for infrastructure reasons (rate limit, API outage).
    # Distinct from an editorial decision, and aborts the cycle rather than being
    # recorded as if the persona had judged the topic.
    node_error: Optional[str]
    published_post: Optional[Dict[str, Any]]
    rejected_count: int
    # Candidates passed over during this cycle, cited by the published post's rationale.
    rejected_this_cycle: List[Dict[str, str]]
    # "topic" for an ordinary cycle, "reflection" when the agent writes about a
    # pattern in its own recent coverage instead of a new source.
    mode: str
    coverage_trend: Optional[Dict[str, Any]]
    cycle_outcome: str
