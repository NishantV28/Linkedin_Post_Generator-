import json
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import Optional
from datetime import timedelta, timezone

from backend.app.memory.db import get_db
from backend.app.memory.models import AgentModel, PostModel, RejectedTopicModel, utc_now
from backend.app.core.scheduler import calculate_next_delay, resolve_cadence, start_agent_task
from backend.app.agent.persona.presets import get_preset_by_name_or_domain
from backend.app.schemas.agent import (
    InitRequest,
    InitResponse,
    FeedResponse,
    FeedItem,
    StatusResponse,
    AgentStatusInfo,
    RejectedTopicsResponse,
    RejectedTopicItem
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
    Idempotency guard: If an active agent with the same name and domain exists, returns its agentId.
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

    # Idempotency guard. Matched case-insensitively: "distill"/"AI research" and
    # "Distill"/"AI Research" are the same persona, and treating them as two spawns
    # a second scheduler loop that competes for the same API quota.
    existing_agent = db.query(AgentModel).filter(
        func.lower(AgentModel.name) == name.lower(),
        func.lower(AgentModel.domain) == domain.lower(),
        AgentModel.active == True
    ).first()

    if existing_agent:
        # Ensure task is running
        if existing_agent.next_run_at:
            scheduled_at = existing_agent.next_run_at
            if scheduled_at.tzinfo is None:
                scheduled_at = scheduled_at.replace(tzinfo=timezone.utc)
            delay = max(0.0, (scheduled_at - utc_now()).total_seconds())
        else:
            delay = 0.0
        start_agent_task(existing_agent.id, initial_delay_seconds=delay)
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
    start_agent_task(new_agent.id, initial_delay_seconds=first_delay)

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
