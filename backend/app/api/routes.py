import json
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import Optional
from datetime import timedelta, timezone

from backend.app.memory.db import get_db
from backend.app.memory.models import AgentModel, PostModel, RejectedTopicModel, utc_now
from backend.app.memory.repository import MemoryRepository
from backend.app.core.scheduler import calculate_next_delay, get_agent_activity, resolve_cadence, start_agent_task, trigger_agent_now
from backend.app.agent.persona.presets import get_preset_by_name_or_domain
from backend.app.agent.reframer import reframe_post
from backend.app.schemas.agent import (
    InitRequest,
    InitResponse,
    FeedResponse,
    FeedItem,
    StatusResponse,
    AgentStatusInfo,
    RejectedTopicsResponse,
    RejectedTopicItem,
    ReframeRequest,
    ReframeResponse,
)

router = APIRouter(prefix="/api/agent", tags=["agent"])


def format_iso8601(dt) -> str:
    """Format datetime into ISO 8601 string (e.g. 2026-08-08T10:00:00Z)."""
    if dt is None:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


@router.post("/init", response_model=InitResponse, status_code=status.HTTP_201_CREATED)
async def init_agent(req: InitRequest, db: Session = Depends(get_db)):
    """
    Initialize a persona agent.
    Idempotency guard: If an active agent with the same name and domain exists,
    triggers an immediate cycle run and returns its agentId.
    Otherwise, creates a new agent record in SQLite.
    """
    persona_info = req.persona
    name = persona_info.name.strip()
    domain = persona_info.domain.strip()

    if not name or not domain:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Both 'name' and 'domain' must be provided in persona."
        )

    # Idempotency / Reactivation guard. Matched case-insensitively.
    existing_agent = db.query(AgentModel).filter(
        func.lower(AgentModel.name) == name.lower(),
        func.lower(AgentModel.domain) == domain.lower()
    ).first()

    if existing_agent:
        existing_agent.active = True
        existing_agent.created_at = utc_now()
        existing_agent.next_run_at = utc_now()
        db.commit()
        trigger_agent_now(existing_agent.id)
        return InitResponse(agentId=existing_agent.id)

    # Generate full persona configuration from presets + overrides
    persona_config = get_preset_by_name_or_domain(name, domain)
    if persona_info.bio:
        persona_config.bio = persona_info.bio

    now = utc_now()
    cadence = persona_config.posting_cadence_hours
    min_h, max_h = resolve_cadence(cadence.min_hours, cadence.max_hours)
    first_delay = calculate_next_delay(min_h, max_h)
    new_agent = AgentModel(
        name=name,
        domain=domain,
        persona_json=persona_config.model_dump_json(),
        active=True,
        created_at=now,
        next_run_at=now + timedelta(seconds=first_delay),
        cycle_count=0
    )

    db.add(new_agent)
    db.commit()
    db.refresh(new_agent)

    # Launch autonomous background scheduler task for new agent
    trigger_agent_now(new_agent.id)

    return InitResponse(agentId=new_agent.id)


@router.get("/feed", response_model=FeedResponse)
def get_feed(agentId: str = Query(..., description="Target Agent ID"), db: Session = Depends(get_db)):
    """
    Read feed posts for a given agentId.
    Ordered by created_at DESC. Pure read endpoint, no LLM calls.
    """
    agent = db.query(AgentModel).filter(AgentModel.id == agentId).first()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent with id '{agentId}' not found."
        )

    posts_query = db.query(PostModel).filter(
        PostModel.agent_id == agentId
    ).order_by(PostModel.created_at.desc()).all()

    feed_items = []
    for post in posts_query:
        try:
            sources = json.loads(post.sources_json) if post.sources_json else []
        except Exception:
            sources = []

        feed_items.append(
            FeedItem(
                id=post.id,
                createdAt=format_iso8601(post.created_at),
                text=post.text,
                rationale=post.rationale,
                sources=sources
            )
        )

    return FeedResponse(posts=feed_items)


