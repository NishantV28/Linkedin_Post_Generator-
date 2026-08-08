# Implementation Plan — Autonomous AI Persona Agent

Stack: **FastAPI** (backend) + **LangGraph/LangChain** (agent core) + **SQLite** (relational memory) + **ChromaDB** (vector memory) + **sentence-transformers** (embeddings) + **hybrid (dense + BM25) retrieval** + **React** (frontend).



---

## Phase 1 — Foundations & Contracts

**Goal:** A running FastAPI service with the exact evaluator-facing API contract, backed by real (empty) SQLite tables, plus the persona data model. No agent intelligence yet — everything returns real but static/seeded data.

### Tasks
1. **Project scaffolding**
   - `backend/app/main.py` — FastAPI app, CORS, lifespan stub.
   - `backend/app/core/config.py` — pydantic-settings: DB path, LLM API key, cadence bounds, search API keys.
   - `requirements.txt` (now includes `chromadb`, `sentence-transformers`, `rank_bm25`), `.env.example`, `Dockerfile`.
2. **SQLite schema & models** (`app/memory/models.py`, SQLAlchemy)
   - `agents(id, name, domain, persona_json, created_at, active, next_run_at, cycle_count)`
   - `posts(id, agent_id, text, rationale, sources_json, created_at, topic_title)` — vectors live in Chroma, keyed by this `id`, not in this table.
   - `rejected_topics(id, agent_id, title, source_url, reason, judge_scores_json, created_at)`
   - `cycle_runs(id, agent_id, started_at, finished_at, outcome, candidates_seen)`
   - `app/memory/db.py` — engine/session, `init_db()` called on startup.
3. **Persona schema** (`app/agent/persona/schema.py`)
   - `PersonaConfig`: name, domain, bio, `voice_guidelines` (tone, sentence rhythm, forbidden phrases), `stable_interests` (list), `editorial_thresholds` (min relevance/novelty/credibility scores, 1–10 scale), `posting_cadence_hours` (min,max).
   - 1–2 hardcoded presets in `presets.py` (e.g. "Ada — AI Security Researcher") to use as default when `/init` doesn't fully specify voice/thresholds.
4. **API DTOs** (`app/schemas/agent.py`) matching the spec byte-for-byte:
   - `InitRequest{persona:{name, domain}}` → `InitResponse{agentId}`
   - `FeedResponse{posts:[{id, createdAt, text, rationale, sources}]}`
5. **Routes**
   - `POST /api/agent/init` — validates single-call-per-persona (idempotency guard by name+domain or just reject if `agentId` already active), builds full `PersonaConfig` from preset + overrides, inserts `agents` row, returns `agentId`.
   - `GET /api/agent/feed?agentId=` — pure read from `posts` table, ordered `created_at DESC`, mapped to response shape. **No LLM calls in this path.**
6. **Debug/demo routes** (not part of the graded contract): `GET /api/agent/status`, `GET /api/agent/rejected`.

### Deliverables
- `docker compose up` gives a working API; Postman/curl: init → returns agentId; feed → returns `{"posts": []}`.

### Exit criteria
- API shapes match spec exactly (field names, ISO 8601 `createdAt`, reverse-chronological, empty-array case).
- DB persists across restart (SQLite file on a mounted volume).

---

## Phase 2 — Discovery & Memory Layer

**Goal:** Ability to pull live topic candidates and de-duplicate them against SQLite memory. Testable standalone via a script, no graph/scheduler yet.

### Tasks
1. **Discovery tools** (`app/agent/tools/`)
   - `hn.py` — Hacker News Algolia API, filter by keyword match against `persona.stable_interests`.
   - `arxiv.py` — arXiv Atom API, category filtered by persona domain (cs.CR for security, cs.RO for robotics, cs.AI/cs.CL generally).
   - `github_trending.py` — scrape or use a trending API scoped to AI/ML repos.
   - `web_search.py` — Tavily (or SerpAPI) wrapper, query built from `stable_interests`.
   - Each returns a normalized `TopicCandidate{title, summary, url, source, published_at}`.
2. **Embeddings util** (`app/memory/embeddings.py`)
   - Loads `sentence-transformers/all-MiniLM-L6-v2` once at startup (module-level singleton, avoid reloading per call).
   - `embed(text: str) -> list[float]`, `embed_batch(texts: list[str]) -> list[list[float]]`.
3. **Vector store** (`app/memory/vector_store.py`)
   - `chromadb.PersistentClient(path="./chroma_data")`, one collection per agent (`collection_name = f"agent_{agent_id}"`), or a single collection filtered by `agent_id` metadata.
   - `add(id, text, embedding, metadata={type: "published"|"rejected_dup", agent_id})`.
   - `query_dense(embedding, top_k) -> [(id, distance, metadata)]`.
4. **Sparse index** (`app/memory/sparse_index.py`)
   - `rank_bm25.BM25Okapi` built from tokenized `(title + summary)` of all posts for the agent, loaded fresh from SQLite each cycle (cheap — tens of documents).
   - `query_sparse(query_text, top_k) -> [(id, score)]`.
