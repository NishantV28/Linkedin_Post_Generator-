# System Walkthrough & Verification Guide

This document provides a complete, step-by-step guide to configure, run, and manually verify **Phase 1 (Foundations & Contracts)**, **Phase 2 (Discovery & Memory Layer)**, and **Phase 3 (LangGraph Agentic Core — Editorial Judgment & Voice)** of the Autonomous AI Persona Agent project.

---

## 1. Environment Configuration (`.env`)

Before running any script or starting the backend server, copy `.env.example` to `.env` in the project root:

```bash
cp .env.example .env
```

### Environment Variables Breakdown

| Variable | Required for Phase 1 & 2? | Required for Phase 3? | Description | Example / Default |
| :--- | :---: | :---: | :--- | :--- |
| `GROQ_API_KEY` | ⚠️ OPTIONAL | ⚡ **RECOMMENDED** | Groq API key (`gsk_...`) for ultra-fast LLM inference (`llama-3.3-70b-versatile`) | `gsk_your_groq_key_here` |
| `OPENAI_API_KEY` | ⚠️ OPTIONAL | 🔴 **REQUIRED (if no Groq key)** | OpenAI API key (`sk-...`) for GPT model execution (`gpt-4o-mini`) | `sk-your_openai_key_here` |
| `LLM_MODEL` | ⚠️ OPTIONAL | ⚠️ OPTIONAL | LLM Model name override (defaults to `llama-3.3-70b-versatile` for Groq, `gpt-4o-mini` for OpenAI) | `llama-3.3-70b-versatile` |
| `TAVILY_API_KEY` | ⚠️ OPTIONAL | ⚠️ OPTIONAL | Tavily live web search key. Automatically falls back to DuckDuckGo if missing | `your_tavily_api_key_here` |
| `DATABASE_URL` | **YES** | **YES** | SQLite database file connection string | `sqlite:///./post_generator.db` |
| `ENVIRONMENT` | **YES** | **YES** | Mode (`development` / `production`) | `development` |
| `LOG_LEVEL` | **YES** | **YES** | Logging severity level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) | `INFO` |
| `HOST` | **YES** | **YES** | Host IP binding for FastAPI uvicorn server | `0.0.0.0` |
| `PORT` | **YES** | **YES** | HTTP server port | `8000` |

---

## 2. Phase 1, Phase 2 & Phase 3 Architecture Summary

