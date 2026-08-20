import json
import uuid
from typing import Any, Dict
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, Boolean, Integer, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

def generate_uuid() -> str:
    return str(uuid.uuid4())

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class AgentModel(Base):
    __tablename__ = "agents"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(255), nullable=False)
    domain = Column(String(255), nullable=False)
    persona_json = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    active = Column(Boolean, nullable=False, default=True)
    next_run_at = Column(DateTime(timezone=True), nullable=True)
    cycle_count = Column(Integer, nullable=False, default=0)

    posts = relationship("PostModel", back_populates="agent", cascade="all, delete-orphan")
    rejected_topics = relationship("RejectedTopicModel", back_populates="agent", cascade="all, delete-orphan")
    cycle_runs = relationship("CycleRunModel", back_populates="agent", cascade="all, delete-orphan")

    @staticmethod
    def get_persona(agent: "AgentModel") -> Dict[str, Any]:
        """Deserialize the immutable persona payload stored with an agent."""
        return json.loads(agent.persona_json)


class PostModel(Base):
    __tablename__ = "posts"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    agent_id = Column(String(36), ForeignKey("agents.id"), nullable=False, index=True)
    text = Column(Text, nullable=False)
    rationale = Column(Text, nullable=False)
    sources_json = Column(Text, nullable=False, default="[]")
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    topic_title = Column(String(512), nullable=True)
    # "topic" for an ordinary post, "reflection" for one about the agent's own
    # recent coverage. Used to pace reflections rather than emit them back to back.
    kind = Column(String(32), nullable=False, default="topic", server_default="topic")

    agent = relationship("AgentModel", back_populates="posts")
    revisions = relationship(
        "PostRevisionModel",
        back_populates="post",
        cascade="all, delete-orphan",
        order_by="PostRevisionModel.version"
    )


class PostRevisionModel(Base):
    """
    One saved version of a post's text.

    Reframing used to overwrite `posts.text` in place, so the previous wording was
    gone the moment a user asked for a change - there was no way to compare drafts or
    undo a bad instruction. Every version is recorded here instead, including the
    original, so the post's whole history stays readable and restorable.
    """
    __tablename__ = "post_revisions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    post_id = Column(String(36), ForeignKey("posts.id"), nullable=False, index=True)
    # 1 is the post as first published; each reframe or restore adds the next number.
    version = Column(Integer, nullable=False)
    text = Column(Text, nullable=False)
    rationale = Column(Text, nullable=True)
    # The human instruction that produced this version. Null for version 1, which the
    # agent wrote on its own, and for restores.
    feedback = Column(Text, nullable=True)
    # "original" | "reframe" | "restore" - how this version came about.
    source = Column(String(32), nullable=False, default="reframe")
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    post = relationship("PostModel", back_populates="revisions")


class RejectedTopicModel(Base):
    __tablename__ = "rejected_topics"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    agent_id = Column(String(36), ForeignKey("agents.id"), nullable=False, index=True)
    title = Column(String(512), nullable=False)
    source_url = Column(String(1024), nullable=True)
    reason = Column(Text, nullable=False)
    judge_scores_json = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    agent = relationship("AgentModel", back_populates="rejected_topics")


class CycleRunModel(Base):
    __tablename__ = "cycle_runs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    agent_id = Column(String(36), ForeignKey("agents.id"), nullable=False, index=True)
    started_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    outcome = Column(String(64), nullable=False)  # e.g., "published", "no_candidate", "all_rejected", "error"
    candidates_seen = Column(Integer, nullable=False, default=0)

    agent = relationship("AgentModel", back_populates="cycle_runs")
