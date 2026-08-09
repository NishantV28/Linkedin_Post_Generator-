"""
Run one autonomous cycle and print what it decided.

Calls the same `execute_cycle_for_agent` the scheduler uses, so the harness exercises
the real pipeline: pre-filter, rejection memory, deduplication, topic spacing, the
editorial judge, the writer, QA and publication. An earlier version re-implemented
discovery itself, which meant it judged every raw candidate instead of the pre-filtered
ten, and quietly tested a pipeline that never runs in production.
"""

import os
import sys
import json
import logging

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Windows consoles default to cp1252, which cannot encode the typographic characters
# (em dashes, curly quotes) that appear in generated posts. Without this, printing a
# post raises UnicodeEncodeError.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass

from backend.app.core.config import settings
from backend.app.core.scheduler import execute_cycle_for_agent
from backend.app.memory.db import init_db, SessionLocal
from backend.app.memory.models import AgentModel, PostModel, RejectedTopicModel
from backend.app.agent.persona.presets import DISTILL_PRESET

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

RULE = "=" * 78


def _has_llm_key() -> bool:
    groq = settings.GROQ_API_KEY or os.environ.get("GROQ_API_KEY")
    openai_key = settings.OPENAI_API_KEY or os.environ.get("OPENAI_API_KEY")
    return bool([k for k in (groq, openai_key) if k and not k.startswith("your_")])


def _get_or_create_agent(db):
    agent = db.query(AgentModel).filter(AgentModel.name == DISTILL_PRESET.name).first()
    if agent:
        print(f"Using existing agent {agent.name} ({agent.id})")
        return agent

    agent = AgentModel(
        name=DISTILL_PRESET.name,
        domain=DISTILL_PRESET.domain,
        persona_json=DISTILL_PRESET.model_dump_json(),
        active=True,
        cycle_count=0,
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)
    print(f"Created agent {agent.name} ({agent.id})")
    return agent


def _print_posts(db, agent_id, before_ids):
    query = db.query(PostModel).filter(PostModel.agent_id == agent_id)
    if before_ids:
        query = query.filter(~PostModel.id.in_(before_ids))
    posts = query.order_by(PostModel.created_at.desc()).all()

    if not posts:
        print()
        print("No post published this cycle.")
        print("That is a valid outcome: this persona publishes only when a candidate")
        print("clears its editorial bar.")
        return

    for post in posts:
        print()
        print(RULE)
        print(f"PUBLISHED ({post.kind})")
        print(RULE)
        print(f"Topic  : {post.topic_title}")
        print(f"Sources: {json.loads(post.sources_json or '[]')}")
        print()
        print(post.text)
        print()
        print(f"[{len(post.text.split())} words]")
        print()
        print("--- RATIONALE ---")
        print(post.rationale)


def _print_rejections(db, agent_id, limit=8):
    rows = (
        db.query(RejectedTopicModel)
        .filter(RejectedTopicModel.agent_id == agent_id)
        .order_by(RejectedTopicModel.created_at.desc())
        .limit(limit)
        .all()
    )
    if not rows:
        return

    print()
    print(RULE)
    print(f"EDITORIAL DECISIONS AGAINST ({len(rows)} most recent)")
    print(RULE)
    for row in rows:
        try:
            scores = json.loads(row.judge_scores_json or "{}")
        except Exception:
            scores = {}
        stage = scores.get("stage", "?")
        disqualifier = scores.get("disqualifier")
        headline = f"[{stage}]" + (f" {disqualifier}" if disqualifier else "")
        reason = row.reason.split("] ", 1)[-1]
        print()
        print(f"{headline} {row.title[:66]}")
        print(f"   {reason[:230]}")


def main():
    if not _has_llm_key():
        print("No usable LLM key found. Set GROQ_API_KEY or OPENAI_API_KEY in .env.")
        return

    print(RULE)
    print("ONE AUTONOMOUS CYCLE - the same path the scheduler runs")
    print(RULE)
    print(f"Model: {settings.LLM_MODEL or '(provider default)'}")

    init_db()
    db = SessionLocal()
    try:
        agent = _get_or_create_agent(db)
        agent_id = agent.id
        before_ids = [
            p.id for p in db.query(PostModel).filter(PostModel.agent_id == agent_id).all()
        ]
    finally:
        db.close()

    outcome = execute_cycle_for_agent(agent_id)

    db = SessionLocal()
    try:
        print()
        print(RULE)
        print(f"CYCLE OUTCOME: {outcome}")
        print(RULE)
        _print_posts(db, agent_id, before_ids)
        _print_rejections(db, agent_id)
    finally:
        db.close()


if __name__ == "__main__":
    main()
