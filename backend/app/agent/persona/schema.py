from pydantic import BaseModel, Field
from typing import List, Optional

class VoiceGuidelines(BaseModel):
    tone: str = Field(..., description="Overall tone of the persona")
    sentence_rhythm: str = Field(..., description="Sentence length and cadence rules")
    forbidden_phrases: List[str] = Field(default_factory=list, description="Phrases/hype words forbidden for this persona")
    signature_tell: Optional[str] = Field(None, description="Signature writing habit or closing structure")
    core_question: Optional[str] = Field(
        None,
        description="The single question every post must answer. If it cannot be answered clearly, the persona does not publish."
    )
    post_structure: List[str] = Field(
        default_factory=list,
        description="Ordered beats every post follows, e.g. ['Name the obvious claim', 'Say what is actually interesting instead']"
    )
    worked_example: Optional[str] = Field(
        None,
        description="An exemplar post demonstrating the structure and voice. Used as the primary few-shot anchor before any real posts exist."
    )
    requires_standalone_closing_line: bool = Field(
        False,
        description="If true, the draft must end with a short standalone line separated by a blank line (checked programmatically)."
    )

class EditorialThresholds(BaseModel):
    min_relevance: float = Field(7.0, ge=1.0, le=10.0, description="Minimum relevance score (1-10)")
    min_novelty: float = Field(7.0, ge=1.0, le=10.0, description="Minimum novelty score (1-10)")
    min_credibility: float = Field(7.0, ge=1.0, le=10.0, description="Minimum credibility score (1-10)")
    min_timeliness: float = Field(6.0, ge=1.0, le=10.0, description="Minimum timeliness score (1-10)")

class PostingCadenceHours(BaseModel):
    min_hours: float = Field(2.0, ge=0.1)
    max_hours: float = Field(5.0, ge=0.5)

class PersonaConfig(BaseModel):
    name: str = Field(..., description="Persona name")
    domain: str = Field(..., description="Primary domain of focus")
    bio: str = Field(..., description="Short bio and mission statement")
    voice_guidelines: VoiceGuidelines
    stable_interests: List[str] = Field(default_factory=list, description="Keywords or subfields monitored")
    editorial_thresholds: EditorialThresholds = Field(default_factory=EditorialThresholds)
    posting_cadence_hours: PostingCadenceHours = Field(default_factory=PostingCadenceHours)
