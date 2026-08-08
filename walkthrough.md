# System Walkthrough & Verification Guide

This document provides a complete, step-by-step guide to configure, run, and manually verify **Phase 1 (Foundations & Contracts)** and **Phase 2 (Discovery & Memory Layer)** of the Autonomous AI Persona Agent project.

---

## 1. Environment Configuration (`.env`)

Before running any script or starting the backend server, copy `.env.example` to `.env` in the project root:

```bash
cp .env.example .env
```

### Environment Variables Breakdown

| Variable | Required for Phase 1 & 2? | Description | Example / Default |
| :--- | :---: | :--- | :--- |
| `DATABASE_URL` | **YES** | SQLite connection string for persistent relational storage | `sqlite:///./post_generator.db` |
| `ENVIRONMENT` | **YES** | Execution environment mode | `development` |
| `LOG_LEVEL` | **YES** | Logging severity level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) | `INFO` |
| `HOST` | **YES** | Host IP binding address for uvicorn server | `0.0.0.0` |
| `PORT` | **YES** | HTTP port for the FastAPI server | `8000` |
| `CADENCE_MIN_HOURS` | **YES** | Minimum autonomous posting interval (in hours) | `2.0` |
| `CADENCE_MAX_HOURS` | **YES** | Maximum autonomous posting interval (in hours) | `5.0` |
| `TAVILY_API_KEY` | ⚠️ **OPTIONAL** | API key for Tavily live web search tool. If omitted, discovery automatically falls back to DuckDuckGo search without failing | `your_tavily_api_key_here` |
| `OPENAI_API_KEY` | ⚠️ **OPTIONAL (Phase 1 & 2)**<br>🔴 **REQUIRED (Phase 3+)** | OpenAI API Key required for Phase 3 LLM Editorial Judge and Post Writer nodes. Not needed to test Phase 1 APIs or Phase 2 discovery & hybrid memory | `your_openai_api_key_here` |

---

## 2. Phase 1 & Phase 2 Implementation Verification Summary

