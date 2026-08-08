# Phase 1 Walkthrough — Autonomous AI Persona Agent (Foundations & Contracts)

This document provides a comprehensive overview of the Phase 1 implementation for the **Autonomous AI Persona Agent** project. It details the project architecture, data models, API endpoints, and step-by-step instructions for running and verifying the Phase 1 service.

---

## 1. Accomplishments & Implemented Architecture

In Phase 1, we established the foundational FastAPI backend service, SQLite memory schema, persona data models, and the exact evaluator-facing API contracts.

```
post_generator/
├── requirements.txt           # Dependency specifications (FastAPI, SQLAlchemy, ChromaDB, etc.)
├── .env.example               # Environment settings & API key templates
├── Dockerfile                 # Container image specification for production deployment
├── implementation.md          # Multi-phase master technical implementation plan
├── persona-distill.md         # Reference document for the 'Distill' AI Research persona
├── walkthrough.md             # Phase 1 completion guide and verification steps
└── backend/
    ├── app/
    │   ├── __init__.py
    │   ├── main.py            # FastAPI entry point, CORS, lifespan startup handler
    │   ├── api/
    │   │   ├── __init__.py
    │   │   └── routes.py      # Core endpoints: /init, /feed, /status, /rejected
    │   ├── agent/
    │   │   ├── __init__.py
    │   │   └── persona/
    │   │       ├── __init__.py
    │   │       ├── schema.py  # PersonaConfig, VoiceGuidelines, EditorialThresholds
    │   │       └── presets.py # Hardcoded persona presets (Distill, Ada)
    │   ├── core/
    │   │   ├── __init__.py
    │   │   └── config.py      # Pydantic Settings for environment configuration
    │   ├── memory/
    │   │   ├── __init__.py
    │   │   ├── db.py          # SQLAlchemy engine, session management, init_db()
    │   │   └── models.py      # SQLite ORM tables (agents, posts, rejected_topics, cycle_runs)
    │   └── schemas/
    │       ├── __init__.py
    │       └── agent.py       # API DTO schemas matching spec byte-for-byte
    └── tests/
        ├── __init__.py
        └── test_phase1.py     # Automated unit & integration tests
```

---

## 2. Key Components Breakdown

### Dependencies & Configuration (`requirements.txt`, `config.py`)
- **Web Framework:** `fastapi`, `uvicorn[standard]`
- **Database & Data Models:** `sqlalchemy` (relational memory), `pydantic-settings`
- **Vector & Search Memory (Phases 2-3 prepared):** `chromadb`, `sentence-transformers`, `rank-bm25`
- **Utilities & Testing:** `httpx`, `python-dotenv`, `pytest`

### SQLite Schema (`backend/app/memory/models.py`)
1. **`agents`**: Persists agent identity (`id`, `name`, `domain`, `persona_json`, `created_at`, `active`, `next_run_at`, `cycle_count`).
2. **`posts`**: Persists published agent feed posts (`id`, `agent_id`, `text`, `rationale`, `sources_json`, `created_at`, `topic_title`).
3. **`rejected_topics`**: Persists audit trail of rejected candidate topics (`id`, `agent_id`, `title`, `source_url`, `reason`, `judge_scores_json`, `created_at`).
4. **`cycle_runs`**: Logs execution cycles (`id`, `agent_id`, `started_at`, `finished_at`, `outcome`, `candidates_seen`).

### Persona Presets (`backend/app/agent/persona/`)
- **`Distill` Preset:** AI Research Translator focusing on arXiv `cs.LG`/`cs.AI`/`cs.CL` papers, filtering out hype words ("groundbreaking", "revolutionary"), with strict editorial thresholds.
- **`Ada` Preset:** AI Security Researcher focusing on model safety, prompt injection defenses, and alignment.

### API Contract (`backend/app/schemas/agent.py` & `backend/app/api/routes.py`)
- **`POST /api/agent/init`**:
  - Request: `{"persona": {"name": "Distill", "domain": "AI Research"}}`
  - Response: `{"agentId": "<uuid>"}`
  - Includes idempotency guard (returns existing active `agentId` if called repeatedly with the same name & domain).
