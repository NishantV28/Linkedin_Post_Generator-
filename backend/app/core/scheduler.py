import asyncio
import logging
import random
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Tuple
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.memory.db import SessionLocal
from backend.app.memory.models import AgentModel, CycleRunModel, PostModel, utc_now
from backend.app.agent.persona.schema import PersonaConfig
from backend.app.agent.tools.discovery import discover_all_candidates
from backend.app.agent.tools.prefilter import prefilter_candidates
from backend.app.memory.hybrid_retriever import HybridRetriever
from backend.app.agent.graph import agent_graph

logger = logging.getLogger("autonomous_agent.core.scheduler")

# Global task registry to prevent duplicate running tasks per agent
_running_tasks: Dict[str, asyncio.Task] = {}


def _as_utc(value: datetime) -> datetime:
    """Normalise SQLite datetimes, which may be returned without tzinfo."""
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

def calculate_next_delay(min_hours: float, max_hours: float) -> float:
    """Calculate random jittered delay in seconds between min and max hours."""
    hours = random.uniform(min_hours, max_hours)
    return hours * 3600.0


def resolve_cadence(persona_min: Optional[float], persona_max: Optional[float]) -> Tuple[float, float]:
    """
    Decide the cadence bounds actually used for scheduling.

    Precedence: explicit env override (demos/tests) > the persona's own cadence >
    global fallback. The persona's cadence is part of its identity, so it wins over
    the fallback - but an operator running a demo needs a way to compress it.
    """
    override_min = settings.CADENCE_OVERRIDE_MIN_HOURS
    override_max = settings.CADENCE_OVERRIDE_MAX_HOURS
    if override_min is not None and override_max is not None:
        return override_min, override_max

    return (
        persona_min if persona_min is not None else settings.CADENCE_MIN_HOURS,
        persona_max if persona_max is not None else settings.CADENCE_MAX_HOURS,
    )


def has_reached_post_cap(db: Session, agent_id: str) -> bool:
    """Return whether the agent has exhausted its 48-hour publication budget."""
    return db.query(PostModel).filter(PostModel.agent_id == agent_id).count() >= settings.MAX_POSTS_48H

def execute_cycle_for_agent(agent_id: str) -> Optional[str]:
    """
    Executes a single autonomous cycle for an agent:
    1. Fetch agent persona & state from SQLite
    2. Discover candidates across HN, arXiv, GitHub, Web
    3. Apply hybrid dense+BM25 deduplication
    4. Invoke LangGraph core agent graph
    5. Update cycle count & record cycle run in SQLite
    """
    db = SessionLocal()
    start_time = utc_now()
    outcome = "failed"
    seen_count = 0

    try:
        agent = db.query(AgentModel).filter(AgentModel.id == agent_id).first()
        if not agent or not agent.active:
            logger.warning(f"Agent '{agent_id}' is inactive or not found. Skipping cycle.")
            return "inactive"

        persona_data = AgentModel.get_persona(agent)
        persona = PersonaConfig.model_validate(persona_data)

        logger.info(f"--- STARTING AUTONOMOUS CYCLE #{agent.cycle_count + 1} FOR AGENT '{agent.name}' ({agent_id}) ---")

        # 1. Discover candidates, then triage cheaply before spending any LLM calls.
        raw_candidates = discover_all_candidates(persona)
        seen_count = len(raw_candidates)
        logger.info(f"Discovered {seen_count} raw candidates.")

        raw_candidates = prefilter_candidates(raw_candidates, persona)

        # 2. Hybrid Deduplication. The batch doubles as extra IDF corpus, so
        # terms common across this cycle's candidates count as generic.
        surviving_candidates = []
        batch_texts = [f"{c.title} {c.summary}" for c in raw_candidates]
        for cand in raw_candidates:
            is_dup, reason, _ = HybridRetriever.is_duplicate(
                cand, agent_id=agent.id, db=db, corpus_texts=batch_texts
            )
            if not is_dup:
                surviving_candidates.append(cand)
            else:
                logger.debug(f"Dedup dropped candidate '{cand.title[:45]}...': {reason}")

        logger.info(f"{len(surviving_candidates)} novel candidate(s) survived deduplication.")

        if not surviving_candidates:
            outcome = "no_novel_candidates"
            logger.info("No novel candidates survived deduplication. Cycle completed with no post.")
        else:
            # 3. LangGraph Core Invocation
            initial_state = {
                "persona": persona,
                "agent_id": agent.id,
                "candidates": surviving_candidates,
                "candidate_idx": 0,
                "current_candidate": None,
                "judge_verdict": None,
                "draft": None,
                "qa_verdict": None,
                "retry_count": 0,
                "published_post": None,
                "rejected_count": 0,
                "cycle_outcome": "init"
            }

            # Each candidate costs at most ~6 steps (judge, writer, qa, revisions,
            # rejection log, advance); allow headroom so a long candidate list is
            # not mistaken for a runaway loop.
            recursion_limit = max(50, 8 * len(surviving_candidates))
            final_state = agent_graph.invoke(initial_state, {"recursion_limit": recursion_limit})
            outcome = final_state.get("cycle_outcome", "completed")

        # 4. Update Agent Metrics
        agent.cycle_count += 1
        db.commit()

        return outcome

    except Exception as e:
        logger.error(f"Error during cycle execution for agent '{agent_id}': {e}", exc_info=True)
        outcome = f"error: {str(e)[:100]}"
        return outcome

    finally:
        # Record cycle run audit row
        try:
            finish_time = utc_now()
            cycle_run = CycleRunModel(
                agent_id=agent_id,
                started_at=start_time,
                finished_at=finish_time,
                outcome=outcome,
                candidates_seen=seen_count
            )
            db.add(cycle_run)
            db.commit()
        except Exception as err:
            logger.error(f"Failed to record cycle run audit row: {err}")
        db.close()

