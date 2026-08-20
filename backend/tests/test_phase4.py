import pytest
import asyncio
from datetime import datetime, timedelta, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.memory.models import Base, AgentModel, PostModel, utc_now
from backend.app.core.config import settings
from backend.app.core.scheduler import (
    calculate_next_delay,
    has_reached_post_cap,
    rearm_active_agents,
    start_agent_task,
    _running_tasks
)
from backend.app.agent.persona.presets import DISTILL_PRESET

TEST_DB_URL = "sqlite:///:memory:"
engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

def test_calculate_next_delay():
    delay = calculate_next_delay(2.0, 5.0)
    assert 2.0 * 3600.0 <= delay <= 5.0 * 3600.0

def test_rearm_active_agents_logic():
    import backend.app.core.scheduler as sched_module
    original_session_local = sched_module.SessionLocal
    sched_module.SessionLocal = TestingSessionLocal

    db = TestingSessionLocal()

    now = utc_now()
    future_run = now + timedelta(seconds=100)

    active_agent = AgentModel(
        name="ActiveAgent",
        domain="AI Research",
        persona_json=DISTILL_PRESET.model_dump_json(),
        active=True,
        created_at=now,
        next_run_at=future_run,
        cycle_count=1
    )
    inactive_agent = AgentModel(
        name="InactiveAgent",
        domain="AI Security",
        persona_json=DISTILL_PRESET.model_dump_json(),
        active=False,
        created_at=now,
        cycle_count=5
    )

    db.add_all([active_agent, inactive_agent])
    db.commit()

    # Clear running tasks registry
    _running_tasks.clear()

    # Execute re-arming inside an event loop, matching FastAPI's lifespan.
    async def rearm():
        rearm_active_agents()
        await asyncio.sleep(0)

    try:
        asyncio.run(rearm())

        assert active_agent.id in _running_tasks
        assert inactive_agent.id not in _running_tasks
    finally:
        _running_tasks.clear()
        sched_module.SessionLocal = original_session_local
        db.close()

def test_hard_stop_max_posts_cap():
    """
    The budget counts approved posts inside the current window.

    It used to count every post the agent had ever written, regardless of age or
    review state, so a reactivated agent hit the cap on its first tick and retired
    itself immediately.
    """
    db = TestingSessionLocal()

    now = utc_now()
    capped_agent = AgentModel(
        name="CappedAgent",
        domain="AI",
        persona_json=DISTILL_PRESET.model_dump_json(),
        active=True,
        created_at=now,
        cycle_count=0
    )
    db.add(capped_agent)
    db.commit()

    db.add_all([
        PostModel(agent_id=capped_agent.id, text="x", rationale="x", status="approved")
        for _ in range(settings.MAX_POSTS_48H)
    ])
    db.commit()

    assert has_reached_post_cap(db, capped_agent.id) is True
    db.close()


def test_pending_drafts_do_not_consume_the_post_budget():
    """A queue of unreviewed drafts must not silently retire the agent."""
    db = TestingSessionLocal()

    agent = AgentModel(
        name="DraftHeavyAgent",
        domain="AI",
        persona_json=DISTILL_PRESET.model_dump_json(),
        active=True,
        created_at=utc_now(),
        cycle_count=0
    )
    db.add(agent)
    db.commit()

    db.add_all([
        PostModel(agent_id=agent.id, text="x", rationale="x", status="pending")
        for _ in range(settings.MAX_POSTS_48H + 5)
    ])
    db.commit()

    assert has_reached_post_cap(db, agent.id) is False
    db.close()


def test_posts_from_a_previous_window_do_not_count():
    """
    Reactivating an agent restarts its window, so posts from the earlier run fall
    outside it. Without this an agent could never run again after a completed cycle.
    """
    db = TestingSessionLocal()

    now = utc_now()
    agent = AgentModel(
        name="ReactivatedAgent",
        domain="AI",
        persona_json=DISTILL_PRESET.model_dump_json(),
        active=True,
        created_at=now,          # the window starts here
        cycle_count=0
    )
    db.add(agent)
    db.commit()

    db.add_all([
        PostModel(
            agent_id=agent.id, text="x", rationale="x", status="approved",
            created_at=now - timedelta(days=5),   # from the agent's previous run
        )
        for _ in range(settings.MAX_POSTS_48H)
    ])
    db.commit()

    assert has_reached_post_cap(db, agent.id) is False
    db.close()
