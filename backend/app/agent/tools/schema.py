from pydantic import BaseModel, Field
from typing import Literal

class TopicCandidate(BaseModel):
    """Normalized candidate topic retrieved from discovery sources."""
    id: str = Field(..., description="Unique identifier for the candidate topic")
    title: str = Field(..., description="Headline or paper title")
    summary: str = Field(..., description="Abstract, snippet, or description text")
    url: str = Field(..., description="Source URL")
    source: Literal["hn", "arxiv", "github", "web"] = Field(..., description="Discovery source origin")
    published_at: str = Field(..., description="ISO 8601 publication or discovery timestamp")
    engagement: int = Field(
        0,
        description=(
            "How much discussion this attracted at source (HN points, GitHub stars). "
            "0 where the source has no such signal. Used to judge credibility: a story "
            "a technical community has argued over is better vetted than an unnoticed link."
        )
    )