async def agent_scheduler_loop(agent_id: str, initial_delay_seconds: float = 0.0):
    """
    Async background runner loop for a single agent.
    Runs continuously until 48h limit or max posts cap is reached, or agent deactivated.
    """
    if initial_delay_seconds > 0:
        logger.info(f"Agent '{agent_id}' scheduler starting with initial delay of {initial_delay_seconds:.1f}s.")
        await asyncio.sleep(initial_delay_seconds)

    while True:
        db = SessionLocal()
        try:
            agent = db.query(AgentModel).filter(AgentModel.id == agent_id).first()
            if not agent or not agent.active:
                logger.info(f"Agent '{agent_id}' is no longer active. Exiting scheduler loop.")
                break

            now = utc_now()

            # Hard stop condition 1: 48-hour window elapsed
            window_end = _as_utc(agent.created_at) + timedelta(hours=48)
            if now >= window_end:
                logger.info(f"Agent '{agent_id}' reached 48h operation window limit. Deactivating agent.")
                agent.active = False
                db.commit()
                break

            # Hard stop condition 2: published-post cap reached.  A cycle may
            # reject every candidate, so it must not consume the post budget.
            if has_reached_post_cap(db, agent_id):
                logger.info(f"Agent '{agent_id}' reached max post cap ({settings.MAX_POSTS_48H}). Deactivating agent.")
                agent.active = False
                db.commit()
                break

            persona_data = AgentModel.get_persona(agent)
            cadence = persona_data.get("posting_cadence_hours", {})
            min_h, max_h = resolve_cadence(cadence.get("min_hours"), cadence.get("max_hours"))

            db.close()

            # Execute autonomous cycle in thread pool to keep asyncio event loop responsive
            loop = asyncio.get_running_loop()
            outcome = await loop.run_in_executor(None, execute_cycle_for_agent, agent_id)

            # Schedule next run
            db = SessionLocal()
            agent = db.query(AgentModel).filter(AgentModel.id == agent_id).first()
            if not agent or not agent.active:
                break

            # A successful cycle can publish the final permitted post. Stop
            # immediately instead of waiting for another scheduled wake-up.
            if has_reached_post_cap(db, agent_id):
                logger.info(f"Agent '{agent_id}' reached max post cap ({settings.MAX_POSTS_48H}). Deactivating agent.")
                agent.active = False
                agent.next_run_at = None
                db.commit()
                break

            delay_seconds = calculate_next_delay(min_h, max_h)
            next_run = utc_now() + timedelta(seconds=delay_seconds)
            agent.next_run_at = next_run
            db.commit()

            logger.info(f"Cycle completed (Outcome: {outcome}). Next run scheduled for {next_run.isoformat()} (in {delay_seconds/60:.1f} minutes).")

        except Exception as e:
            logger.error(f"Unexpected error in agent scheduler loop for '{agent_id}': {e}", exc_info=True)
            delay_seconds = 300.0  # Fallback 5 minute retry on system error
        finally:
            db.close()

        await asyncio.sleep(delay_seconds)

    # Do not leave a completed task in the registry; a future /init or restart
    # can then launch a fresh task for the same agent.
    current_task = asyncio.current_task()
    if _running_tasks.get(agent_id) is current_task:
        _running_tasks.pop(agent_id, None)

def start_agent_task(agent_id: str, initial_delay_seconds: float = 0.0) -> Optional[asyncio.Task]:
    """Launch background task for agent if not already running."""
    if agent_id in _running_tasks and not _running_tasks[agent_id].done():
        logger.info(f"Task for agent '{agent_id}' is already running.")
        return _running_tasks[agent_id]

    task = asyncio.get_running_loop().create_task(agent_scheduler_loop(agent_id, initial_delay_seconds))
    _running_tasks[agent_id] = task
    logger.info(f"Started background scheduler task for agent '{agent_id}'.")
    return task

def rearm_active_agents():
    """
    On application startup: query SQLite for all active agents,
    calculate remaining delay until next_run_at, and re-arm background task loops.
    """
    db = SessionLocal()
    try:
        active_agents = db.query(AgentModel).filter(AgentModel.active == True).all()
        logger.info(f"Re-arming scheduler for {len(active_agents)} active agent(s)...")

        now = utc_now()
        for agent in active_agents:
            if agent.next_run_at and _as_utc(agent.next_run_at) > now:
                remaining_seconds = (_as_utc(agent.next_run_at) - now).total_seconds()
            else:
                remaining_seconds = 0.0

            start_agent_task(agent.id, initial_delay_seconds=remaining_seconds)
    except Exception as e:
        logger.error(f"Error re-arming active agents: {e}", exc_info=True)
    finally:
        db.close()


async def stop_all_agent_tasks() -> None:
    """Cancel scheduler tasks during FastAPI shutdown and await their cleanup."""
    tasks = list(_running_tasks.values())
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    _running_tasks.clear()
