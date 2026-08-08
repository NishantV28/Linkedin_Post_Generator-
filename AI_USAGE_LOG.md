# AI Usage Log

Record of AI-assisted development for the **Autonomous AI Persona Agent** submission.

Project: autonomous AI/technology persona ("Distill") that discovers topics from live sources, applies editorial judgment, writes in a consistent voice, remembers what it published, and continues publishing over time without human input.

Repository: <https://github.com/NishantV28/Linkedin_Post_Generator->

---

> ### ⚠️ SECTIONS MARKED "TO COMPLETE" MUST BE FILLED IN BEFORE SUBMITTING
>
> Phases 1–5 were built before the review session documented in Part 2. The commit metadata below (hashes, timestamps, files, scope) is taken directly from git history and is accurate. The **AI tool used and the prompts given** for those phases are marked `TO COMPLETE` — only the author can supply them truthfully.
>
> Stage 2 of judging checks that this log "reasonably corresponds to the implemented features" and that prompt history does not appear "incomplete, generic, or unrelated to the submitted project." Invented or generic prompts are worse than none.

---

## Tools used

| Tool | Used for | Phases |
|---|---|---|
| *TO COMPLETE — e.g. Claude Code / Cursor / ChatGPT* | Initial design and phased implementation | 1–5 |
| Claude Code (Claude Opus 5) | Codebase review, defect diagnosis, fixes, verification | Part 2 |

---

# Part 1 — Phased build

Planning document: [implementation.md](implementation.md). Persona design: [persona-distill.md](persona-distill.md).

All five phases were completed on 2026-08-08 between 11:25 and 14:25.

## Phase 1 — Foundations & API contracts

**Commit** `adcd44b` · 11:25 · 25 files, +1253

Built: FastAPI scaffolding with CORS and lifespan; pydantic-settings config; SQLAlchemy models (`agents`, `posts`, `rejected_topics`, `cycle_runs`); `PersonaConfig` schema with voice guidelines, stable interests, editorial thresholds and cadence; two presets (Distill, Ada); API DTOs matching the required contract; `POST /api/agent/init` and `GET /api/agent/feed`; debug `/status` and `/rejected` endpoints.

> **TO COMPLETE — AI usage for this phase**
> - Tool used:
> - Key prompts given:
> - What the AI produced vs. what you wrote or corrected by hand:

## Phase 2 — Discovery & memory layer

**Commit** `fe09ce4` · 12:30 · 19 files, +1320 −122

Built: four live discovery sources (Hacker News Algolia, arXiv Atom, GitHub Search, Tavily with DuckDuckGo fallback) normalising to a shared `TopicCandidate`; sentence-transformers embedding singleton; ChromaDB persistent vector store; BM25 sparse index; hybrid retriever with Reciprocal Rank Fusion; memory repository keeping SQLite and Chroma in sync; standalone discovery test harness.

> **TO COMPLETE — AI usage for this phase**
> - Tool used:
> - Key prompts given:
> - What the AI produced vs. what you wrote or corrected by hand:

## Phase 3 — LangGraph agentic core

**Commit** `db81a77` · 13:26 · 16 files, +1029 −242

Built: `AgentState` schema; editorial judge node scoring relevance/novelty/credibility/timeliness via structured output; writer node with hybrid-retrieved few-shot anchoring; QA judge node checking voice, factual grounding and repetition; publish node; rejection logger; LangGraph assembly with conditional routing and retry logic; single-cycle test harness.

> **TO COMPLETE — AI usage for this phase**
> - Tool used:
> - Key prompts given:
> - What the AI produced vs. what you wrote or corrected by hand:

## Phase 4 — Autonomy & scheduling

**Commit** `e939b97` · 14:07 · 10 files, +609 −168

Built: asyncio scheduler loop with jittered cadence; cycle execution in a thread pool to keep the event loop responsive; persistence of `next_run_at` so scheduling survives restarts; re-arming of active agents on startup; 48-hour window and published-post cap; task registry preventing duplicate loops; graceful shutdown; Phase 4 tests and the operational runbook ([walkthrough.md](walkthrough.md)).

> **TO COMPLETE — AI usage for this phase**
> - Tool used:
> - Key prompts given:
> - What the AI produced vs. what you wrote or corrected by hand:

## Phase 5 — Frontend & integration

**Commit** `5185676` · 14:25 · 10 files, +1931

Built: Vite + React dashboard; persona init form; polling of `/feed`, `/status` and `/rejected`; post cards with expandable rationale and sources; rejected-topics panel demonstrating editorial judgment live.

> **TO COMPLETE — AI usage for this phase**
> - Tool used:
> - Key prompts given:
> - What the AI produced vs. what you wrote or corrected by hand:

---

# Part 2 — Review, defect diagnosis & hardening

**Tool:** Claude Code (Claude Opus 5) · **Date:** 2026-08-08, from ~14:46

An AI-assisted review session against the problem statement. Work products: [FIXES.md](FIXES.md) (prioritised defect and advancement plan) and the fixes below.

### 2.1 Codebase review against the problem statement

**Prompt (paraphrased):** *"This is my problem statement and my current folder shows what I have done till now. Study it and tell me what changes can be done. Don't make any changes, I just want to see for now."*

The full backend, agent graph, memory layer, discovery tools, frontend, tests and docs were read and assessed against the six judging criteria. Findings were recorded in [FIXES.md](FIXES.md), organised as S0 (eligibility), P0 (blocking), P1 (scoring), P2 (robustness) and A (advanced upgrades).