All three phases are fully built and verified according to the master plan ([implementation.md](file:///c:/Users/Nishant%20Varshney/OneDrive/Desktop/post_generator/Linkedin_Post_Generator-/implementation.md)):

### Phase 1 — Foundations & Contracts Status: **COMPLETE**
- **Scaffolding & Models**: FastAPI app ([backend/app/main.py](file:///c:/Users/Nishant%20Varshney/OneDrive/Desktop/post_generator/Linkedin_Post_Generator-/backend/app/main.py)), Pydantic settings ([backend/app/core/config.py](file:///c:/Users/Nishant%20Varshney/OneDrive/Desktop/post_generator/Linkedin_Post_Generator-/backend/app/core/config.py)), SQLAlchemy models ([backend/app/memory/models.py](file:///c:/Users/Nishant%20Varshney/OneDrive/Desktop/post_generator/Linkedin_Post_Generator-/backend/app/memory/models.py)).
- **Persona Schemas & Presets**: Data models in [backend/app/agent/persona/schema.py](file:///c:/Users/Nishant%20Varshney/OneDrive/Desktop/post_generator/Linkedin_Post_Generator-/backend/app/agent/persona/schema.py) and presets for "Distill" and "Ada" in [backend/app/agent/persona/presets.py](file:///c:/Users/Nishant%20Varshney/OneDrive/Desktop/post_generator/Linkedin_Post_Generator-/backend/app/agent/persona/presets.py).
- **REST Endpoints**: Evaluator-facing routes in [backend/app/api/routes.py](file:///c:/Users/Nishant%20Varshney/OneDrive/Desktop/post_generator/Linkedin_Post_Generator-/backend/app/api/routes.py) (`/init`, `/feed`, `/status`, `/rejected`, `/health`).

### Phase 2 — Discovery & Memory Layer Status: **COMPLETE**
- **Candidate Discovery**: Hacker News, arXiv XML, GitHub Trending, and Web Search integrated in [backend/app/agent/tools/](file:///c:/Users/Nishant%20Varshney/OneDrive/Desktop/post_generator/Linkedin_Post_Generator-/backend/app/agent/tools/).
- **Hybrid Memory & Deduplication**: Local HuggingFace embeddings (`all-MiniLM-L6-v2`), ChromaDB persistent vector database (`./chroma_data`), BM25 lexical index with stopword filtering (`sparse_index.py`), and RRF rank fusion deduplication engine (`hybrid_retriever.py`).

### Phase 3 — LangGraph Agentic Core Status: **COMPLETE**
- **LLM Factory**: Multi-provider client in [backend/app/agent/llm.py](file:///c:/Users/Nishant%20Varshney/OneDrive/Desktop/post_generator/Linkedin_Post_Generator-/backend/app/agent/llm.py) supporting **Groq API** (`GROQ_API_KEY`) and **OpenAI API** (`OPENAI_API_KEY`).
- **Graph State & Nodes**:
  - `editorial_judge.py`: Evaluates topics against relevance, novelty, credibility, and timeliness thresholds.
  - `writer.py`: Generates persona-voiced posts using few-shot past post style context retrieved via `HybridRetriever`.
  - `qa_judge.py`: Verifies post tone, checks forbidden phrases, and validates factual grounding against candidate summaries.
  - `publish.py`: Persists accepted posts into SQLite relational memory and ChromaDB vector memory.
  - `rejection_logger.py`: Logs full audit scoring breakdowns for rejected topics into `rejected_topics` table.
- **Graph Compilation**: LangGraph state graph in [backend/app/agent/graph.py](file:///c:/Users/Nishant%20Varshney/OneDrive/Desktop/post_generator/Linkedin_Post_Generator-/backend/app/agent/graph.py) with dynamic conditional routing.

---

## 3. Step-by-Step Manual Execution & Verification Guide

Follow these steps from scratch to manually test every phase.

---

### Step 1: Configure Your API Key in `.env`

Add your Groq API key or OpenAI API key to `.env`:

```env
# Add Groq API Key (Recommended)
GROQ_API_KEY=gsk_your_groq_api_key_here

# OR Add OpenAI API Key
# OPENAI_API_KEY=sk-your_openai_api_key_here
```

---

### Step 2: Run Phase 3 LangGraph Cycle Test Harness (Live LLM Generation)

Execute the Phase 3 test harness to discover live candidates, run deduplication, pass candidates through the Editorial Judge LLM, generate drafts with the Post Writer LLM, verify with the QA Judge LLM, and persist published posts:

```bash
python scripts/test_cycle.py
```

#### Expected Output
```text
===========================================================================
       AUTONOMOUS AI PERSONA AGENT — PHASE 3 LANGGRAPH CORE HARNESS
===========================================================================
Using Provider: Groq API | Model: llama-3.3-70b-versatile
Loaded existing agent 'Distill' (ID: 3a8c2f1e-91d4-48b2-b3e1-7d12f9e408a2)

1. DISCOVERING LIVE CANDIDATES FOR PERSONA 'Distill'...
---> Total Raw Candidates Discovered: 15

2. DEDUPLICATING CANDIDATES AGAINST PAST MEMORY...
---> Novel Candidates Ready for Editorial Evaluation: 14

3. EXECUTING LANGGRAPH AGENT CORE (EDITORIAL JUDGE -> WRITER -> QA JUDGE -> PUBLISH)...
2026-08-08 12:45:00 - INFO - Starting cycle with 14 candidate(s). Target [0]: 'Scalable MatMul-free Language Modeling...'
2026-08-08 12:45:02 - INFO - Editorial Judge Verdict for 'Scalable MatMul-free Language Modeling...': PASS (Rel=9, Nov=9, Cred=9)
2026-08-08 12:45:05 - INFO - Writer node generated draft for 'Scalable MatMul-free Language Modeling...' (420 chars)
2026-08-08 12:45:06 - INFO - QA Judge Verdict: PASS (Voice=True, Grounded=True, NonRep=True)
2026-08-08 12:45:07 - INFO - SUCCESS: Published post 'post_a1b2c3d4' for agent '3a8c2f1e' to SQLite + ChromaDB.

===========================================================================
                          CYCLE EXECUTION SUMMARY
===========================================================================
  Cycle Outcome          : PUBLISHED
  Candidates Processed   : 1
  Topics Rejected        : 0

---------------------------------------------------------------------------
                       PUBLISHED POST IN FEED
---------------------------------------------------------------------------
POST ID    : post_a1b2c3d4
TITLE      : Scalable MatMul-free Language Modeling
CREATED AT : 2026-08-08 12:45:07
SOURCES    : ['https://arxiv.org/abs/2406.02528']

POST TEXT  :
Matrix multiplication has dominated neural network architectures for decades.
But a new paper proves we can train billion-parameter language models completely
MatMul-free without sacrificing performance...

PUBLISHING RATIONALE :
Selection Rationale: Selected because removing MatMul hardware constraints is a major architectural breakthrough for efficient inference.
Why Now: Timely research published on arXiv today.
---------------------------------------------------------------------------
```

---

### Step 3: Verify the Live Feed API

Start the FastAPI backend server:

```bash
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```

In a separate terminal, fetch the published post feed for your agent:

#### PowerShell:
```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/agent/feed?agentId=3a8c2f1e-91d4-48b2-b3e1-7d12f9e408a2" -Method Get
```

#### bash / cURL:
```bash
curl -X GET "http://127.0.0.1:8000/api/agent/feed?agentId=3a8c2f1e-91d4-48b2-b3e1-7d12f9e408a2"
```

#### Expected JSON Output:
```json
{
  "posts": [
    {
      "id": "post_a1b2c3d4",
      "createdAt": "2026-08-08T12:45:07Z",
      "text": "Matrix multiplication has dominated neural network architectures for decades...",
      "rationale": "Selection Rationale: Selected because removing MatMul hardware constraints...\nWhy Now: Timely research published on arXiv today.",
      "sources": [
        "https://arxiv.org/abs/2406.02528"
      ]
    }
  ]
}
```

---

### Step 4: Run the Standalone Phase 2 Discovery Harness

```bash
python scripts/test_discovery.py
```

---

### Step 5: Run Full Automated Pytest Test Suite

Execute pytest across all three phases:

```bash
python -m pytest backend/tests/ -v
```

#### Expected Output
```text
============================= test session starts =============================
backend/tests/test_phase1.py::test_health_check PASSED                  [ 10%]
backend/tests/test_phase1.py::test_init_agent_success PASSED            [ 20%]
backend/tests/test_phase1.py::test_init_agent_idempotency PASSED          [ 30%]
backend/tests/test_phase1.py::test_get_feed_empty PASSED                [ 40%]
backend/tests/test_phase1.py::test_get_feed_with_seeded_posts PASSED    [ 50%]
backend/tests/test_phase1.py::test_get_status_and_rejected PASSED       [ 60%]
backend/tests/test_phase2.py::test_embeddings_generation PASSED         [ 70%]
backend/tests/test_phase2.py::test_vector_store_operations PASSED       [ 80%]
backend/tests/test_phase2.py::test_sparse_bm25_indexing PASSED          [ 90%]
backend/tests/test_phase2.py::test_rrf_fusion_logic PASSED               [ 95%]
backend/tests/test_phase2.py::test_hybrid_deduplication PASSED           [ 97%]
backend/tests/test_phase3.py::test_editorial_judge_node_pass PASSED     [ 98%]
backend/tests/test_phase3.py::test_writer_node_generation PASSED        [ 99%]
backend/tests/test_phase3.py::test_qa_judge_node_eval PASSED            [100%]

============================= 14 passed in 8.15s ==============================
```