@router.get("/status", response_model=StatusResponse)
def get_status(agentId: Optional[str] = Query(None), db: Session = Depends(get_db)):
    """Debug/demo endpoint: Get agent status."""
    query = db.query(AgentModel)
    if agentId:
        query = query.filter(AgentModel.id == agentId)

    agents = query.all()
    result = []
    for a in agents:
        result.append(
            AgentStatusInfo(
                agentId=a.id,
                name=a.name,
                domain=a.domain,
                active=a.active,
                createdAt=format_iso8601(a.created_at),
                nextRunAt=format_iso8601(a.next_run_at) if a.next_run_at else None,
                cycleCount=a.cycle_count
            )
        )
    return StatusResponse(agents=result)


@router.get("/activity")
def get_activity(agentId: str = Query(..., description="Target Agent ID"), db: Session = Depends(get_db)):
    """Return truthful, in-memory progress for a currently executing cycle."""
    agent = db.query(AgentModel).filter(AgentModel.id == agentId).first()
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Agent with id '{agentId}' not found.")
    return get_agent_activity(agentId)


@router.get("/rejected", response_model=RejectedTopicsResponse)
def get_rejected_topics(agentId: Optional[str] = Query(None), db: Session = Depends(get_db)):
    """Debug/demo endpoint: Get rejected topics audit log."""
    query = db.query(RejectedTopicModel)
    if agentId:
        query = query.filter(RejectedTopicModel.agent_id == agentId)

    rejected_list = query.order_by(RejectedTopicModel.created_at.desc()).all()
    result = []
    for r in rejected_list:
        scores = None
        if r.judge_scores_json:
            try:
                scores = json.loads(r.judge_scores_json)
            except Exception:
                scores = None

        result.append(
            RejectedTopicItem(
                id=r.id,
                agentId=r.agent_id,
                title=r.title,
                sourceUrl=r.source_url,
                reason=r.reason,
                judgeScores=scores,
                createdAt=format_iso8601(r.created_at)
            )
        )
    return RejectedTopicsResponse(rejectedTopics=result)


@router.post("/reframe", response_model=ReframeResponse)
def reframe_existing_post(req: ReframeRequest, db: Session = Depends(get_db)):
    """
    Reframe / restructure an existing post based on human feedback.
    Applies user feedback, ensures relevant hashtags are included, and updates the database record.
    """
    post_id = req.postId.strip()
    feedback = req.feedback.strip()

    if not post_id or not feedback:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Both 'postId' and 'feedback' must be provided."
        )

    post = db.query(PostModel).filter(PostModel.id == post_id).first()
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Post with id '{post_id}' not found."
        )

    # Get persona details
    persona_name = "Ada Engine"
    persona_domain = "AI Research"
    persona_bio = None

    if post.agent_id:
        agent = db.query(AgentModel).filter(AgentModel.id == post.agent_id).first()
        if agent:
            persona_name = agent.name or persona_name
            persona_domain = agent.domain or persona_domain
            if agent.persona_json:
                try:
                    p_data = json.loads(agent.persona_json)
                    persona_bio = p_data.get("bio")
                except Exception:
                    pass

    try:
        new_text = reframe_post(
            original_text=post.text,
            user_feedback=feedback,
            persona_name=persona_name,
            persona_domain=persona_domain,
            persona_bio=persona_bio
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reframe post: {str(e)}"
        )

    # Update in DB & ChromaDB
    updated_rationale = f"{post.rationale}\n\n[Human Feedback Revision]: {feedback}" if post.rationale else f"[Human Feedback Revision]: {feedback}"
    updated_post = MemoryRepository.update_post(
        db=db,
        post_id=post_id,
        new_text=new_text,
        new_rationale=updated_rationale
    )

    return ReframeResponse(
        postId=post_id,
        text=updated_post.text,
        rationale=updated_post.rationale or ""
    )