### 2.2 Getting the project running

Two dependencies listed in `requirements.txt` (`sqlalchemy`, `langchain-openai`) were not installed, so nothing could import. `.env` was located in the parent directory, where `config.py` — which reads `.env` relative to the working directory — never loaded it.

### 2.3 Critical defect: structured output unsupported by the configured model

**Symptom:** every LLM call returned HTTP 400; all 22 discovered candidates were "rejected"; zero posts published.

**Diagnosis:** `llama-3.3-70b-versatile`, the default in both `.env` and `llm.py`, does not support Groq's `json_schema` response format, which is what LangChain's `with_structured_output()` sends. The failure was invisible because the editorial judge's exception handler fabricates a rejection verdict on error — so the rejection log filled with API errors formatted as editorial decisions.

**Method:** queried the Groq models endpoint for the account, then empirically tested structured output across candidate models and methods. Both `openai/gpt-oss-120b` with `json_schema` and `llama-3.3-70b-versatile` with `method="function_calling"` succeeded.

**Resolution:** `LLM_MODEL=openai/gpt-oss-120b` (config-only). Impact: without this, the submission would have served an empty feed for the entire 48-hour evaluation window.

### 2.4 Fix P0-2 — retry counter lost in LangGraph routers

**Defect:** `route_after_qa` incremented `retry_count` inside a conditional-edge function. LangGraph rebuilds state for routers, so the mutation was discarded; the guard `retry_count < 2` was permanently true and the writer↔QA loop ran until `GraphRecursionError`. The exception was swallowed by the scheduler, losing the entire cycle whenever QA requested a revision.

**Verification method:** wrote a minimal LangGraph reproduction proving router mutations do not persist, then a stubbed-node test forcing QA to return `revise` on every draft.

**Changes:** increment moved into `writer_node`; rejection logging converted from a router side effect into a `log_rejection` node (`rejected_count` was being lost the same way); `MAX_REVISIONS` constant; recursion limit scaled to candidate count in `scheduler.py`.

**Result:** clean termination at 3 writer calls per topic; `rejected_count` matches actual rejections. Confirmed subsequently in a live run showing `[QA Judge Rejected after revision limit]` and `Topics Rejected: 7` (previously always `0`).

**Secondary finding:** LangGraph's default recursion limit of 25 would have failed on ~8 rejected candidates regardless of retries — a latent bug the retry loop was masking.

### 2.5 Fix P0-3 — deduplication discarding unrelated topics

**Defect:** duplicate detection treated a Reciprocal Rank Fusion score — which is rank-based — as a similarity measure. Anything ranked first in both the dense and sparse lists scored `1/61 + 1/61 = 0.0328`, just over the `0.031` threshold, regardless of actual similarity. In a live run, 13 of 22 candidates were dropped against a single seeded post; every drop scored exactly 0.0328 and every keep exactly 0.0164, while cosine distances ranged 0.62–1.04. The dense threshold never fired.

**Method:** measured `all-MiniLM-L6-v2` cosine distance on labelled pairs before choosing thresholds. This showed dense distance alone cannot work — "same paper, reworded" lands at 0.41–0.49 while "different paper, same subfield" lands at 0.40. Raw token overlap failed likewise (0.400 for a different paper vs 0.364 for the same-paper reword) because shared tokens were generic. The discriminating signal is *rare*-term overlap.

**Changes:** RRF removed from the duplicate decision (retained for ranking in `get_relevant_context`); two calibrated signals — near-identical dense distance, or borderline distance corroborated by IDF-weighted lexical overlap; IDF computed over past posts plus the current candidate batch; decision inputs returned for auditability.

**Result:** 10/10 labelled cases correct, including the decisive pair where the closer item (0.397) is novel and the farther one (0.520) is a duplicate. Live run: 0 of 22 dropped, correctly.

**Note:** the BM25 IDF flooring hack was removed and then restored after two tests failed — on a tiny corpus `BM25Okapi`'s IDF collapses to exactly 0, so removing the floor made sparse retrieval return nothing. Duplicate detection now uses its own IDF, so the floor is harmless there; the code comment records this.

### 2.6 Fixes P2-7 and P2-8 — observability

`MemoryRepository.get_rejected_topics` was called by the test harness but never defined, crashing the script after printing results. Windows consoles default to cp1252 and could not encode the typographic characters in generated posts, raising `UnicodeEncodeError` mid-output. Both fixed so a full cycle prints end to end.

### 2.7 Verification

All 17 existing tests pass after every change. End-to-end live run: 22 candidates discovered → 22 survived dedup → 7 rejected with substantive scored reasoning → 1 published with rationale and sources. Feed contract confirmed: HTTP 200, reverse-chronological, ISO 8601 UTC timestamps, unique ids.

### 2.8 Outstanding work

Recorded in [FIXES.md](FIXES.md), including the persona-voice gap (the writer prompt does not use the persona design document), unenforced editorial thresholds, memory not read by the judges, and deployment hardening.

---

## Human contribution

> **TO COMPLETE.** Judges weigh how the author directed, evaluated and corrected AI output. Worth stating explicitly:
>
> - Persona design and editorial standards — [persona-distill.md](persona-distill.md) is original design work defining voice, beliefs, post structure and rejection criteria
> - Architecture decisions — stack selection, phased plan in [implementation.md](implementation.md)
> - Which AI suggestions were rejected or corrected, and why
> - Testing, review and integration decisions
