from pydantic import BaseModel, Field
from typing import List, Optional, Any, Dict

class PersonaInitInfo(BaseModel):
    name: str = Field(..., description="Name of the persona", json_schema_extra={"example": "Distill"})
    domain: str = Field(..., description="Domain of focus", json_schema_extra={"example": "AI Research"})
    bio: Optional[str] = Field(None, description="Optional bio override")
    voiceSamples: Optional[List[str]] = Field(
        None,
        max_length=5,
        description=(
            "Two or three posts written by the user. These demonstrate the voice far "
            "better than the preset's hand-written examples, so they replace them."
        )
    )

class InitRequest(BaseModel):
    persona: PersonaInitInfo

class InitResponse(BaseModel):
    agentId: str = Field(..., description="Unique ID of the initialized agent")

class FeedItem(BaseModel):
    id: str = Field(..., description="Unique post ID")
    createdAt: str = Field(..., description="ISO 8601 formatted timestamp", json_schema_extra={"example": "2026-08-08T10:00:00Z"})
    text: str = Field(..., description="Post body text")
    rationale: str = Field(..., description="Rationale for why this post was selected/published")
    sources: List[str] = Field(default_factory=list, description="List of source URLs")
    status: str = Field("approved", description="pending, approved, rejected or posted")
    reviewedAt: Optional[str] = Field(None, description="When a human decided on this post")

class FeedResponse(BaseModel):
    posts: List[FeedItem]
    pendingCount: int = Field(0, description="How many drafts are waiting for review")

class AgentStatusInfo(BaseModel):
    agentId: str
    name: str
    domain: str
    active: bool
    createdAt: str
    nextRunAt: Optional[str] = None
    cycleCount: int

class StatusResponse(BaseModel):
    agents: List[AgentStatusInfo]

class RejectedTopicItem(BaseModel):
    id: str
    agentId: str
    title: str
    sourceUrl: Optional[str] = None
    reason: str
    judgeScores: Optional[Dict[str, Any]] = None
    createdAt: str

class RejectedTopicsResponse(BaseModel):
    rejectedTopics: List[RejectedTopicItem]


class ReframeRequest(BaseModel):
    postId: str = Field(..., description="The ID of the post to reframe")
    feedback: str = Field(..., description="Human review or feedback instructions to reframe the post")


class ReframeResponse(BaseModel):
    postId: str = Field(..., description="The post ID")
    text: str = Field(..., description="The newly reframed post text")
    rationale: str = Field(..., description="The updated or preserved rationale")


class RevisionItem(BaseModel):
    version: int = Field(..., description="1 is the original; each change adds the next number")
    text: str = Field(..., description="The post text as of this version")
    feedback: Optional[str] = Field(None, description="The human instruction that produced this version")
    source: str = Field(..., description="How this version came about: original, reframe or restore")
    createdAt: str = Field(..., description="When this version was saved")
    isCurrent: bool = Field(..., description="True for the version currently published")


class RevisionsResponse(BaseModel):
    postId: str
    revisions: List[RevisionItem]


class RestoreRequest(BaseModel):
    version: int = Field(..., ge=1, description="The version number to make current again")


class ReviewRequest(BaseModel):
    note: Optional[str] = Field(None, max_length=2000, description="Optional reviewer note")


class ReviewResponse(BaseModel):
    postId: str
    status: str = Field(..., description="pending, approved, rejected or posted")
    reviewedAt: Optional[str] = Field(None, description="When the decision was made")

