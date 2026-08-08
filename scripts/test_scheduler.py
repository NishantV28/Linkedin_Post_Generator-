import os
import sys
import asyncio
import logging
from datetime import timedelta

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Windows consoles default to cp1252, which cannot encode the typographic
# characters (em dashes, curly quotes, narrow no-break spaces) that appear in
# generated posts. Without this, printing a post raises UnicodeEncodeError.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass


from backend.app.memory.db import init_db, SessionLocal
from backend.app.memory.models import AgentModel, PostModel, CycleRunModel, utc_now
from backend.app.agent.persona.presets import DISTILL_PRESET
from backend.app.core.scheduler import start_agent_task, rearm_active_agents, execute_cycle_for_agent
from backend.app.core.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("test_scheduler")

async def run_scheduler_test():
    print("=" * 75)
    print("      AUTONOMOUS AI PERSONA AGENT — PHASE 4 SCHEDULER & AUTONOMY HARNESS")
    print("=" * 75)

    # 1. Initialize DB
    init_db()
    db = SessionLocal()

    try:
        # 2. Create or load agent
        agent = db.query(AgentModel).filter(AgentModel.name == DISTILL_PRESET.name).first()
        if not agent:
            # Short cadence override in persona JSON for fast local soak test
            preset_copy = DISTILL_PRESET.model_copy()
            preset_copy.posting_cadence_hours.min_hours = 0.001  # ~3.6 seconds
            preset_copy.posting_cadence_hours.max_hours = 0.002  # ~7.2 seconds

            agent = AgentModel(
                name=preset_copy.name,
                domain=preset_copy.domain,
                persona_json=preset_copy.model_dump_json(),
                active=True,
                created_at=utc_now(),
                cycle_count=0
            )
            db.add(agent)
            db.commit()
            db.refresh(agent)
            print(f"Created new test agent '{agent.name}' (ID: {agent.id})")
        else:
            print(f"Loaded existing agent '{agent.name}' (ID: {agent.id}, Cycle Count: {agent.cycle_count})")

        agent_id = agent.id
        db.close()

        # 3. Force-run 1 cycle synchronously to demonstrate execution logic
        print("\n1. EXECUTING INITIAL SYNCHRONOUS CYCLE...")
        outcome = execute_cycle_for_agent(agent_id)
        print(f"---> Cycle Outcome: {outcome}")

        # 4. Test Autonomy: Start background task with short cadence
        print("\n2. STARTING BACKGROUND AUTONOMOUS SCHEDULER TASK (Soak testing for 15s)...")
        start_agent_task(agent_id, initial_delay_seconds=2.0)

        # Monitor for 15 seconds while background loop runs
        for step in range(1, 4):
            await asyncio.sleep(5.0)
            db = SessionLocal()
            current_agent = db.query(AgentModel).filter(AgentModel.id == agent_id).first()
            post_count = db.query(PostModel).filter(PostModel.agent_id == agent_id).count()
            cycle_runs = db.query(CycleRunModel).filter(CycleRunModel.agent_id == agent_id).count()
            print(f"  [T+{step*5}s Monitor] Active: {current_agent.active} | Cycles Logged: {cycle_runs} | Feed Posts: {post_count}")
            db.close()

        # 5. Simulate Server Restart & Re-arming
        print("\n3. SIMULATING SERVER RESTART & LIFESPAN RE-ARMING...")
        print("Re-arming active agents from SQLite persistent state...")
        rearm_active_agents()
        await asyncio.sleep(3.0)

        # 6. Final Audit
        db = SessionLocal()
        final_agent = db.query(AgentModel).filter(AgentModel.id == agent_id).first()
        posts = db.query(PostModel).filter(PostModel.agent_id == agent_id).all()
        runs = db.query(CycleRunModel).filter(CycleRunModel.agent_id == agent_id).all()

        print("\n" + "=" * 75)
        print("                      AUTONOMY & SCHEDULER SOAK TEST SUMMARY")
        print("=" * 75)
        print(f"  Agent ID               : {final_agent.id}")
        print(f"  Agent Active           : {final_agent.active}")
        print(f"  Total Cycles Run       : {final_agent.cycle_count}")
        print(f"  Total Feed Posts       : {len(posts)}")
        print(f"  Total Cycle Audit Rows : {len(runs)}")
        print(f"  Next Scheduled Run     : {final_agent.next_run_at}")
        print("=" * 75)

    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(run_scheduler_test())