5. **Hybrid retriever** (`app/memory/hybrid_retriever.py`)
   - `retrieve(query_text, top_k) -> ranked list[id]` — runs dense (Chroma) and sparse (BM25) in parallel, fuses via **Reciprocal Rank Fusion**: `score(id) = Σ 1/(k + rank_in_list)` across both rankers (k≈60, standard RRF constant).
   - `is_duplicate(candidate, threshold) -> bool` — true if the top fused match's dense distance is below threshold *or* its RRF score is a clear outlier vs the rest of the candidate set.
   - `get_relevant_context(agent_id, query_text, top_k)` — used later by the writer node for **topically relevant** past posts, not just chronologically recent ones (style anchors that actually relate to the current topic retrieve better than a plain "last 5").
6. **Memory repository** (`app/memory/repository.py`)
   - `get_recent_posts(agent_id, n)` — for recency-based continuity (used alongside hybrid retrieval, not instead of it).
   - `save_post(...)` — writes SQLite row **and** calls `vector_store.add(...)`.
   - `save_rejection(...)`, `save_cycle_run(...)`.
7. **Standalone test harness** (`scripts/test_discovery.py`)
   - Run discovery + hybrid dedup for a sample persona, print surviving candidates and which retriever (dense/sparse/both) flagged each dropped one — validate before wiring into LangGraph.

### Deliverables
- Script output showing: N raw candidates → M after hybrid dedup, for a real persona, with a per-candidate breakdown of dense vs sparse contribution.

