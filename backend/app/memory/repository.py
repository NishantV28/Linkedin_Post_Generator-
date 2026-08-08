import json
import logging
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session

from backend.app.memory.models import PostModel, RejectedTopicModel, CycleRunModel, AgentModel, utc_now
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
        topic_title: Optional[str] = None
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
            created_at=utc_now()
        )

        db.add(post)
        db.commit()
        db.refresh(post)

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
    def get_rejected_topics(db: Session, agent_id: str, limit: int = 5) -> List[RejectedTopicModel]:
        """Fetch the N most recent rejected topics for an agent, newest first."""
        return db.query(RejectedTopicModel).filter(
            RejectedTopicModel.agent_id == agent_id
        ).order_by(RejectedTopicModel.created_at.desc()).limit(limit).all()
