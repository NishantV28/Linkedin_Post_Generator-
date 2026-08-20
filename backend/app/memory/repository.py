import json
import logging
from typing import List, Optional, Dict, Any
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.memory.models import (
    PostModel,
    PostRevisionModel,
    RejectedTopicModel,
    CycleRunModel,
    AgentModel,
    utc_now,
)
from backend.app.memory.embeddings import embed
from backend.app.memory.vector_store import add_post_vector

logger = logging.getLogger("autonomous_agent.memory.repository")

class MemoryRepository:
    """Repository helper for atomic operations across SQLite database and ChromaDB vector store."""

    @staticmethod
    def save_post(
        db: Session,
        agent_id: str,
        text: str,
        rationale: str,
        sources: List[str],
        topic_title: Optional[str] = None,
        kind: str = "topic"
    ) -> PostModel:
        """
        Saves a published post to SQLite and syncs its dense embedding to ChromaDB.
        """
        post = PostModel(
            agent_id=agent_id,
            text=text,
            rationale=rationale,
            sources_json=json.dumps(sources),
            topic_title=topic_title or "Untitled Topic",
            kind=kind,
            created_at=utc_now()
        )

        db.add(post)
        db.commit()
        db.refresh(post)

        # Version 1 - the post as the agent first wrote it. Recorded up front so the
        # original wording survives any later reframe.
        db.add(PostRevisionModel(
            post_id=post.id,
            version=1,
            text=post.text,
            rationale=post.rationale,
            feedback=None,
            source="original",
            created_at=post.created_at
        ))
        db.commit()

        # Sync to ChromaDB
        embed_text = f"{topic_title or ''} {text}"
        vector = embed(embed_text)
        add_post_vector(
            agent_id=agent_id,
            post_id=post.id,
            text=embed_text,
            embedding=vector,
            metadata={"topic_title": topic_title or "", "type": "published"}
        )

        logger.info(f"Saved post {post.id} for agent {agent_id} to SQLite and ChromaDB.")
        return post

    @staticmethod
    def list_revisions(db: Session, post_id: str) -> List["PostRevisionModel"]:
        """Every saved version of a post, oldest first."""
        return (
            db.query(PostRevisionModel)
            .filter(PostRevisionModel.post_id == post_id)
            .order_by(PostRevisionModel.version.asc())
            .all()
        )

    @staticmethod
    def update_post(
        db: Session,
        post_id: str,
        new_text: str,
        new_rationale: Optional[str] = None,
        feedback: Optional[str] = None,
        source: str = "reframe"
    ) -> Optional[PostModel]:
        """
        Replace a post's text, keeping the previous wording as a numbered revision.

        The embedding is computed before the commit rather than after: a failure there
        used to leave SQLite holding the new text while ChromaDB kept the old vector
        AND the old document, so deduplication and few-shot retrieval silently ran on
        wording that no longer existed. Failing before the commit keeps the two stores
        agreeing with each other.
        """
        post = db.query(PostModel).filter(PostModel.id == post_id).first()
        if not post:
            return None

        if not new_text or len(new_text.split()) < 40:
            # Guard against a blank or truncated model response overwriting a real post.
            raise ValueError(
                f"Refusing to replace post {post_id} with {len(new_text.split())} words."
            )

        embed_text = f"{post.topic_title or ''} {new_text}"
        vector = embed(embed_text)

        last_version = (
            db.query(func.max(PostRevisionModel.version))
            .filter(PostRevisionModel.post_id == post_id)
            .scalar()
        )
        # A post created before revision tracking has no rows yet; its current text is
        # version 1, so the incoming text becomes version 2.
        if last_version is None:
            db.add(PostRevisionModel(
                post_id=post.id,
                version=1,
                text=post.text,
                rationale=post.rationale,
                feedback=None,
                source="original",
                created_at=post.created_at
            ))
            last_version = 1

        post.text = new_text
        if new_rationale is not None:
            post.rationale = new_rationale

        db.add(PostRevisionModel(
            post_id=post.id,
            version=last_version + 1,
            text=new_text,
            rationale=new_rationale,
            feedback=feedback,
            source=source,
            created_at=utc_now()
        ))

        db.commit()
        db.refresh(post)

        add_post_vector(
            agent_id=post.agent_id,
            post_id=post.id,
            text=embed_text,
            embedding=vector,
            metadata={"topic_title": post.topic_title or "", "type": "published"}
        )

        logger.info(f"Updated post {post.id} to version {last_version + 1} ({source}).")
        return post

    @staticmethod
    def save_rejection(
        db: Session,
        agent_id: str,
        title: str,
        reason: str,
        source_url: Optional[str] = None,
        judge_scores: Optional[Dict[str, Any]] = None
    ) -> RejectedTopicModel:
        """Saves a rejected candidate topic record to SQLite."""
        rejection = RejectedTopicModel(
            agent_id=agent_id,
            title=title,
            source_url=source_url,
            reason=reason,
            judge_scores_json=json.dumps(judge_scores) if judge_scores else None,
            created_at=utc_now()
        )
        db.add(rejection)
        db.commit()
        db.refresh(rejection)
        logger.info(f"Recorded rejection for topic '{title}' (Agent: {agent_id}). Reason: {reason}")
        return rejection

    @staticmethod
    def save_cycle_run(
        db: Session,
        agent_id: str,
        outcome: str,
        candidates_seen: int,
        started_at: Optional[Any] = None
    ) -> CycleRunModel:
        """Logs a completed agent execution cycle run to SQLite."""
        cycle = CycleRunModel(
            agent_id=agent_id,
            started_at=started_at or utc_now(),
            finished_at=utc_now(),
            outcome=outcome,
            candidates_seen=candidates_seen
        )
        db.add(cycle)

        # Update agent cycle_count
        agent = db.query(AgentModel).filter(AgentModel.id == agent_id).first()
        if agent:
            agent.cycle_count += 1

        db.commit()
        db.refresh(cycle)
        return cycle

    @staticmethod
    def get_recent_posts(db: Session, agent_id: str, limit: int = 5) -> List[PostModel]:
        """Fetch the N most recent published posts for an agent."""
        return db.query(PostModel).filter(
            PostModel.agent_id == agent_id
        ).order_by(PostModel.created_at.desc()).limit(limit).all()

    @staticmethod
    def get_rejected_urls(db: Session, agent_id: str) -> set:
        """
        Source URLs this agent has already turned down.

        Discovery returns the same items cycle after cycle, so without this the agent
        re-judges known rejects at full LLM cost for the whole run.
        """
        rows = db.query(RejectedTopicModel.source_url).filter(
            RejectedTopicModel.agent_id == agent_id,
            RejectedTopicModel.source_url.isnot(None)
        ).all()
        return {row[0] for row in rows if row[0]}

    @staticmethod
    def get_rejected_topics(db: Session, agent_id: str, limit: int = 5) -> List[RejectedTopicModel]:
        """Fetch the N most recent rejected topics for an agent, newest first."""
        return db.query(RejectedTopicModel).filter(
            RejectedTopicModel.agent_id == agent_id
        ).order_by(RejectedTopicModel.created_at.desc()).limit(limit).all()