### Exit criteria
- Dedup correctly drops near-duplicate topics across two consecutive manual runs, including a case where two topics are lexically similar but semantically distinct (sparse should NOT flag it) and a case where phrasing differs but meaning is identical (dense should flag it) — confirms hybrid is doing real work, not just dense alone.
- All discovery sources degrade gracefully (one API failing doesn't crash the batch — wrap each source call in try/except, log, continue).
- Chroma and SQLite stay in sync (a post never exists in one without the other) — enforce via a single `save_post` transaction-like helper.

---

## Phase 3 — LangGraph Agentic Core (Editorial Judgment + Voice)

**Goal:** The actual "brain" — a single graph invocation takes a persona + fresh candidates and either produces one well-justified post or produces nothing, with a full paper trail of rejections.

### Tasks
1. **State** (`app/agent/state.py`) — `AgentState` TypedDict as previously designed (persona, candidates, current_candidate, judge_verdict, draft, qa_verdict, rejected_this_cycle, retry_count, published_post).
2. **Editorial judge node + prompt** (`nodes/editorial_judge.py`, `prompts/editorial_judge.py`)
   - Structured output via `with_structured_output(JudgeVerdict)`: `relevance, novelty, credibility, timeliness` (1–10 each) + `decision` + free-text `reasoning`.
   - Prompt includes: persona domain/interests, the candidate, and a short list of recently published titles (anti-repetition context beyond embeddings).
   - Accept only if all sub-scores clear `persona.editorial_thresholds`.
3. **Writer node + prompt** (`nodes/writer.py`, `prompts/writer.py`)
   - Few-shot: **hybrid-retrieved** posts most topically related to the current candidate (`hybrid_retriever.get_relevant_context`), plus the 1–2 most recent posts for recency continuity — better style anchoring than plain chronological recency alone.
   - Input: accepted candidate + judge's reasoning + retrieved context.
   - Output: `DraftPost{text, rationale_selected, rationale_why_now}`.
4. **QA judge node + prompt** (`nodes/qa_judge.py`, `prompts/qa_judge.py`)
   - Structured output: `voice_consistent: bool, factually_grounded: bool, non_repetitive: bool, verdict: pass|revise, feedback: str`.
   - Checks the draft's claims are traceable to the source summary (no hallucinated facts).
5. **Publish node** (`nodes/publish.py`) — embeds final text, writes `posts` row, done.
6. **Rejection logging node** — shared helper called from both judge failure paths, writes `rejected_topics` row with full scoring breakdown.
7. **Graph assembly** (`app/agent/graph.py`)
   - Wire nodes with the conditional edges described earlier (judge reject → next candidate; qa revise → writer retry, max 2; qa fail after retries → next candidate; no candidates left → END with no post).
   - Compile with a `SqliteSaver` checkpointer (same SQLite file) for crash-resilience/replay of in-flight cycles.
8. **Standalone test** (`scripts/test_cycle.py`) — run one full cycle manually against seeded candidates, inspect the rejection log and the published post's rationale/sources for quality.

### Deliverables
- One manually-triggered cycle produces either a persona-voiced post with correct rationale/sources, or a clean "no post this cycle" outcome with logged reasons.

### Exit criteria
- At least one demo run shows a rejected topic with a substantive reason (not just "low score").
- Post `rationale` field genuinely answers "why selected / why now" and lists real source URLs.
- Two consecutive cycles on overlapping topics show dedup/judge correctly avoiding repetition.

---

## Phase 4 — Autonomy & Scheduling

**Goal:** The system runs itself after `/init`, survives restarts, and self-limits to a sane number of posts over the 48h window.

### Tasks
1. **Runner** (`app/core/scheduler.py`) — plain `asyncio` loop, no external scheduling library (APScheduler is more machinery than a single-agent jittered interval needs).
   - `AgentRunner.start()`: `while active and within_48h: await run_cycle(agent_id); agent.next_run_at = now + jitter(cadence_min, cadence_max); await asyncio.sleep(seconds_until(next_run_at))`.
   - `run_cycle` wraps the LangGraph invocation, updates `agents.cycle_count`, and is itself wrapped in try/except so one bad LLM/tool call doesn't kill the loop.
   - Hard stop: loop exits once `now > agent.created_at + 48h`, or `cycle_count >= max_posts` cap; sets `agents.active = false`.
2. **Lifespan wiring** (`app/main.py`)
   - On startup: `init_db()`, then for every `agents.active = true` row, compute `remaining = max(0, next_run_at - now)` from the persisted timestamp and `asyncio.create_task(runner.start(agent_id, initial_delay=remaining))` — this is what makes it resume correctly after a redeploy, since the task itself doesn't survive a restart but the timestamp in SQLite does.
   - On `POST /init`: create agent row with `next_run_at = now + jitter`, `asyncio.create_task(runner.start(agent_id))`.
3. **Idempotency & guardrails**
   - Reject a second `/init` for an agent that's already active.
   - Wrap each cycle in try/except so one bad LLM call doesn't kill the scheduler job.
4. **Ops script** for local testing with a short cadence (e.g. 2–5 minutes instead of hours) via an env override, to soak-test the full loop quickly before switching to real cadence.

### Deliverables
- Start the app, call `/init` once, watch (via `/status` + logs) the scheduler fire on its own and posts accumulate in `/feed` with zero further API calls.
- Kill and restart the process mid-window; confirm scheduling resumes from persisted state, not from zero.

### Exit criteria
- A 30–60 min local soak test (short cadence) produces multiple posts and at least one rejection, unattended.
- Feed endpoint remains correct and read-only throughout.

---

## Phase 5 — Frontend, Integration & Deployment

**Goal:** A demo-ready dashboard, full-stack integration test, and a live deployment that stays up for the 48h evaluation window.

### Tasks
1. **React app** (`frontend/`)
   - `InitAgentForm.tsx` — pick/edit a persona, call `/init`, store `agentId` (localStorage is fine here, it's just a demo client).
   - `useFeedPolling.ts` — polls `/feed` every ~30s.
   - `PersonaHeader.tsx`, `FeedList.tsx` / `PostCard.tsx`, `RationalePanel.tsx` (expand to show why/why-now/sources).
   - `RejectedTopicsPanel.tsx` — hits the debug `/rejected` endpoint, for demoing editorial judgment live.
2. **Integration tests** (`backend/tests/test_api_contract.py`)
   - Exact-shape assertions on `/init` and `/feed` responses (field names, ISO timestamp format, ordering, empty-array case).
   - End-to-end test: init → force-run one cycle synchronously (test-only trigger) → assert feed has 1 post with non-empty rationale/sources.
3. **Deployment**
   - Backend: Railway/Render/Fly.io (or small VPS) with a persistent volume for the SQLite file — must **not** be serverless/sleep-on-idle, since autonomy depends on the process staying alive.
   - Frontend: static hosting (Vercel/Netlify), pointed at the deployed API.
   - Set real cadence (2–5h jittered) and `max_posts` cap for the actual 48h evaluation run.
4. **Final dry run**
   - Init against the deployed instance, monitor for a few hours, confirm posts accumulate, rationale/sources are populated, feed stays correctly ordered and stable across polls.

### Deliverables
- Deployed URL + working `/api/agent/init` and `/api/agent/feed`.
- Frontend dashboard demonstrating persona identity, live feed, rationale, and (bonus) rejected-topics transparency.

### Exit criteria
- Fresh `/init` call on the deployed instance produces posts over real time with zero manual intervention.
- Restarting the deployed service (if the host does that) doesn't lose agent state or duplicate the schedule.

---

## Cross-phase checklist (evaluation criteria mapping)

| Evaluation criterion | Where it's earned |
|---|---|
| Autonomous operation after init | Phase 4 (scheduler + lifespan re-arm) |
| Quality of editorial decision-making | Phase 3 (editorial judge rubric + rejection log) |
| Consistency of persona | Phase 1 (immutable PersonaConfig) + Phase 3 (writer few-shot from own past posts) |
| Effective use of memory | Phase 2 (SQLite + Chroma + hybrid dense/BM25 dedup) + Phase 3 (hybrid-retrieved writer context) |
| Transparency of publishing rationale | Phase 3 (rationale generation) + Phase 1 (API contract) |
| Overall feed quality/coherence | All phases, validated in Phase 5 dry run |
