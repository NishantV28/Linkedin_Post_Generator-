from typing import TypedDict, List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field

from backend.app.agent.persona.schema import PersonaConfig
from backend.app.agent.tools.schema import TopicCandidate


class WriterContext(BaseModel):
    """
    The editorial decision, handed from judge to writer.

    This is the boundary between "what deserves to be said" and "how to explain it".
    The writer receives a settled angle and verified facts, and may not go looking for
    a different story - which is what produced posts that drifted off their source.
    """
    obvious_assumption: str = Field(..., description="What a casual reader would initially assume")
    interesting_turn: str = Field(..., description="What is actually more interesting")
    core_claim: str = Field(..., description="The single claim the post should explain")
    mechanism: str = Field(..., description="The concrete mechanism, finding, or technical detail")
    evidence: List[str] = Field(default_factory=list, description="Verified supporting facts")
    limitations: List[str] = Field(default_factory=list, description="Important limitations, if present")
    persona_relevance: str = Field(..., description="Why this fits the persona's interests")
    why_now: Optional[str] = Field(None, description="Evidence-based reason this is timely, or null")
    sources: List[str] = Field(default_factory=list, description="Source URLs for this candidate only")


class EditorialScores(BaseModel):
    """Judge scores, 0-5. Enforced in code, not trusted from the decision field."""
    evidence_strength: int = Field(..., ge=0, le=5)
    editorial_value: int = Field(..., ge=0, le=5)
    persona_fit: int = Field(..., ge=0, le=5)
    timeliness: int = Field(..., ge=0, le=5)
    explainability: int = Field(..., ge=0, le=5)


DISQUALIFIERS = Literal[
    "opinion_no_evidence",
    "pure_announcement",
    "listicle",
    "off_topic",
    "no_accessible_source",
    "already_covered",
    "duplicate_theme",
    "low_editorial_value",
    "weak_persona_fit",
    "insufficient_detail",
    "unverifiable_claim",
]


class JudgeVerdict(BaseModel):
    """Structured output of the editorial judge."""
    source_type: Literal["paper", "repo", "release", "blog_post", "article", "other"]
    disqualifier: Optional[DISQUALIFIERS] = Field(
        None, description="The single reason this fails, or null if it passes"
    )
    summary: str = Field(..., description="Factual description of what this item is and does")
    editorial_angle: str = Field(..., description="The single specific idea that makes this worth explaining")
    editorial_value: Literal[
        "mechanism", "surprising_finding", "meaningful_change",
        "useful_technique", "important_failure", "tradeoff", "none"
    ]
    scores: EditorialScores
    credibility: Literal["low", "medium", "high"]
    trend_signal: Optional[str] = Field(None, description="Evidence this is timely now, or null")
    decision: Literal["publish", "reject"]
    reasoning: str = Field(..., description="Why the candidate passed or failed the editorial standard")
    writer_context: Optional[WriterContext] = Field(
        None, description="Editorial handoff. Required when decision is 'publish'."
    )


class DraftPost(BaseModel):
    """Structured output of the writer."""
    text: str = Field(..., description="The finished post")
    rationale_selected: str = Field(..., description="Why this topic was selected, per the judge's decision")
    rationale_why_now: str = Field(..., description="Why this is relevant now, using only the judge's evidence")
    sources: List[str] = Field(default_factory=list, description="Source URLs, carried from the judge")


class QAVerdict(BaseModel):
    """Structured output of the QA judge."""
    voice_consistent: bool = Field(..., description="Matches tone and rhythm, avoids forbidden words")
    factually_grounded: bool = Field(..., description="Every claim traceable to the judge's verified context")
    non_repetitive: bool = Field(..., description="Distinct from recent posts in story, angle and theme")
    plain_language_clear: bool = Field(
        ...,
        description=(
            "True only if a reader with no background in this specific subfield could follow "
            "what changed. False if any specialist term is used without being rewritten in "
            "plain language."
        )
    )
    single_idea: bool = Field(
        ...,
        description="True if the post explains exactly one central idea rather than several"
    )
    verdict: Literal["pass", "revise"]
    feedback: str = Field(..., description="Specific, actionable revision guidance")


class AgentState(TypedDict):
    """LangGraph state for a single cycle."""
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
