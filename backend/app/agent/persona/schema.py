from pydantic import BaseModel, Field
from typing import List, Optional


class MemoryWindows(BaseModel):
    """
    How far back the agent looks before calling something a repeat.

    A new URL is not a new editorial idea, so repetition is judged at three widths:
    the same story, the same angle applied to a different story, and the same theme.
    """
    recent_posts_for_context: int = Field(5, description="Recent posts passed to the judge and writer")
    duplicate_window_hours: int = Field(24, description="Same underlying story")
    same_angle_window_hours: int = Field(48, description="Same editorial angle, different source")
    same_theme_window_hours: int = Field(72, description="Same broad theme")


class EditorialThresholds(BaseModel):
    """
    Minimum scores required to publish, enforced in code.

    The judge scores 0-5 per dimension. Enforcing here rather than trusting the model
    stops a verdict that says "publish" while its own scores say otherwise.
    """
    min_evidence_strength: int = Field(3, ge=0, le=5)
    min_editorial_value: int = Field(3, ge=0, le=5)
    min_persona_fit: int = Field(3, ge=0, le=5)
    min_explainability: int = Field(3, ge=0, le=5)


class PostingCadenceHours(BaseModel):
    min_hours: float = Field(2.0, ge=0.1)
    max_hours: float = Field(5.0, ge=0.5)


class VoiceGuidelines(BaseModel):
    """How the persona sounds. Stable across every post."""
    tone: str = Field(..., description="Emotional and intellectual register")
    sentence_rhythm: str = Field(..., description="Sentence structure and pacing")
    forbidden_phrases: List[str] = Field(default_factory=list, description="Hype and filler this persona never uses")
    core_question: Optional[str] = Field(None, description="The editorial north star every post answers")

    worked_example: Optional[str] = Field(
        None,
        description="An exemplar post demonstrating shape and voice. A style anchor, never a template."
    )

    # Length, enforced programmatically.
    min_post_words: int = Field(100, description="Minimum post length in words")
    max_post_words: int = Field(180, description="Hard maximum, never exceeded")

    # Deterministic style rules, checked in code rather than left to the model -
    # every one of these has been violated in a live run.
    max_sentence_words: int = Field(25, description="A sentence doing two jobs should be split")
    forbid_em_dashes: bool = Field(True, description="Em-dashes read as machine-written here")
    forbid_parenthetical_definitions: bool = Field(
        True,
        description="Jargon must be rewritten in plain language, not glossed in brackets"
    )
    forbid_closing_takeaway: bool = Field(
        True,
        description="The post ends when the mechanism is explained; no appended punchline"
    )


class PersonaConfig(BaseModel):
    """
    The persona's stable identity.

    Deliberately separate from per-cycle editorial decisions: the identity holds still
    while topics change. Nothing here is regenerated per cycle.
    """
    name: str = Field(..., description="Public identity")
    domain: str = Field(..., description="Main subject area")
    bio: str = Field(..., description="Who the persona is and what it does")

    voice_guidelines: VoiceGuidelines
    stable_interests: List[str] = Field(default_factory=list, description="Long-term topics the persona covers")
    editorial_thresholds: EditorialThresholds = Field(default_factory=EditorialThresholds)
    memory: MemoryWindows = Field(default_factory=MemoryWindows)
    posting_cadence_hours: PostingCadenceHours = Field(default_factory=PostingCadenceHours)
