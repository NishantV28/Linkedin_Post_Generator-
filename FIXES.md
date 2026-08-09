# Fix & Advancement Plan

**Status as of 2026-08-08:** the pipeline runs end-to-end and publishes a post. Before the model-config fix below it produced **zero** posts while appearing to work normally.

Everything here is grounded in actual local runs: 22 live candidates discovered, rejections with real scoring, posts published, feed contract verified.

**How this document is organised**

| Section | Meaning |
|---|---|
| [S0](#s0--eligibility-passfail-before-any-judging) | Eligibility — pass/fail before judging. Outranks everything. |
| [P0](#p0--blocks-a-valid-submission) | Blocks a valid submission |
| [P1](#p1--directly-costs-judging-points) | Directly costs judging points |
| [P2](#p2--robustness--deployment) | Robustness & deployment |
| [A](#a--advanced-upgrades-scoring-differentiators) | Advanced upgrades — scoring differentiators |

Start at [Suggested order](#suggested-order) for the working sequence.

---

## 0. Environment fixes (applied)

| Change | Detail |
|---|---|
| Installed missing deps | `sqlalchemy`, `langchain-openai` were in `requirements.txt` but not installed — nothing could import |
| `.env` relocated | Was at `post_generator/.env` (parent dir); [config.py](backend/app/core/config.py) reads `.env` relative to CWD, so it was never loaded |
| `LLM_MODEL` switched | `llama-3.3-70b-versatile` → `openai/gpt-oss-120b` (see P0-1) |
| `TAVILY_API_KEY` placeholder cleared | Placeholder string is truthy, so [web_search.py:26](backend/app/agent/tools/web_search.py#L26) burned a failing API call every cycle |

## Changelog

| # | Item | Status | Files touched |
|---|---|---|---|
| P0-2 | Retry counter lost in router | **Done** | `agent/graph.py`, `agent/nodes/writer.py`, `core/scheduler.py` |
| P0-3 | Dedup dropped unrelated topics | **Done** | `memory/hybrid_retriever.py`, `memory/sparse_index.py`, `core/scheduler.py`, `scripts/test_discovery.py` |
| P2-7 | Missing `get_rejected_topics` crashed the harness | **Done** | `memory/repository.py` |
| P2-8 | Console encoding crash hid post text | **Done** | `scripts/*.py` |
| P1-2 | Persona doc never reached the model | **Done** | `persona/schema.py`, `persona/presets.py`, `persona/voice.py`, `prompts/writer.py`, `prompts/qa_judge.py`, `nodes/writer.py`, `nodes/qa_judge.py` |
| P0-5 | **arXiv returned zero candidates all along** | **Done** | `tools/arxiv.py` |
| P0-6 | `.env` cadence was dead config | **Done** | `core/config.py`, `core/scheduler.py`, `api/routes.py` |
| P1-1 | Editorial thresholds never enforced | **Done** | `nodes/editorial_judge.py`, `prompts/editorial_judge.py` |
| P1-3 | Memory never read by the judges | **Done** | `nodes/editorial_judge.py`, `nodes/qa_judge.py` |
| — | Frontend collapsed the persona's closing line | **Done** | `frontend/src/styles.css` |
| P1-6 | QA rejections logged the editorial judge's reasoning | **Done** | `nodes/rejection_logger.py`, `agent/graph.py` |
| P1-4 | Rationale omitted "why over other candidates" | **Done** | `nodes/publish.py`, `agent/state.py`, `agent/graph.py` |
| P1-5 | API failures recorded as editorial rejections | **Done** | `nodes/*.py`, `agent/graph.py`, `agent/state.py` |
| P2-3 | Stale agentId dead-ended the dashboard | **Done** | `frontend/src/App.jsx` |
| — | Case-sensitive init created duplicate agents | **Done** | `api/routes.py` |
| — | Structured-output method hardcoded per model | **Done** | `agent/llm.py` |
| — | Worked example copied verbatim into posts | **Done** | `persona/voice.py`, `nodes/qa_judge.py`, `prompts/writer.py` |
| A-4 | **Candidate pre-filter — 63% fewer LLM calls** | **Done** | `tools/prefilter.py`, `tools/hn.py`, `tools/arxiv.py`, `core/scheduler.py` |
| A-6 | Startup LLM self-check | **Done** | `agent/llm.py`, `main.py` |
| SPEC | **Judge/writer split per `distill_persona_prompt_spec.md`** | **Done** | `persona/schema.py`, `persona/presets.py`, `persona/voice.py`, `agent/state.py`, `prompts/*.py`, `nodes/*.py`, `tests/test_phase3.py` |
| — | LLM fallback chain, timeout, call delay | **Done** | `core/config.py`, `agent/llm.py`, `tools/*.py` |
| A-2 | Memory that changes decisions | **Done** | `memory/repository.py`, `memory/hybrid_retriever.py`, `memory/reflection.py`, `nodes/reflection_writer.py`, `prompts/reflection.py`, `agent/graph.py`, `core/scheduler.py` |

All **22** tests pass after these changes (4 added during this work).

**A full cycle now runs and prints end-to-end**: 27 candidates discovered (22 before the arXiv fix) → rejected with real scored reasoning → published with post text, rationale, sources, and the rejection audit log all visible.

---

## S0 — Eligibility (pass/fail, before any judging)

Stage 1 is automated and binary. Failing any item here means the project is never scored, regardless of quality.

### S0-1. 🚨 No AI Usage Log

The rules require it: *"AI Usage Log must be included and accessible."* **No such file exists in this repo.** Stage 2 additionally checks that the log "reasonably corresponds to the implemented features" and that prompt history does not appear "incomplete, generic, or unrelated to the submitted project" — so it must reflect the actual phases built, not a generic summary.

Cheapest possible point to lose. Roughly 30 minutes of work.

- [x] Created [AI_USAGE_LOG.md](AI_USAGE_LOG.md) at the repo root
- [x] Linked from the README
- [ ] **Fill in the `TO COMPLETE` sections** — the AI tool and prompts used for Phases 1–5, and the human-contribution section

> The log's commit metadata (hashes, timestamps, files, scope) is taken from git history and is accurate. Part 2 (review and fixes) is documented in full. **Phases 1–5 carry `TO COMPLETE` placeholders for the tool and prompts used, because only the author can supply those truthfully** — and Stage 2 penalises prompt history that looks "generic or unrelated to the submitted project", so invented entries are worse than none.

### S0-2. 🚨 No live demo URL

Also Stage 1 pass/fail: *"Live Demo URL must be functional and return a working application."* It must stay up for the whole ~48h observation window.

Constraints that rule out most free tiers (see [P2-6](#p2-6-deployment)): torch + Chroma memory footprint, a process that must never sleep, and a persistent volume for SQLite + `chroma_data`.

- [ ] Deploy backend to an always-on host with a persistent volume
- [ ] Deploy frontend, pointed at the deployed API
- [ ] Verify `/api/agent/init` and `/api/agent/feed` from outside the network

### S0-3. Commit history authenticity

Stage 2 flags "little or no development activity during the hackathon, followed by a large final commit." Current history is 5 clean phased commits — good. Keep committing incrementally as fixes land rather than squashing everything into one final push.

- [ ] Commit each fix separately as it is completed

> ⚠️ **`LLM_MODEL` is only set in the local `.env`.** It is not in `.env.example`, and it is the difference between a working agent and a silent one. Any deployment without `openai/gpt-oss-120b` (or the `method="function_calling"` change) returns to zero posts with no visible error. See [P0-1](#p0-1-structured-output-fails-on-the-default-model--mitigated).

---

## P0 — Blocks a valid submission

### P0-1. Structured output fails on the default model ✅ mitigated

**Problem.** `llama-3.3-70b-versatile` does not support Groq's `json_schema` response format, which is what `with_structured_output()` sends. Every LLM call returned `400 Bad Request`.

**Why it was invisible.** [editorial_judge.py:64-72](backend/app/agent/nodes/editorial_judge.py#L64-L72) catches the error and fabricates a rejection verdict with all scores = 1. The logs read like normal editorial activity; `rejected_topics` filled with API errors formatted as editorial decisions.

**Impact.** Zero posts for the entire 48h evaluation window, with no obvious symptom.

**Fix (choose one):**
- Config only — `LLM_MODEL=openai/gpt-oss-120b` *(applied)*
- Code — `llm.with_structured_output(JudgeVerdict, method="function_calling")` to keep llama-3.3-70b

**Hardening (still to do):** validate the model at startup with one throwaway structured call, and fail loudly rather than degrading into fake rejections.

- [x] Add startup model validation — see [A-6](#a-6-autonomy-robustness)
- [x] Stop writing runtime errors into `rejected_topics` — done via [P1-5](#p1-5-llm-failures-publish-garbage-instead-of-skipping--done); the cycle now aborts with an `aborted_error` outcome instead

---

### P0-2. Retry counter never increments → cycles die silently ✅ DONE

**Location.** [graph.py:75-78](backend/app/agent/graph.py#L75-L78)

**Problem.** `route_after_qa` mutates `state["retry_count"]` inside a conditional-edge function. LangGraph builds a fresh state dict for routers; mutations there are never written back to channels. Verified empirically — a router that mutates state loops until `GraphRecursionError`.

**Impact.** Every time QA returns `revise`, the graph ping-pongs writer → qa → writer until the recursion limit (25), burning ~12 LLM round-trips, then throws. The exception is swallowed in [scheduler.py:106](backend/app/core/scheduler.py#L106) and the cycle ends with **no post and no rejection record**.

**Confirmed live.** The cycle summary printed `Topics Rejected: 0` while SQLite held 3 rejections — same mechanism, via `rejected_count` in [rejection_logger.py:41](backend/app/agent/nodes/rejection_logger.py#L41).

**Fix applied.** Routers are now pure — they read state and return a node name, nothing else.

- [x] **`retry_count` moved into `writer_node`** ([writer.py:28-32](backend/app/agent/nodes/writer.py#L28-L32)) — guarded on the incoming `qa_verdict` being `revise`, so the first draft isn't miscounted as a retry. Also normalised the `.lower()` comparison on [line 60](backend/app/agent/nodes/writer.py#L60), which gates the revision feedback the retry depends on.
- [x] **Rejection logging is now a node**, not a router side effect. Rather than patching only the retry counter, both routers' `log_candidate_rejection(state)` calls were replaced by a `log_rejection` node, since `rejected_count` was being lost the same way. The node infers which judge rejected from `qa_verdict`, so no new state field was needed. `MAX_REVISIONS = 2` replaces the bare literal.
- [x] **Recursion limit scales with candidate count** ([scheduler.py:97-101](backend/app/core/scheduler.py#L97-L101)) — `max(50, 8 × candidates)`.

**Flow after the change:**

```
editorial_judge ─┬─ pass ──→ writer
                 └─ reject → log_rejection → advance_candidate

qa_judge ─┬─ pass ─────────────────→ publish
          ├─ revise (retries left) → writer
          └─ otherwise ───────────→ log_rejection → advance_candidate
```

> **Latent bug this exposed.** LangGraph's default recursion limit is 25, and each rejected candidate costs ~3 steps (judge → log_rejection → advance). A cycle would therefore have thrown after roughly the 8th rejected topic — and live runs discover 22 candidates. The infinite retry loop was masking this; once retries terminated correctly, cycles ran longer and would have started failing on candidate volume alone.

**Verified.** LLM nodes stubbed, QA forced to `revise` on every draft — the exact input that used to hang:

| | Before | After |
|---|---|---|
| Outcome | `GraphRecursionError` | `all_rejected`, clean exit |
| Writer calls | ~12 then crash | 3 per topic (1 draft + 2 revisions) |
| `rejected_count` in state | 0 | 3 |
| Actual rejections logged | 0 | 3 |

---

### P0-3. Dedup drops unrelated topics → feed goes silent ✅ DONE

**Location.** [hybrid_retriever.py:102](backend/app/memory/hybrid_retriever.py#L102)

**Problem.** `if top_rrf_score > 0.031` treats a *rank*-based score as a *similarity* score. RRF gives `1/(60+1) + 1/(60+1) = 0.0328` to anything ranked #1 in both the dense and sparse lists — regardless of how similar it actually is. The threshold sits just under that, so "ranked first in both lists" alone means "duplicate."

**Confirmed live.** Against a single seeded post, 13 of 22 candidates were dropped:

| Dropped candidate | Dense distance | RRF |
|---|---|---|
| "Gnosis Explains The Method Behind Gawker Media Hack" | 0.8555 | 0.0328 |
| "GitHub: Sudharsanselvaraj/Token-Print" | 0.9814 | 0.0328 |
| *(all 13 dropped)* | 0.62 – 0.98 | **0.0328** |
| *(all 9 accepted)* | 0.65 – 1.04 | **0.0164** |

Every drop scored exactly 0.0328, every keep exactly 0.0164. The cosine threshold of 0.35 **never fires** — real distances are 0.6–1.0. The only thing deciding "duplicate" is whether BM25 returned any hit at all.

**Impact.** Compounds over 48h: more posts → more BM25 hits → nearly everything reads as duplicate → feed stalls.

**Calibration.** Measured `all-MiniLM-L6-v2` cosine distance on labelled pairs before choosing any threshold:

| Distance | Relationship |
|---|---|
| 0.00 | identical text |
| 0.41 – 0.49 | same paper, reworded |
| **0.40** | **different paper, same subfield** |
| 0.63 – 0.86 | different AI topic |
| 0.90+ | unrelated |

**Dense distance alone cannot work.** "Same paper reworded" (0.41–0.49) and "different paper, same subfield" (0.40) overlap — the *different* paper is closer than the reworded duplicate. No single threshold separates them.

Raw token overlap fails for the same reason: a different paper scored 0.400 overlap versus 0.364 for the same-paper reword, because the shared tokens were all generic ("language", "large", "model", "open"). The distinguishing signal is the **rare** token — "baichuan".

**Fix applied** ([hybrid_retriever.py](backend/app/memory/hybrid_retriever.py)):

- [x] **RRF removed from the duplicate decision entirely.** It ranks; it does not judge. It remains in `get_relevant_context`, where ranking is the actual job, so hybrid retrieval still backs the writer's few-shot context.
- [x] **Two independent signals, calibrated:**
  - `DENSE_NEAR_IDENTICAL = 0.25` — semantics alone are enough
  - `DENSE_BORDERLINE = 0.55` + `LEXICAL_CORROBORATION = 0.40` — a merely-similar item must *also* share the candidate's distinctive vocabulary
- [x] **IDF-weighted lexical overlap** (`_idf_weights` / `_weighted_overlap`) measures the share of the candidate's *rare* terms already covered by a past post. Sharing "model" barely registers; sharing "baichuan" decides it.
- [x] **IDF corpus widened** — [scheduler.py](backend/app/core/scheduler.py) passes the cycle's candidate batch via `corpus_texts`, so terms common across the batch are correctly treated as generic. Past posts alone are too few to estimate IDF.
- [x] **Decision inputs are logged** — the returned `scores` dict carries `dense_distance`, `lexical_overlap`, and both match ids; reason strings quote the numbers and surface in `/api/agent/rejected`.

> **The IDF flooring hack in [sparse_index.py](backend/app/memory/sparse_index.py) was restored after removal broke tests.** It exists for a real reason: on a tiny corpus `BM25Okapi`'s IDF collapses to exactly `0`, and `query_sparse` filters on `> 0`, so removing the floor made sparse retrieval return nothing at all. It does flatten the rare/common distinction — which is precisely why duplicate detection now uses its own IDF instead of BM25 scores. Comment updated to record this.

**Verified**, 10/10 labelled cases correct. The two rows that matter:

| Candidate | Distance | Lexical | Verdict |
|---|---|---|---|
| Qwen 3 — *different* paper | 0.397 | 0.28 | **NOVEL** ✓ |
| Baichuan 2, other source — *same* paper | 0.520 | 0.47 | **DUPLICATE** ✓ |

The closer item is novel and the farther one is a duplicate. Only the rare-term signal separates them.

**Live run:** against the same seeded post that previously caused 13 of 22 candidates to be dropped, **0 of 22** are now dropped — none of them was ever a duplicate.

---

### P0-5. arXiv returned zero candidates all along ✅ DONE

**The most consequential defect found so far.** Distill is an AI-research persona whose primary source is arXiv. [arxiv.py](backend/app/agent/tools/arxiv.py) requested `http://export.arxiv.org/api/query`; arXiv answers plain HTTP with a **301 redirect to https**, and `httpx` does not follow redirects by default. The response body was empty, `status_code != 200` logged a warning nobody read, and the function returned `[]`.

**Every post the agent had ever written came from Hacker News headlines, GitHub repo blurbs, or scraped web results.** Not one came from a paper.

This also explains why almost nothing cleared the editorial bar once thresholds were enforced ([P1-1](#p1-1-editorial-thresholds-are-never-enforced-in-code--done)): a pool of Ask HN threads and 59-star repos genuinely cannot reach Distill's `credibility >= 8.0`. The judge was right; the pool was empty of anything worth publishing.

- [x] `https://` scheme, plus `follow_redirects=True` as belt and braces

**Result:** 5 arXiv candidates per cycle, published within the last 2 days, each with a ~500-character abstract — which also fixes the thin-summary problem for the highest-quality candidates. The very next cycle published a genuine paper.

---

### P0-6. `.env` cadence was dead config ✅ DONE *(doc update outstanding)*

`POST /api/agent/init` scheduled from `persona_config.posting_cadence_hours` (2.5-4.5 h for Distill). `CADENCE_MIN_HOURS` / `CADENCE_MAX_HOURS` were only a `.get()` fallback in the scheduler loop — and since `persona_json` always contains a cadence, **the fallback could never fire**. The env vars did nothing, while [walkthrough.md](walkthrough.md) instructed users to set them.

Rather than editing the preset (cadence is part of the persona's identity — the persona doc specifies "roughly every 3 hours"), added an explicit override with defined precedence:

**env override → persona cadence → global fallback**

- [x] `CADENCE_OVERRIDE_MIN_HOURS` / `CADENCE_OVERRIDE_MAX_HOURS` in config
- [x] `resolve_cadence()` in `scheduler.py`, used by both `/init` and the loop
- [x] All three precedence paths verified
- [ ] Update [walkthrough.md](walkthrough.md) §3 and §7, which still document the old dead behaviour

> **Before the real 48h run, comment out both `CADENCE_OVERRIDE_*` lines.** Distill then posts on its own 2.5-4.5 h rhythm with no other change.

---

### P0-4. Stale content published as news ✅ DONE

**Confirmed live.** The published post covers `arXiv:2309.10305` (Baichuan 2) — a **September 2023** paper — and its rationale claims *"Baichuan 2 arrives while reproducibility and independent evaluation are hot concerns, making its release timely."* Presenting a three-year-old paper as current news is immediately visible to a judge.

**Root cause.** [hn.py:30-34](backend/app/agent/tools/hn.py#L30-L34) queries Algolia's relevance-sorted `/search` with no date filter, so it returns stories from any year.

**Fixed in three places, each closing a different route to stale content:**

- [x] **`min_timeliness` enforced in code** ([P1-1](#p1-1-editorial-thresholds-are-never-enforced-in-code--done)) — the Baichuan paper now scores 3/10 and is rejected automatically
- [x] **HN recency window** — `numericFilters=created_at_i>` over 21 days. Live runs had been surfacing stories **140, 1046, 2404 and 5717 days old**; HN went from 15 stale candidates to 5 current ones
- [x] **Global age cutoff before any LLM call** — the pre-filter ([A-4](#a-4-editorial-decision-quality--pre-filter--done)) drops anything older than 30 days, so stale items never reach the judge at all

---

## P1 — Directly costs judging points

### P1-1. Editorial thresholds are never enforced in code ✅ DONE

**Location.** [editorial_judge.py](backend/app/agent/nodes/editorial_judge.py), [prompts/editorial_judge.py:20](backend/app/agent/prompts/editorial_judge.py#L20)

The node trusts the LLM's `decision` string and never compares returned scores against `persona.editorial_thresholds`. `min_timeliness` isn't even mentioned in the prompt's decision rule.

**Fix.** After the LLM call, gate programmatically:

```python
t = persona.editorial_thresholds
passes = (verdict.relevance >= t.min_relevance and verdict.novelty >= t.min_novelty
          and verdict.credibility >= t.min_credibility and verdict.timeliness >= t.min_timeliness)
verdict.decision = "pass" if passes else "reject"
```

**Fix applied.**

- [x] **Programmatic gate** in `editorial_judge_node`: all four scores are checked against the persona's thresholds, and a model `pass` below the bar is overruled. The reason string records which dimension failed, e.g. *"[Below Distill's publishing bar: timeliness 3 < 6.5.]"*
- [x] **`min_timeliness` added to the prompt**, with instructions to judge against the publication date rather than how modern the subject sounds — plus a note that scores are checked programmatically, so inflating them to force a decision achieves nothing.

**Verified** with 4 parametrised tests covering: all-clear passes, stale content, weak source, and off-topic — each asserting an approving model verdict is overruled when a threshold fails.

**Effect on stale content** (this is [P0-4](#p0-4-stale-content-published-as-news--largely-resolved-by-p1-1) in practice): the September 2023 Baichuan paper, previously *published as news*, now scores `Time=3` and is rejected automatically. Across a live cycle, most stale HN items were rejected on timeliness alone.

---

### P1-2. The persona doc never reaches the model ✅ DONE

This is the biggest gap between what was designed and what the judges read.

**Confirmed live.** Generated post:

> Just saw the Baichuan 2 paper. It's an open large-scale transformer language model. The authors publish the model weights and training code. […] It adds another openly available big model to the ecosystem, which helps keep research reproducible and accessible.

Against the template in [persona-distill.md:37-41](persona-distill.md#L37-L41):

> Another paper claims better reasoning. **But** the interesting part isn't the benchmark score. It's the training strategy […] *That's the part worth paying attention to.*

The output has no obvious-claim setup, no contrarian turn, no "what does this actually change," and no standalone takeaway line. It ends on exactly the filler the persona doc says to stop before writing.

**Root causes in [prompts/writer.py](backend/app/agent/prompts/writer.py):**
- Opens with `"You are {name}, a thought leader in {domain}"` — the LinkedIn-guru register the persona is explicitly defined against
- `voice_guidelines.signature_tell` is populated in both presets and **referenced nowhere in the codebase**
- The 4-part structure, the worked example, and the core question ("what does this paper actually change?") are absent
- `stable_interests` is not passed

**Fix applied.** The persona doc now drives the code instead of sitting beside it.

- [x] **Structure moved into the persona schema, not the prompt template.** `VoiceGuidelines` gained `core_question`, `post_structure`, `worked_example` and `requires_standalone_closing_line`. Hardcoding Distill's beats into the shared template would have broken Ada; both presets now carry their own, taken verbatim from [persona-distill.md](persona-distill.md).
- [x] **`WRITER_SYSTEM_PROMPT` rewritten** around the core question, the ordered beats, and the worked example. "Thought leader" framing removed — it was the exact register the persona is defined against.
- [x] **`signature_tell` and `stable_interests` now passed** — `signature_tell` was populated in both presets and referenced nowhere in the codebase.
- [x] **Explicit anti-filler rules** derived from observed failures: no narrating the reading process ("Just saw…"), no call to action, no "what the community needs", no sentence that would be equally true of a different paper.
- [x] **QA judge given the same standards** — it previously checked only tone and forbidden words, so `voice_consistent` could not detect a structural failure.
- [x] **Programmatic structure check** in `qa_judge_node`, overriding the LLM verdict, alongside the existing forbidden-phrase check.

> **Deterministic formatting is repaired, not re-prompted.** The first live run after this change produced **0 posts / 22 rejections**. Diagnosis: the writing was already correct — all four beats, a real takeaway — but the closing line was separated by `\n` instead of `\n\n`, so the structure check failed and burned both revision rounds on a formatting slip.
>
> Rather than relaxing the check or hoping the model complies, `ensure_closing_line_separation` in the new [persona/voice.py](backend/app/agent/persona/voice.py) promotes a short trailing line into its own block before QA sees it. It only fires when the final line is already short enough to be a takeaway — a long rambling final paragraph is a genuine structural failure and still fails QA. The prompt also now states the blank-line requirement explicitly.

**Result** — same topic, before and after:

| | Post text |
|---|---|
| **Before** | "Just saw a Hacker News post about a new QCMP framework… No hype here—just a concrete methodological proposal. If you work on agent robustness, worth a skim. The community needs more work on this front, and QCMP adds a fresh perspective." |
| **After** | "The paper claims to make AI agents more robust.<br>But the interesting part isn't the robustness claim itself.<br>It introduces a QCMP framework that treats poisoning as a design constraint and builds resistance directly into the agent's training and inference pipeline.<br><br>*QCMP reframes poison resistance as a built-in system property.*" |

Live cycle: 1 published / 7 rejected. Tests: 18 passing, including a new one asserting that a structure violation overrides an approving LLM verdict.

**Still open from this area** (tracked in [A-1](#a-1-persona-consistency-weakest-area-highest-scoring-impact)): the style-drift guard.

---

### P1-3. Memory is written but never read by the judges ✅ DONE

`recent_post_titles` in [editorial_judge.py:47](backend/app/agent/nodes/editorial_judge.py#L47) and `recent_posts` in [qa_judge.py:39](backend/app/agent/nodes/qa_judge.py#L39) are both hardcoded to `"None in memory."`

So the QA `non_repetitive` check is a no-op and the editorial judge has zero anti-repetition context. `MemoryRepository.get_recent_posts` exists and is **never called anywhere**.

This is the single biggest gap against the "effective use of memory" criterion — the plumbing is built, just not connected.

- [x] **`get_recent_posts` wired into the editorial judge** — last 8 published titles, with an explicit instruction to reject anything covering the same ground under a different headline. Catches repeats the embeddings miss.
- [x] **Recent post bodies wired into the QA judge** — the `non_repetitive` check now has something to compare against instead of the literal string `"None in memory."`
- [x] Both loaders fail soft: a memory error logs and degrades, it never blocks judging
- [x] Callbacks and self-noticing — delivered under [A-2](#a-2-memory-that-changes-decisions-not-just-dedup--done)

---

### P1-6. QA rejections log the *editorial* judge's reasoning ✅ DONE

**Found in a live run after the P0-2 fix.** [rejection_logger.py:19](backend/app/agent/nodes/rejection_logger.py#L19) always builds its reason from `judge_verdict.reasoning`, regardless of which stage rejected the topic. So a QA rejection is recorded with the editorial judge's text — which, for an item that *passed* editorial review, ends in "...leading to a pass":

```
Title : 'Baichuan 2: Open Large-Scale Language Models...'
Reason: [QA Judge Rejected after revision limit] ...its recent release keeps it
        timely enough for current analysis, leading to a pass.
Scores: {"relevance": 8, "novelty": 7, "credibility": 9, "decision": "pass"}
```

A rejection labelled "rejected" that reads "leading to a pass", with `"decision": "pass"` in its scores. This is served publicly by `/api/agent/rejected` and is exactly what an evaluator inspecting editorial judgment would read.

**Fix.** When `qa_verdict` indicates the rejection, use `qa_verdict.feedback` as the reason and record the QA booleans alongside (or instead of) the editorial scores.

- [x] **The rejecting stage's own reasoning is used.** Stage detection moved into `_describe_rejection`, so the logic lives in one place instead of being duplicated between the graph router and the logger.
- [x] **QA verdict fields recorded** in `judge_scores` (`stage`, `voice_consistent`, `factually_grounded`, `non_repetitive`), with the editorial scores preserved under `editorial_scores`.

**Verified** — the same Baichuan case that previously read *"...leading to a pass"* under a rejection heading now reads *"Draft reads as a flat summary and does not answer what the paper changes."*

> This bug blocked diagnosis twice during development: with QA feedback invisible, every QA-stage failure needed a separate debug script to investigate.

---

### P1-4. Rationale omits "why over other candidates" ✅ DONE

The brief's example rationale explicitly includes *"why it was chosen over other candidates."* Currently [publish.py:21](backend/app/agent/nodes/publish.py#L21) emits only selection + why-now.

The data already exists — the rejections logged during that same cycle. Adding a third line naming passed-over candidates scores directly on transparency, and matches the "showing its work" behavior in the persona doc.

- [x] **Rejections threaded into the published rationale.** `rejected_this_cycle` accumulates on the state as candidates are rejected, and `publish_node` builds a third `Chosen Over:` section citing up to 3 by name with the reason each was passed over.

Example as served by `/api/agent/feed`:

```
Selection Rationale: Fits reasoning interests.
Why Now: Released 2026-08-06.
Chosen Over: 2 other candidate(s) were evaluated and rejected this cycle.
  - An off-topic HN thread about career advice - Career discussion, not research
  - Baichuan 2: Open Large-Scale Language Models - Draft reads as a flat summary...
```

The claim is backed by real decisions rather than asserted, which is what the brief's example rationale asks for.

---

### P1-5. LLM failures publish garbage instead of skipping ✅ DONE

> **This failure happened for real during development, which is why it was pulled forward.** Groq's free tier has a **200,000 tokens-per-day** cap. Repeated full-cycle test runs exhausted it. The result: 3 candidates were genuinely judged, then **24 consecutive HTTP 429s were each recorded as an editorial rejection with fabricated `1,1,1,1` scores**. The feed was empty and `/api/agent/rejected` was full of API errors that read like editorial decisions.
>
> During a 48-hour evaluation this would have been fatal and invisible.

**Fix applied.** Infrastructure failure is now distinguished from editorial judgment via a `node_error` field on the state.

- [x] **Editorial judge** no longer fabricates a `1,1,1,1` rejection verdict
- [x] **Writer** no longer emits an off-voice template draft
- [x] **QA judge** no longer auto-*passes* an unreviewed draft — that inverted the purpose of a quality gate
- [x] **The cycle aborts** on `node_error` via a new `abort_cycle` node. A rate limit will hit every remaining candidate too, so continuing only burns quota and pollutes the log. The scheduler records `aborted_error: ...` and retries next cycle.

**Verified** with a simulated 429 across 27 candidates:

| | Before | After |
|---|---|---|
| LLM calls attempted | 27 | **1** |
| Fake editorial rejections logged | 27 | **0** |
| Cycle outcome | looked like normal rejections | `aborted_error: ... 429 ... (TPD)` |

> ### ⚠️ Token budget for the real run
> The 200k/day cap is a live constraint, not a test artifact. One cycle costs roughly one editorial call per candidate (~27) plus writer and QA calls. Before the 48-hour run, the [A-4](#a-4-editorial-decision-quality--pre-filter--done) pre-filter now cuts this to ~12k tokens/cycle — dropping stale and low-credibility candidates before the LLM sees them is the single biggest saving — and consider a paid tier or a second provider key.

---

## P2 — Robustness & deployment

### P2-1. Discovery quality

- **Repeated queries.** [github_trending.py:24](backend/app/agent/tools/github_trending.py#L24) and [web_search.py:24](backend/app/agent/tools/web_search.py#L24) always use `stable_interests[0]`, so every cycle issues an identical query and returns near-identical candidates that dedup then discards. Rotate the keyword by cycle number.
- **Thin summaries.** HN candidates carry `"{title}. Points: N, Comments: M"` as their entire summary — the judge and writer have nothing but a headline to reason about, which is how hallucinations get in. Fetch the linked page or the HN discussion text.
- **Low-quality GitHub results.** The live run surfaced unrelated 59–212 star repos. Raise the star floor and constrain by topic.
- **Web search returns non-articles.** The query in [web_search.py:24](backend/app/agent/tools/web_search.py#L24) is `"latest {keyword} research breakthrough"`, and a live run returned *"latest, late, latests — WordWeb dictionary definition"*, *"CBS News | Breaking news"*, and *"ABC News"*. The leading word "latest" is dominating the match. Drop it and query the interest term directly.
- **Rejections aren't remembered.** Rejected topics never enter the vector store, so the same item is re-discovered and re-judged at full LLM cost every cycle for 48h.

- [x] **Skip previously rejected items pre-LLM** — `MemoryRepository.get_rejected_urls` ([A-2](#a-2-memory-that-changes-decisions-not-just-dedup--done)). Kept in SQLite rather than the vector store: an exact URL match is the right test here, and it needs no embedding call.
- [x] **HN recency window** — also closes [P0-4](#p0-4-stale-content-published-as-news--done)
- [ ] Rotate discovery keywords per cycle
- [ ] Enrich HN summaries — still `"{title}. Points: N, Comments: M"`, which is thin enough to invite invented detail
- [ ] Tighten GitHub query, and drop the leading "latest" from the web query

### P2-2. Persona/domain mismatch on arbitrary init

[presets.py:72-86](backend/app/agent/persona/presets.py#L72-L86) overrides only `name` and `domain`, keeping the matched preset's interests. An init of `{"name": "Nova", "domain": "Robotics"}` yields Distill's `cs.LG`/`cs.CL` interests driving arXiv queries while the agent claims to be a robotics persona.

- [ ] Either synthesize a full `PersonaConfig` from the requested domain at init (one LLM call), or deliberately keep the fixed identity and document that choice in the README

### P2-3. Feed contract edge case ✅ DONE

[routes.py:104-109](backend/app/api/routes.py#L104-L109) returns **404** for an unknown `agentId`. If the host ever resets its disk, the evaluator's saved id 404s forever instead of degrading to `{"posts": []}`.

- [x] **The dashboard now recovers** — a 404 clears the stored agent and returns to the init screen instead of showing an error with no way out. Hit three times during local testing after database resets.
- [x] **The API still returns 404**, deliberately. An unknown agent genuinely is *not found*, and silently returning `{"posts": []}` would disguise a real problem as an empty feed — the same mistake behind most of the bugs above. The client degrades; the API stays honest.

### P2-4. First-post latency

The first cycle is scheduled 2–5h after init ([routes.py:77](backend/app/api/routes.py#L77)). An evaluator polling in the first hour sees an empty feed.

- [ ] Run the first cycle ~60–120s after init, then fall into the normal jittered cadence

### P2-5. Rate limits ✅ DONE

Groq's free tier returned 429s while evaluating 22 candidates in one cycle.

- [x] **Candidates capped at 10/cycle** by the pre-filter ([A-4](#a-4-editorial-decision-quality--pre-filter--done))
- [x] **Retries on transient failures** — `with_retry(stop_after_attempt=3)` on every structured call. `llama-3.3-70b` returns a malformed tool call roughly 1 time in 3, which was aborting whole cycles; retries took it to 5/5.
- [x] **Quota exhaustion is survivable** — the cycle aborts cleanly and the scheduler retries next cadence ([P1-5](#p1-5-llm-failures-publish-garbage-instead-of-skipping--done))

### P2-6. Deployment

- **Memory footprint.** `sentence-transformers` pulls torch (~1GB image); Chroma adds more. A 512MB free tier will OOM. Prefetch the model in a Docker layer and size the instance up, or swap to a hosted embeddings API.
- **Persistence.** SQLite + `chroma_data` must sit on a real volume, on an always-on host. Any sleep-on-idle service kills the autonomy story.
- **Dockerfile.** [Dockerfile:19](Dockerfile#L19) sets `PYTHONPATH=/app/backend`, but imports are `backend.app.*` — it works only because CWD is `/app`. Should be `/app`. No HF model prefetch layer, no `VOLUME` declaration.

- [ ] Fix `PYTHONPATH`
- [ ] Prefetch embedding model in the image
- [ ] Confirm host has a persistent volume and does not sleep

### P2-7. Broken helper in the test harness ✅ DONE

[test_cycle.py:125](scripts/test_cycle.py#L125) calls `MemoryRepository.get_rejected_topics(...)`, which does not exist in [repository.py](backend/app/memory/repository.py). The script prints the published post correctly, then crashes with `AttributeError`.

- [x] Added `get_rejected_topics` to `MemoryRepository`

### P2-8. Console encoding ✅ DONE

Post text contains `U+202F` and curly quotes; printing to a Windows cp1252 console raises `UnicodeEncodeError`. The JSON API is unaffected — this only breaks the local scripts.

- [x] `sys.stdout.reconfigure(encoding="utf-8")` guard added to all three scripts

---

## A — Advanced upgrades (scoring differentiators)

Everything above fixes what is broken. This section is about what would make the submission competitive.

**Most of these are already specified in [persona-distill.md](persona-distill.md) and simply never implemented.** The design work is done; only the wiring is missing. That is the cheapest available quality.

### Already strong — do not rebuild

Editorial judgment, the autonomy loop with restart re-arm, the rejection audit trail, and the hybrid dense + IDF dedup ([P0-3](#p0-3-dedup-drops-unrelated-topics--feed-goes-silent--done)). The dedup design in particular is defensible engineering and worth describing in the README as a differentiator rather than leaving buried in code.

### A-1. Persona consistency *(weakest area, highest scoring impact)*

Judging criterion: **consistency of the AI persona**.

- [x] Rewrite the writer prompt around the 4-part structure and worked example ([P1-2](#p1-2-the-persona-doc-never-reaches-the-model--done))
- [x] Pass `signature_tell` — was populated in both presets and referenced nowhere
- [x] Programmatic closing-line check, overriding the LLM verdict
- [ ] **Style-drift guard**: embed each new post, compare against the centroid of prior posts, trigger a revision if it drifts beyond a threshold. Makes consistency *measurable* instead of hoped-for, and reuses the embedding infrastructure already present.
- [ ] Programmatic check that the draft closes with a separated takeaway line, mirroring the existing forbidden-phrase check in [qa_judge.py:48-54](backend/app/agent/nodes/qa_judge.py#L48-L54)

### A-2. Memory that changes decisions, not just dedup ✅ DONE

Judging criterion: **effective use of memory**. Most submissions will stop at deduplication; these go further.

- [x] **Topic spacing** — `HybridRetriever.order_by_topic_spacing` defers candidates within 0.55 cosine distance of the most recent post. Deliberately a *reordering*, not a filter: if nothing else clears the editorial bar the related topic still publishes, matching "unless there's a genuine reason" in the persona brief. Verified: a self-critique-reasoning candidate was pushed behind an unrelated sparse-attention one when the last post was about self-critique reasoning.
- [x] **Callbacks** — the writer prompt now permits one short reference back to a retrieved past post when the connection is real, with explicit instructions never to force it and never to cite a post not in its retrieved context. The retrieval already existed and was being discarded.
- [x] **Rejection memory** — `MemoryRepository.get_rejected_urls` skips candidates this agent has already turned down, before any LLM call. Discovery returns the same items every cycle, so this compounds over a 48-hour run.
- [x] **Self-noticing** — the agent now occasionally publishes a post about a pattern in its *own* coverage instead of a new source.

  The trend is detected **deterministically** in [memory/reflection.py](backend/app/memory/reflection.py) and handed to the model. A model asked "do you notice a pattern?" always answers yes, so it is only ever asked to *write about* a pattern that was already found. Requires 5+ posts, 3+ of the last 5 on related ground, and 5 ordinary posts since the last reflection.

  `TREND_DISTANCE` calibrated on measured pairs: posts within one subfield sat at 0.56-0.75, unrelated pairs at 0.82-0.99. Grouping is anchor-based, so a theme forms when one post is close to several others rather than every pair being mutually close.

  Reflections flow through the **same QA gate** as ordinary posts rather than bypassing it, with their factual grounding checked against the agent's own post history. They carry `kind="reflection"` (added via a lightweight migration so existing databases keep working), cite the sources of the posts they reflect on, and a reflection that fails QA is abandoned rather than published unreviewed.

  Verified: trend detection across four scenarios (too few posts / real theme / varied feed / just reflected), routing through the live graph including the revise loop returning to the reflection writer, and the publish path with source de-duplication.

### A-3. Transparency beyond the minimum

Judging criterion: **transparency of publishing rationale**.

- [ ] **"Why over other candidates"** — the spec's own example rationale includes it. The data exists (that cycle's rejections) and is unused ([P1-4](#p1-4-rationale-omits-why-over-other-candidates)).
- [ ] **Grounded "why now"** — currently invented. A live run claimed a September 2023 paper *"arrives while reproducibility and independent evaluation are hot concerns."* Compute recency from `published_at` and state it factually.
- [ ] **Visible editorial restraint** — the persona doc's *"Skipped two papers this round — both were just bigger models with the same trick"*. Puts judgment in the feed itself, not only in a debug endpoint.
- [ ] Fix the self-contradicting rejection log ([P1-6](#p1-6-qa-rejections-log-the-editorial-judges-reasoning))

### A-4. Editorial decision quality — pre-filter ✅ DONE

**Why this stopped being optional.** Groq's free tier allows 200,000 tokens/day. At ~27 editorial calls per cycle the agent consumed ~29k tokens/cycle — about 6 cycles/day, against the 13-16 a 48-hour run needs. The workaround was switching to a weaker model, which **measurably degraded editorial judgment**: on the same Ask HN post, `gpt-oss-120b` scored credibility 5-6 and rejected it, while `llama-3.3-70b` scored 8 and published it.

The pre-filter ([tools/prefilter.py](backend/app/agent/tools/prefilter.py)) removes candidates the persona's own thresholds already exclude, before any LLM call:

- **Stale** — older than 30 days cannot be news for any persona
- **Thin** — a summary under 60 characters gives the writer nothing concrete, which is where invented detail comes from
- **Below the credibility ceiling** — the best score a source can realistically earn, derived from observed scoring rather than invented (arXiv 9, GitHub 7, HN 7, web 6; Ask/Tell HN self-posts capped at 5). An arXiv link posted to HN keeps the arXiv ceiling.
- **Capped** at 10 candidates per cycle, ranked by credibility with recency as tie-breaker

It deliberately makes no editorial judgement of its own — it only drops what could not clear the bar, and orders the rest.

**Two root causes surfaced while measuring it:**

- **Hacker News was returning stories up to 5,717 days old.** Algolia's `/search` ranks by relevance with no date bound. Added `numericFilters=created_at_i>` for a 21-day window; HN went from 15 stale candidates to 5 current ones.
- **arXiv only fetched 5 papers**, so after filtering there were too few on-topic candidates to reliably produce a post. Raised to 15, which the per-cycle cap then trims.

| | Before | After |
|---|---|---|
| Candidates discovered | 27 | 27 |
| **LLM calls per cycle** | **27** | **10** |
| Tokens per cycle | ~29,250 | ~12,250 |
| Cycles per day within quota | 6 | **16** |

A 48-hour run needs ~13-16 cycles, so `gpt-oss-120b` — the stricter judge — now fits comfortably. **`LLM_MODEL` restored to `openai/gpt-oss-120b`.**

- [x] Cheap pre-filter before the LLM
- [x] HN recency filter (also resolves the remaining half of [P0-4](#p0-4-stale-content-published-as-news--largely-resolved-by-p1-1))
- [ ] Source corroboration across independent sources

---

### A-5. Feed coherence across the window

Judging criterion: **overall quality and coherence of the generated feed**.

- [ ] Post-type variety (deep dive / quick take / occasional meta-post)
- [ ] Guard against topical monoculture across the full 48h

### A-6. Autonomy robustness

Judging criterion: **autonomous operation after initialization**.

- [x] **Startup self-check** — `validate_llm_configuration()` makes one cheap structured-output call at startup and classifies the outcome: unsupported response format, rate limit, or other. Logged as a banner error when it fails, and surfaced on `/health` as `canPublish`, so a deployed instance can be checked from outside without waiting a full cadence to discover it publishes nothing. Verified against all three failure modes plus the healthy path.

  > `status` stays `"ok"` when the check fails - the process really is healthy, and returning unhealthy would make a platform restart-loop a container that is serving requests correctly. `canPublish: false` is the signal that matters.
- [x] Retries and clean abort on the 429s observed on Groq's free tier ([P2-5](#p2-5-rate-limits--done))
- [ ] Deployment hardening ([P2-6](#p2-6-deployment))

---

## Suggested order

| # | Work | Why in this position |
|---|---|---|
| ✅ | ~~**P0-2** retry counter~~ | done — was silently burning whole cycles |
| ✅ | ~~**P0-3** dedup threshold~~ | done — was stalling the feed over time |
| ✅ | ~~**P2-7** + **P2-8**~~ | done — a full cycle now runs and prints end-to-end |
| **1** | **S0-1** AI Usage Log | Removes a disqualification risk for ~30 min of work. Outranks everything else — quality is irrelevant if the submission is never scored. |
| ✅ | ~~**P1-2** writer prompt~~ | done — the persona doc now drives the writer and QA judge |
| ✅ | ~~**P1-1** + **P1-3**~~ | done — thresholds enforced, memory wired into both judges |
| ✅ | ~~**P0-5** arXiv~~ | done — found while diagnosing an empty feed; the single most consequential defect |
| ✅ | ~~**P1-6** + **P1-4** + **P1-5**~~ | done — rejection log is trustworthy, rationale cites alternatives, API errors no longer masquerade as editorial decisions |
| **5** | **S0-1** fill in the AI log placeholders, then **S0-2** deploy | ← *next*. Both are Stage 1 pass/fail and deployment needs soak time |
| ✅ | ~~**A-4** cheap pre-filter~~ | done — 63% fewer LLM calls, which restored the stricter model |
| **6** | **A-2** callbacks + topic spacing | The memory differentiator most submissions will lack |
| **5** | **P0-4** recency filter | Stops stale content being published as news |
| **6** | **A-2** callbacks + topic spacing | The memory differentiator most submissions will lack |
| **7** | **S0-2** deploy + **A-6** startup self-check | Stage 1 requirement; needs soak time before the real run |
| **8** | **P1-5** fail-closed, **A-1** drift guard, **A-4** corroboration | Polish if time remains |

---

## Verification

```powershell
cd c:\Users\mansi\post_generator\Linkedin_Post_Generator-

# key loads?
python -c "from backend.app.core.config import settings; k = settings.GROQ_API_KEY or ''; print('key ok:', k.startswith('gsk_'))"

# clean slate
Remove-Item post_generator.db -Force -ErrorAction SilentlyContinue
Remove-Item chroma_data -Recurse -Force -ErrorAction SilentlyContinue

# one full cycle
python scripts\test_cycle.py

# live run (set CADENCE_MIN_HOURS=0.05 / CADENCE_MAX_HOURS=0.1 first)
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

**Reset `CADENCE_MIN_HOURS=2.0` and `CADENCE_MAX_HOURS=5.0` before the real 48h run.**
