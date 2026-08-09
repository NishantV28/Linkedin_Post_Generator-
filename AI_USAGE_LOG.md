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
| Claude Code (Claude Opus 5) | Codebase review, defect diagnosis, fixes, verification, judge/writer refactor, dashboard connection | Part 2 |

## Summary of AI-assisted work

| | |
|---|---|
| Commits in Part 2 | 7 (`31ab818` … `4fd20b0`) |
| Defects found and fixed | 20+, recorded in [FIXES.md](FIXES.md) |
| Automated tests | 23 → **33 passing** |
| Most consequential find | arXiv had never returned a candidate; every post came from forum headlines rather than papers |
| Largest refactor | Editorial judgment split from writing, per the author's specification |

**The recurring defect pattern** was worth naming on its own: something failed, the failure was caught, and the code substituted something that looked normal. A failed API call became an editorial rejection. A broken source became an empty list. A lost counter became "keep retrying". A quality check that errored became an approval. Individually each is a reasonable-looking `try/except`; together they made a system that could fail completely while appearing to work. Most of Part 2 is making failures look like failures.

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

### 2.7 Fix P0-5 — arXiv had never returned a single candidate

**Commit `66b7fdb`.** Distill is an AI-research persona whose primary source is arXiv. The tool requested `http://export.arxiv.org`; arXiv answers plain HTTP with a 301 to HTTPS, and `httpx` does not follow redirects by default. The response body was empty, the non-200 logged a warning nobody read, and the function returned `[]`.

**Every post the agent had written to that point came from Hacker News headlines, GitHub blurbs or scraped web results. Not one came from a paper.** It also explained why almost nothing cleared the editorial bar once thresholds were enforced: a pool of forum threads genuinely cannot reach a research persona's credibility standard.

### 2.8 Editorial standards, memory and persona voice

**Commit `66b7fdb`.**

- **Thresholds enforced in code.** The judge previously returned scores and a decision, and the decision was trusted. A model scoring a candidate below the bar while saying "pass" is now overruled, with the failing dimension recorded in the rejection reason.
- **Memory wired into both judges.** Both were being handed the literal string `"None in memory."`, so the anti-repetition check compared each draft against nothing.
- **Persona voice reached the model for the first time.** The writer prompt opened with "you are a thought leader", the register the persona was explicitly designed against, and `signature_tell` was populated in the presets but referenced nowhere in the codebase.

### 2.9 Cost control and model handling

**Commits `19bd910`, `d4c82a6`.** Groq's free tier allows 200,000 tokens per day. At roughly one editorial call per candidate the agent consumed about 29k per cycle, which forced a switch to a weaker model that **measurably degraded editorial judgment** — on the same Hacker News post, `gpt-oss-120b` scored credibility 5-6 and rejected it while `llama-3.3-70b` scored 8 and published it.

A deterministic pre-filter now drops candidates the persona's own thresholds already exclude before any LLM call: stale, thin-summary, or below the source evidence ceiling, capped per cycle with a per-source share limit. **LLM calls per cycle fell from 27 to 10**, which let the stricter model be restored rather than trading quality for quota.

Measuring it surfaced two further defects: Hacker News was returning stories up to **5,717 days old** (Algolia's relevance search has no date bound), and arXiv fetched too few papers for enough on-topic candidates to survive filtering.

Also added: a fallback model chain, request timeouts, and spacing between calls. Verified across four routing cases — a rate limit skips straight to the fallback without wasting retries, a malformed tool call retries on the same model, and total exhaustion still fails honestly.

### 2.10 Failure handling and self-noticing memory

**Commits `31ab818`, `155a4e4`.**

A rate limit during testing exposed the most dangerous failure mode in the project: **24 consecutive HTTP 429s were each recorded as an editorial rejection with fabricated 1/10 scores.** The feed was empty and the public rejection log was full of API errors that read like editorial decisions. Infrastructure failure is now distinguished from editorial judgment, and the cycle aborts honestly rather than fabricating verdicts.

Memory was extended beyond deduplication: topic spacing defers candidates that echo the previous post, previously rejected URLs are skipped before any LLM call, and the agent occasionally publishes a reflection on a pattern in its own coverage. That pattern is **detected deterministically from post embeddings** rather than asked of the model, since a model asked whether it notices a trend always says yes.

A startup check now proves the configured model can return structured output and reports it on `/health` as `canPublish` — the failure that twice produced an empty feed with no error.

### 2.11 Judge/writer split

**Commit `ad7eb41`.** Implemented against a specification written by the author ([distill_persona_prompt_spec.md](distill_persona_prompt_spec.md)).

The editorial judge now decides what deserves publishing and hands the writer a settled angle: obvious assumption, interesting turn, core claim, mechanism, verified evidence, limitations, why-now and sources. The writer renders that context and no longer reads the raw source or chooses its own angle.

That boundary fixed a defect found by reviewing a published post: a reflection had carried a discovery candidate into its cycle, so QA graded it against an unrelated physics paper, and QA's feedback then steered the writer into rewriting the post about that paper — which published under a "Reflection" title with three unrelated source URLs attached.

Scoring moved to five dimensions on 0-5 with eleven named disqualifiers, enforced in Python. Deterministic voice rules now cover em-dashes, sentence length, parenthetical jargon glosses, appended takeaways, structural scaffolding leaking into prose, and wording copied from the style example.

### 2.12 Dashboard connection

**Commit `ad7eb41`.** A persona gate initialises one agent from a name and domain, and every page binds to that agent. The previous adapter fell back to whichever agent the backend listed first, so the dashboard could display a different persona's feed than the one selected. A stale agent id now clears storage and returns to the gate rather than dead-ending on a 404.

### 2.13 Verification

**33 automated tests pass.** Live runs confirmed: pre-filter reducing 32 candidates to 10, the editorial judge producing specific disqualifiers (`pure_announcement`, `off_topic`, `insufficient_detail`, `opinion_no_evidence`) against real candidates, and the full API contract — HTTP 200, reverse-chronological, ISO 8601 UTC timestamps, unique ids.

**Not verified:** no post has been generated end to end under the final judge/writer split. Every Groq model pool was rate-limited before a cycle reached publication. The architecture is unit-tested and the judge stage is confirmed on live candidates, but the writing itself has not been observed under the final prompt.

### 2.14 Outstanding work

Tracked in [FIXES.md](FIXES.md) with a prioritised order. The two items that gate the submission are the `TO COMPLETE` sections of this document and deployment to an always-on host; everything else affects score rather than eligibility.

---

## Human contribution

> **TO COMPLETE.** Judges weigh how the author directed, evaluated and corrected AI output. Worth stating explicitly:
>
> - Persona design and editorial standards — [persona-distill.md](persona-distill.md) is original design work defining voice, beliefs, post structure and rejection criteria
> - Architecture decisions — stack selection, phased plan in [implementation.md](implementation.md)
> - Which AI suggestions were rejected or corrected, and why
> - Testing, review and integration decisions
