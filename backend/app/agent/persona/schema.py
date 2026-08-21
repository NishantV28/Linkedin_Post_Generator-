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

    # Adjectives describe a voice; examples demonstrate one, and models match the
    # second far more reliably than the first. "Precise, unhurried, sceptical" leaves
    # enormous latitude - three real posts do not.
    #
    # Hand-written for a preset, or supplied by the user at setup. User samples are
    # the truest description of how that person actually writes, so they replace the
    # preset's rather than being appended to them.
    voice_samples: List[str] = Field(
        default_factory=list,
        description="Example posts demonstrating this voice. Style anchors, never templates."
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


class DiscoverySources(BaseModel):
    """
    Where this persona looks for material.

    Previously every agent searched Hacker News, arXiv, GitHub and the web regardless
    of its domain - reasonable for an AI-research persona and a poor fit for any
    other, which quietly limited the persona system to one subject area. Making the
    sources part of the identity means a persona in a different field can be given
    somewhere sensible to read.
    """
    hacker_news: bool = Field(True, description="Hacker News front page and Show HN")
    arxiv: bool = Field(True, description="arXiv recent submissions")
    github: bool = Field(True, description="GitHub search by topic")
    web_search: bool = Field(True, description="Tavily, or DuckDuckGo when no key is set")
    rss_feeds: List[str] = Field(
        default_factory=list,
        description="Feed URLs specific to this persona's field"
    )
    search_terms: List[str] = Field(
        default_factory=list,
        description="Extra queries for web and GitHub search. Defaults to stable_interests when empty."
    )


# The shapes a post can take. Every post used to be the same one - an explanation of
# a single source - which reads as monotonous over a run of a dozen. Each of these
# still explains one idea; they differ in how they open and what they ask of a reader.
POST_TYPES = ("explainer", "observation", "question", "lesson", "contrarian")


class PostTypeMix(BaseModel):
    """
    How often each post type should appear, as relative weights.

    Weights rather than a fixed rotation, so the mix stays natural rather than
    cycling predictably, and so a persona can lean heavily towards one shape without
    excluding the others.
    """
    explainer: int = Field(6, ge=0, description="Explains one mechanism from a source. The default shape.")
    observation: int = Field(2, ge=0, description="A pattern noticed across several sources")
    question: int = Field(1, ge=0, description="Opens a genuine question the evidence raises")
    lesson: int = Field(1, ge=0, description="What this changes for someone building things")
    contrarian: int = Field(1, ge=0, description="Where the obvious reading of the evidence is wrong")


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
    discovery_sources: DiscoverySources = Field(default_factory=DiscoverySources)
    post_type_mix: PostTypeMix = Field(default_factory=PostTypeMix)