Both **Phase 1** and **Phase 2** are fully built and verified according to the master plan ([implementation.md](file:///c:/Users/Nishant%20Varshney/OneDrive/Desktop/post_generator/Linkedin_Post_Generator-/implementation.md)):

### Phase 1 — Foundations & Contracts Status: **COMPLETE**
- **Scaffolding & Models**: FastAPI app ([backend/app/main.py](file:///c:/Users/Nishant%20Varshney/OneDrive/Desktop/post_generator/Linkedin_Post_Generator-/backend/app/main.py)), Pydantic configuration ([backend/app/core/config.py](file:///c:/Users/Nishant%20Varshney/OneDrive/Desktop/post_generator/Linkedin_Post_Generator-/backend/app/core/config.py)), and SQLAlchemy models ([backend/app/memory/models.py](file:///c:/Users/Nishant%20Varshney/OneDrive/Desktop/post_generator/Linkedin_Post_Generator-/backend/app/memory/models.py)) for `agents`, `posts`, `rejected_topics`, and `cycle_runs`.
- **Persona Data Model**: Persona schemas ([backend/app/agent/persona/schema.py](file:///c:/Users/Nishant%20Varshney/OneDrive/Desktop/post_generator/Linkedin_Post_Generator-/backend/app/agent/persona/schema.py)) and preset profiles for "Distill" and "Ada" ([backend/app/agent/persona/presets.py](file:///c:/Users/Nishant%20Varshney/OneDrive/Desktop/post_generator/Linkedin_Post_Generator-/backend/app/agent/persona/presets.py)).
- **API Contracts & Routes**: Evaluator-facing endpoints implemented in [backend/app/api/routes.py](file:///c:/Users/Nishant%20Varshney/OneDrive/Desktop/post_generator/Linkedin_Post_Generator-/backend/app/api/routes.py):
  - `POST /api/agent/init` (idempotent persona initialization)
  - `GET /api/agent/feed?agentId=` (pure read-only feed, reverse-chronological, ISO 8601 timestamps)
  - `GET /api/agent/status` (agent operational status audit)
  - `GET /api/agent/rejected` (editorial rejection log audit)
  - `GET /health` (service health check)

### Phase 2 — Discovery & Memory Layer Status: **COMPLETE**
- **Multi-Source Discovery Tools**: Integrated scrapers in [backend/app/agent/tools/](file:///c:/Users/Nishant%20Varshney/OneDrive/Desktop/post_generator/Linkedin_Post_Generator-/backend/app/agent/tools/):
  - `hn.py`: Hacker News Algolia REST API scraper
  - `arxiv.py`: arXiv Atom XML API feed parser
  - `github_trending.py`: GitHub Search REST API monitor
  - `web_search.py`: Tavily search wrapper with DuckDuckGo fallback
  - `discovery.py`: Aggregator across all candidate discovery sources
- **Memory Engine**:
  - `embeddings.py`: SentenceTransformers (`all-MiniLM-L6-v2`, 384 dimensions)
  - `vector_store.py`: ChromaDB persistent vector database (`./chroma_data`)
  - `sparse_index.py`: BM25Okapi lexical index wrapper
  - `hybrid_retriever.py`: Hybrid dense + sparse retrieval with Reciprocal Rank Fusion ($k=60$) and deduplication engine
  - `repository.py`: Atomic persistence manager for synchronized SQLite and ChromaDB operations

---

## 3. Step-by-Step Manual Execution & Verification Guide

Follow these steps from scratch to manually test every component.

---

### Step 1: Run the Standalone Discovery & Deduplication Test Harness

This script tests Phase 2 candidate discovery across Hacker News, arXiv, GitHub, and Web search, initializes embeddings, and passes candidates through the Hybrid Dense+BM25 deduplication engine.

#### Command
```bash
python scripts/test_discovery.py
```

#### Expected Output
```text
======================================================================
      AUTONOMOUS AI PERSONA AGENT — PHASE 2 DISCOVERY & DEDUP HARNESS
======================================================================
Loaded existing agent 'Distill' (ID: 3a8c2f1e-91d4-48b2-b3e1-7d12f9e408a2)

[Seeding memory with initial sample post for dedup testing...]

1. RUNNING CANDIDATE DISCOVERY FOR PERSONA 'Distill'...

---> Total Raw Candidates Discovered: 15
  [1] [HN] Another paper claims better reasoning. But the interesting part... (https://news.ycombinator.com/item?id=...)
  [2] [ARXIV] Scalable MatMul-free Language Modeling (cs.CL)... (https://arxiv.org/abs/2406.02528)
  [3] [GITHUB] GitHub: xai-org/grok-1 (48000 stars)... (https://github.com/xai-org/grok-1)
  [4] [WEB] New RLHF alignment strategies for reasoning agents... (https://...)

2. RUNNING HYBRID DENSE + BM25 DEDUPLICATION EVALUATION...
  [ACCEPTED - NOVEL] Source: ARXIV | Title: 'Scalable MatMul-free Language Modeling...'
                     Dense Distance: 0.7241 | RRF Score: 0.0164
  [DROPPED - DUP] Source: HN | Title: 'Self-Critique Reasoning Models...'
                  Reason: Semantic duplicate detected (dense distance 0.2104 <= 0.35)
                  Dense Distance: 0.2104 | RRF Score: 0.0328

======================================================================
                        DISCOVERY & DEDUP SUMMARY
======================================================================
  Raw Candidates Discovered : 15
  Duplicates Dropped        : 1
  Surviving Novel Candidates: 14
======================================================================
```

---

### Step 2: Start the FastAPI Backend Server

Launch the FastAPI web server to serve the API endpoints and auto-initialize the SQLite database.

#### Command
```bash
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```

#### Expected Startup Console Output
```text
INFO:     Started server process [12345]
INFO:     Waiting for application startup.
INFO:     autonomous_agent - Initializing SQLite database tables...
INFO:     autonomous_agent - Database initialization complete.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

---

### Step 3: Verify All REST API Endpoints

While the uvicorn server is running, execute the following commands in a separate terminal (PowerShell or bash/curl) to verify Phase 1 API contracts.

#### 3.1 Health Check (`GET /health`)

##### PowerShell:
```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -Method Get
```
##### bash / cURL:
```bash
curl -X GET "http://127.0.0.1:8000/health"
```

##### Expected JSON Response:
```json
{
  "status": "ok",
  "environment": "development"
}
```

---

#### 3.2 Initialize Persona Agent (`POST /api/agent/init`)

##### PowerShell:
```powershell
$body = @{
    persona = @{
        name = "Distill"
        domain = "AI Research"
    }
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/agent/init" -Method Post -ContentType "application/json" -Body $body
```

##### bash / cURL:
```bash
curl -X POST "http://127.0.0.1:8000/api/agent/init" \
     -H "Content-Type: application/json" \
     -d '{"persona": {"name": "Distill", "domain": "AI Research"}}'
```

##### Expected JSON Response (Status 201 Created):
```json
{
  "agentId": "3a8c2f1e-91d4-48b2-b3e1-7d12f9e408a2"
}
```

*Note: Calling `/init` again with the same name & domain returns the same `agentId` (Idempotent).*

---

#### 3.3 Query Feed Endpoints (`GET /api/agent/feed?agentId=...`)

##### PowerShell:
```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/agent/feed?agentId=3a8c2f1e-91d4-48b2-b3e1-7d12f9e408a2" -Method Get
```

##### bash / cURL:
```bash
curl -X GET "http://127.0.0.1:8000/api/agent/feed?agentId=3a8c2f1e-91d4-48b2-b3e1-7d12f9e408a2"
```

##### Expected JSON Response:
```json
{
  "posts": []
}
```
*(If posts were seeded or published, items are returned in reverse-chronological order with ISO 8601 timestamps, text, rationale, and source URLs).*

---

#### 3.4 Check Agent Status Audit (`GET /api/agent/status`)

##### PowerShell:
```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/agent/status" -Method Get
```

##### bash / cURL:
```bash
curl -X GET "http://127.0.0.1:8000/api/agent/status"
```

##### Expected JSON Response:
```json
{
  "agents": [
    {
      "agentId": "3a8c2f1e-91d4-48b2-b3e1-7d12f9e408a2",
      "name": "Distill",
      "domain": "AI Research",
      "active": true,
      "createdAt": "2026-08-08T10:00:00Z",
      "nextRunAt": null,
      "cycleCount": 0
    }
  ]
}
```

---

#### 3.5 Check Rejected Topics Audit Log (`GET /api/agent/rejected?agentId=...`)

##### PowerShell:
```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/agent/rejected?agentId=3a8c2f1e-91d4-48b2-b3e1-7d12f9e408a2" -Method Get
```

##### bash / cURL:
```bash
curl -X GET "http://127.0.0.1:8000/api/agent/rejected?agentId=3a8c2f1e-91d4-48b2-b3e1-7d12f9e408a2"
```

##### Expected JSON Response:
```json
{
  "rejectedTopics": []
}
```

---

### Step 4: Run Automated Test Suites

Run the complete test suite to automatically validate API schemas, SQLite transaction behavior, sentence embeddings, ChromaDB vector indexing, BM25 sparse search, RRF rank fusion, and deduplication logic.

#### Command
```bash
python -m pytest backend/tests/test_phase1.py backend/tests/test_phase2.py -v
```

#### Expected Output
```text
============================= test session starts =============================
platform win32 -- Python 3.10.9, pytest-9.1.1, pluggy-1.6.0
collected 10 items

backend/tests/test_phase1.py::test_health_check PASSED                  [ 10%]
backend/tests/test_phase1.py::test_init_agent_success PASSED            [ 20%]
backend/tests/test_phase1.py::test_init_agent_idempotency PASSED          [ 30%]
backend/tests/test_phase1.py::test_get_feed_empty PASSED                [ 40%]
backend/tests/test_phase1.py::test_get_feed_with_seeded_posts PASSED    [ 50%]
backend/tests/test_phase1.py::test_get_status_and_rejected PASSED       [ 60%]
backend/tests/test_phase2.py::test_embeddings_generation PASSED         [ 70%]
backend/tests/test_phase2.py::test_vector_store_operations PASSED       [ 80%]
backend/tests/test_phase2.py::test_sparse_bm25_indexing PASSED          [ 90%]
backend/tests/test_phase2.py::test_rrf_fusion_logic PASSED               [100%]

============================= 10 passed in 4.82s ==============================
```

---

## 4. File Structure Reference

```text
Linkedin_Post_Generator-/
├── .env                       # Active environment variables (copied from .env.example)
├── .env.example               # Template for environment settings & API keys
├── Dockerfile                 # Docker build container specification
├── requirements.txt           # Python dependencies (FastAPI, ChromaDB, SentenceTransformers, etc.)
├── implementation.md          # Multi-phase master technical implementation plan
├── persona-distill.md         # Reference specification for "Distill" persona
├── walkthrough.md             # Complete step-by-step verification guide
├── post_generator.db          # Persistent SQLite database file
├── chroma_data/               # Persistent ChromaDB vector database directory
├── scripts/
│   └── test_discovery.py      # Standalone Phase 2 discovery & hybrid dedup test harness
└── backend/
    ├── app/
    │   ├── main.py            # FastAPI entry point & lifespan startup handler
    │   ├── api/
    │   │   └── routes.py      # REST API endpoints (/init, /feed, /status, /rejected, /health)
    │   ├── agent/
    │   │   ├── persona/
    │   │   │   ├── schema.py  # PersonaConfig, VoiceGuidelines, EditorialThresholds DTOs
    │   │   │   └── presets.py # Persona presets ("Distill", "Ada")
    │   │   └── tools/
    │   │       ├── schema.py  # TopicCandidate DTO
    │   │       ├── hn.py      # Hacker News Algolia API scraper
    │   │       ├── arxiv.py   # arXiv Atom XML feed parser
    │   │       ├── github_trending.py # GitHub Search API monitor
    │   │       ├── web_search.py      # Tavily search wrapper + DuckDuckGo fallback
    │   │       └── discovery.py       # Candidate aggregator across all tools
    │   ├── core/
    │   │   └── config.py      # Pydantic Settings environment configuration
    │   ├── memory/
    │   │   ├── db.py          # SQLAlchemy engine, session management, init_db()
    │   │   ├── models.py      # SQLite ORM models (Agent, Post, RejectedTopic, CycleRun)
    │   │   ├── embeddings.py  # SentenceTransformers singleton (all-MiniLM-L6-v2)
    │   │   ├── vector_store.py# ChromaDB PersistentClient vector store wrapper
    │   │   ├── sparse_index.py# BM25Okapi lexical index wrapper
    │   │   ├── hybrid_retriever.py # Reciprocal Rank Fusion (RRF) dense + BM25 retriever & dedup
    │   │   └── repository.py  # Atomic persistence manager for SQLite & ChromaDB
    │   └── schemas/
    │       └── agent.py       # API DTO schemas matching spec byte-for-byte
    └── tests/
        ├── conftest.py        # Pytest path configuration
        ├── test_phase1.py     # Automated Phase 1 API contract test suite
        └── test_phase2.py     # Automated Phase 2 memory & retriever test suite
```
