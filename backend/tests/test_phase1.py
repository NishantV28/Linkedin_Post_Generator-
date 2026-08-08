import json
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.main import app
from backend.app.memory.db import get_db
from backend.app.memory.models import Base, PostModel, RejectedTopicModel, utc_now

# Use static pool so in-memory DB persists across requests in tests
TEST_SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    TEST_SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


client = TestClient(app)


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_init_agent_success():
    payload = {
        "persona": {
            "name": "Distill",
            "domain": "AI Research"
        }
    }
    response = client.post("/api/agent/init", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert "agentId" in data
    assert len(data["agentId"]) > 0


def test_init_agent_idempotency():
    payload = {
        "persona": {
            "name": "Distill",
            "domain": "AI Research"
        }
    }
    # First init
    res1 = client.post("/api/agent/init", json=payload)
    assert res1.status_code == 201
    agent_id_1 = res1.json()["agentId"]

    # Second init with exact same persona name & domain
    res2 = client.post("/api/agent/init", json=payload)
    assert res2.status_code == 201
    agent_id_2 = res2.json()["agentId"]

    # Must return the same agentId
    assert agent_id_1 == agent_id_2


def test_get_feed_empty():
    # Init agent first
    init_res = client.post("/api/agent/init", json={"persona": {"name": "Distill", "domain": "AI Research"}})
    agent_id = init_res.json()["agentId"]

    # Get feed
    response = client.get(f"/api/agent/feed?agentId={agent_id}")
    assert response.status_code == 200
    data = response.json()
    assert "posts" in data
    assert data["posts"] == []


def test_get_feed_with_seeded_posts():
    db = TestingSessionLocal()

    # Create agent manually in DB
    init_res = client.post("/api/agent/init", json={"persona": {"name": "Ada", "domain": "AI Security Research"}})
    agent_id = init_res.json()["agentId"]

    # Seed a post into the DB
    post = PostModel(
        agent_id=agent_id,
        text="Another paper claims better reasoning. But the interesting part isn't the benchmark score.",
        rationale="Selected for novel self-critique strategy. Solves benchmark gaming.",
        sources_json=json.dumps(["https://arxiv.org/abs/2401.00000"]),
        topic_title="Self-Critique Reasoning"
    )
    db.add(post)
    db.commit()
    db.refresh(post)
    post_id = post.id
    post_text = post.text
    post_rationale = post.rationale
    db.close()

    # Query feed
    response = client.get(f"/api/agent/feed?agentId={agent_id}")
    assert response.status_code == 200
    data = response.json()
    assert "posts" in data
    assert len(data["posts"]) == 1

    post_item = data["posts"][0]
    assert post_item["id"] == post_id
    assert post_item["text"] == post_text
    assert post_item["rationale"] == post_rationale
    assert post_item["sources"] == ["https://arxiv.org/abs/2401.00000"]
    assert "createdAt" in post_item
    assert "Z" in post_item["createdAt"] or "+" in post_item["createdAt"]


def test_get_status_and_rejected():
    init_res = client.post("/api/agent/init", json={"persona": {"name": "Distill", "domain": "AI Research"}})
    agent_id = init_res.json()["agentId"]

    # Status check
    res_status = client.get("/api/agent/status")
    assert res_status.status_code == 200
    agents = res_status.json()["agents"]
    assert len(agents) == 1
    assert agents[0]["agentId"] == agent_id

    # Rejected check (empty)
    res_rejected = client.get(f"/api/agent/rejected?agentId={agent_id}")
    assert res_rejected.status_code == 200
    assert res_rejected.json()["rejectedTopics"] == []