- **`GET /api/agent/feed?agentId=<uuid>`**:
  - Response: `{"posts": [{"id": "...", "createdAt": "2026-08-08T10:00:00Z", "text": "...", "rationale": "...", "sources": [...]}]}`
  - Pure read endpoint sorted by `created_at DESC`. Returns `{"posts": []}` when empty.
- **Debug Endpoints:** `GET /api/agent/status` and `GET /api/agent/rejected`.

---

## 3. How to Run and Verify Phase 1

### Prerequisites
- Python 3.10+ installed
- `pip` package manager

### Option A: Local Python Server

1. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Start the FastAPI Server:**
   ```bash
   python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

3. **Verify Health Endpoint:**
   Access [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health) or run:
   ```bash
   curl http://127.0.0.1:8000/health
   ```
   *Expected Response:* `{"status": "ok", "environment": "development"}`

---

### Option B: Docker Containerization

1. **Build Docker Image:**
   ```bash
   docker build -t autonomous-agent:latest .
   ```

2. **Run Docker Container:**
   ```bash
   docker run -p 8000:8000 --name agent-backend autonomous-agent:latest
   ```

---

## 4. Verification & Testing

### Automated Test Suite Execution
Run the automated pytest test suite covering all contract specs:

```bash
python -m pytest backend/tests/test_phase1.py -v
```

*Output:*
```text
backend/tests/test_phase1.py::test_health_check PASSED
backend/tests/test_phase1.py::test_init_agent_success PASSED
backend/tests/test_phase1.py::test_init_agent_idempotency PASSED
backend/tests/test_phase1.py::test_get_feed_empty PASSED
backend/tests/test_phase1.py::test_get_feed_with_seeded_posts PASSED
backend/tests/test_phase1.py::test_get_status_and_rejected PASSED
======================== 6 passed in 1.06s ========================
```

---

### Manual API Verification Steps

#### Step 1: Initialize Persona Agent (`/api/agent/init`)

**PowerShell Command:**
```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/agent/init" -Method Post -ContentType "application/json" -Body '{"persona": {"name": "Distill", "domain": "AI Research"}}'
```

**cURL Command:**
```bash
curl -X POST "http://127.0.0.1:8000/api/agent/init" \
     -H "Content-Type: application/json" \
     -d '{"persona": {"name": "Distill", "domain": "AI Research"}}'
```

*Expected Response:*
```json
{
  "agentId": "3a8c2f1e-91d4-48b2-b3e1-7d12f9e408a2"
}
```

---

#### Step 2: Fetch Empty Feed (`/api/agent/feed`)

**PowerShell Command:**
```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/agent/feed?agentId=3a8c2f1e-91d4-48b2-b3e1-7d12f9e408a2" -Method Get
```

**cURL Command:**
```bash
curl -X GET "http://127.0.0.1:8000/api/agent/feed?agentId=3a8c2f1e-91d4-48b2-b3e1-7d12f9e408a2"
```

*Expected Response:*
```json
{
  "posts": []
}
```

---

#### Step 3: Check Agent Status (`/api/agent/status`)

```bash
curl -X GET "http://127.0.0.1:8000/api/agent/status"
```

*Expected Response:*
```json
{
  "agents": [
    {
      "agentId": "3a8c2f1e-91d4-48b2-b3e1-7d12f9e408a2",
      "name": "Distill",
      "domain": "AI Research",
      "active": true,
      "createdAt": "2026-08-08T10:46:00Z",
      "nextRunAt": null,
      "cycleCount": 0
    }
  ]
}
```

---

## 5. Next Steps — Transition to Phase 2

With Phase 1 foundations, contracts, and SQLite database models fully operational and verified, we are ready to proceed to **Phase 2 — Discovery & Memory Layer** (Hacker News Algolia, arXiv Atom API, GitHub trending, ChromaDB vector store, BM25 sparse index, and hybrid dense+BM25 Reciprocal Rank Fusion retrieval).
