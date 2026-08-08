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

All 17 existing tests pass after these changes.

**A full cycle now runs and prints end-to-end**: 22 candidates discovered → 7 rejected with reasoning → 1 published, with post text, rationale, sources, and the rejection audit log all visible.

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

- [ ] Add startup model validation
- [ ] Stop writing runtime errors into `rejected_topics` — use a separate `error` outcome

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

### P0-4. Stale content published as news

**Confirmed live.** The published post covers `arXiv:2309.10305` (Baichuan 2) — a **September 2023** paper — and its rationale claims *"Baichuan 2 arrives while reproducibility and independent evaluation are hot concerns, making its release timely."* Presenting a three-year-old paper as current news is immediately visible to a judge.

**Root cause.** [hn.py:30-34](backend/app/agent/tools/hn.py#L30-L34) queries Algolia's relevance-sorted `/search` with no date filter, so it returns stories from any year.

**Fix.**
- Add `numericFilters=created_at_i>{now - 72h}` to the HN query, or use `search_by_date`
- Add a hard recency gate in discovery: drop any candidate whose `published_at` is older than N days before it ever reaches the judge
- Enforce `min_timeliness` (see P1-1)

- [ ] HN recency filter
- [ ] Global `published_at` cutoff in [discovery.py](backend/app/agent/tools/discovery.py)

---

## P1 — Directly costs judging points

### P1-1. Editorial thresholds are never enforced in code

**Location.** [editorial_judge.py](backend/app/agent/nodes/editorial_judge.py), [prompts/editorial_judge.py:20](backend/app/agent/prompts/editorial_judge.py#L20)

The node trusts the LLM's `decision` string and never compares returned scores against `persona.editorial_thresholds`. `min_timeliness` isn't even mentioned in the prompt's decision rule.

**Fix.** After the LLM call, gate programmatically:

```python
t = persona.editorial_thresholds
passes = (verdict.relevance >= t.min_relevance and verdict.novelty >= t.min_novelty
          and verdict.credibility >= t.min_credibility and verdict.timeliness >= t.min_timeliness)
verdict.decision = "pass" if passes else "reject"
```

Add `min_timeliness` to the prompt too, so the model reasons about it rather than being overridden after the fact.

- [ ] Programmatic threshold gate
- [ ] Add timeliness to the decision rule in the prompt

---

### P1-2. The persona doc never reaches the model

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

**Fix.**
- [ ] Rewrite `WRITER_SYSTEM_PROMPT` around the persona doc: core question, 4-part structure, the worked example as a few-shot anchor
- [ ] Pass `signature_tell` and `stable_interests` into the prompt
- [ ] Drop "thought leader" framing entirely
- [ ] Add a programmatic check that the draft ends with a separated takeaway line, mirroring the forbidden-phrase check in [qa_judge.py:48-54](backend/app/agent/nodes/qa_judge.py#L48-L54)

---

### P1-3. Memory is written but never read by the judges

`recent_post_titles` in [editorial_judge.py:47](backend/app/agent/nodes/editorial_judge.py#L47) and `recent_posts` in [qa_judge.py:39](backend/app/agent/nodes/qa_judge.py#L39) are both hardcoded to `"None in memory."`

So the QA `non_repetitive` check is a no-op and the editorial judge has zero anti-repetition context. `MemoryRepository.get_recent_posts` exists and is **never called anywhere**.

This is the single biggest gap against the "effective use of memory" criterion — the plumbing is built, just not connected.

- [ ] Wire `get_recent_posts` into the editorial judge prompt
- [ ] Wire recent post texts into the QA prompt
- [ ] Add callbacks: instruct the writer to occasionally reference a retrieved past post (the retrieval already happens in [writer.py:33-38](backend/app/agent/nodes/writer.py#L33-L38))
- [ ] Add self-noticing: after N posts, let the persona comment on its own coverage trend

---

### P1-6. QA rejections log the *editorial* judge's reasoning

**Found in a live run after the P0-2 fix.** [rejection_logger.py:19](backend/app/agent/nodes/rejection_logger.py#L19) always builds its reason from `judge_verdict.reasoning`, regardless of which stage rejected the topic. So a QA rejection is recorded with the editorial judge's text — which, for an item that *passed* editorial review, ends in "...leading to a pass":

```
Title : 'Baichuan 2: Open Large-Scale Language Models...'
Reason: [QA Judge Rejected after revision limit] ...its recent release keeps it
        timely enough for current analysis, leading to a pass.
Scores: {"relevance": 8, "novelty": 7, "credibility": 9, "decision": "pass"}
```

A rejection labelled "rejected" that reads "leading to a pass", with `"decision": "pass"` in its scores. This is served publicly by `/api/agent/rejected` and is exactly what an evaluator inspecting editorial judgment would read.

**Fix.** When `qa_verdict` indicates the rejection, use `qa_verdict.feedback` as the reason and record the QA booleans alongside (or instead of) the editorial scores.

- [ ] Use the rejecting stage's own reasoning in `log_candidate_rejection`
- [ ] Include QA verdict fields in `judge_scores` for QA rejections

---

### P1-4. Rationale omits "why over other candidates"

The brief's example rationale explicitly includes *"why it was chosen over other candidates."* Currently [publish.py:21](backend/app/agent/nodes/publish.py#L21) emits only selection + why-now.

The data already exists — the rejections logged during that same cycle. Adding a third line naming passed-over candidates scores directly on transparency, and matches the "showing its work" behavior in the persona doc.

- [ ] Thread this cycle's rejections into the published rationale

---

### P1-5. LLM failures publish garbage instead of skipping

- [writer.py:91-95](backend/app/agent/nodes/writer.py#L91-L95) falls back to `"Interesting developments in {domain}: {title}…"` — completely off-voice
- [qa_judge.py:66-72](backend/app/agent/nodes/qa_judge.py#L66-L72) **auto-passes** on error

Together, one rate-limit blip puts template junk in the graded feed. Groq's free tier already returned **429s** during the local run.

- [ ] Writer failure → skip candidate, log as an error outcome (never publish a fallback)
- [ ] QA failure → treat as `revise`/skip, never auto-pass

---

## P2 — Robustness & deployment

### P2-1. Discovery quality

- **Repeated queries.** [github_trending.py:24](backend/app/agent/tools/github_trending.py#L24) and [web_search.py:24](backend/app/agent/tools/web_search.py#L24) always use `stable_interests[0]`, so every cycle issues an identical query and returns near-identical candidates that dedup then discards. Rotate the keyword by cycle number.
- **Thin summaries.** HN candidates carry `"{title}. Points: N, Comments: M"` as their entire summary — the judge and writer have nothing but a headline to reason about, which is how hallucinations get in. Fetch the linked page or the HN discussion text.
- **Low-quality GitHub results.** The live run surfaced unrelated 59–212 star repos. Raise the star floor and constrain by topic.
- **Web search returns non-articles.** The query in [web_search.py:24](backend/app/agent/tools/web_search.py#L24) is `"latest {keyword} research breakthrough"`, and a live run returned *"latest, late, latests — WordWeb dictionary definition"*, *"CBS News | Breaking news"*, and *"ABC News"*. The leading word "latest" is dominating the match. Drop it and query the interest term directly.
- **Rejections aren't remembered.** Rejected topics never enter the vector store, so the same item is re-discovered and re-judged at full LLM cost every cycle for 48h.

- [ ] Rotate discovery keywords per cycle
- [ ] Enrich HN summaries
- [ ] Tighten GitHub query
- [ ] Persist rejections to the vector store and skip them pre-LLM

### P2-2. Persona/domain mismatch on arbitrary init

[presets.py:72-86](backend/app/agent/persona/presets.py#L72-L86) overrides only `name` and `domain`, keeping the matched preset's interests. An init of `{"name": "Nova", "domain": "Robotics"}` yields Distill's `cs.LG`/`cs.CL` interests driving arXiv queries while the agent claims to be a robotics persona.

- [ ] Either synthesize a full `PersonaConfig` from the requested domain at init (one LLM call), or deliberately keep the fixed identity and document that choice in the README

### P2-3. Feed contract edge case

[routes.py:104-109](backend/app/api/routes.py#L104-L109) returns **404** for an unknown `agentId`. If the host ever resets its disk, the evaluator's saved id 404s forever instead of degrading to `{"posts": []}`.

- [ ] Return an empty feed rather than 404

### P2-4. First-post latency

The first cycle is scheduled 2–5h after init ([routes.py:77](backend/app/api/routes.py#L77)). An evaluator polling in the first hour sees an empty feed.

- [ ] Run the first cycle ~60–120s after init, then fall into the normal jittered cadence

### P2-5. Rate limits

Groq's free tier returned 429s while evaluating 22 candidates in one cycle.

- [ ] Cap candidates evaluated per cycle (e.g. 8)
- [ ] Add backoff//jitter between judge calls

### P2-6. Deployment

- **Memory footprint.** `sentence-transformers` pulls torch (~1GB image); Chroma adds more. A 512MB free tier will OOM. Prefetch the model in a Docker layer and size the instance up, or swap to a hosted embeddings API.
- **Persistence.** SQLite + `chroma_data` must sit on a real volume, on an always-on host. Any sleep-on-idle service kills the autonomy story.
- **Dockerfile.** [Dockerfile:19](Dockerfile#L19) sets `PYTHONPATH=/app/backend`, but imports are `backend.app.*` — it works only because CWD is `/app`. Should be `/app`. No HF model prefetch layer, no `VOLUME` declaration.

- [ ] Fix `PYTHONPATH`
- [ ] Prefetch embedding model in the image
- [ ] Confirm host has a persistent volume and does not sleep

### P2-7. Broken helper in the test harness

[test_cycle.py:125](scripts/test_cycle.py#L125) calls `MemoryRepository.get_rejected_topics(...)`, which does not exist in [repository.py](backend/app/memory/repository.py). The script prints the published post correctly, then crashes with `AttributeError`.

- [ ] Add `get_rejected_topics` to `MemoryRepository`

### P2-8. Console encoding

Post text contains `U+202F` and curly quotes; printing to a Windows cp1252 console raises `UnicodeEncodeError`. The JSON API is unaffected — this only breaks the local scripts.

- [ ] `sys.stdout.reconfigure(encoding="utf-8")` at the top of the scripts

---

## A — Advanced upgrades (scoring differentiators)

Everything above fixes what is broken. This section is about what would make the submission competitive.

**Most of these are already specified in [persona-distill.md](persona-distill.md) and simply never implemented.** The design work is done; only the wiring is missing. That is the cheapest available quality.

### Already strong — do not rebuild

Editorial judgment, the autonomy loop with restart re-arm, the rejection audit trail, and the hybrid dense + IDF dedup ([P0-3](#p0-3-dedup-drops-unrelated-topics--feed-goes-silent--done)). The dedup design in particular is defensible engineering and worth describing in the README as a differentiator rather than leaving buried in code.

### A-1. Persona consistency *(weakest area, highest scoring impact)*

Judging criterion: **consistency of the AI persona**.

- [ ] Rewrite the writer prompt around the 4-part structure and worked example ([P1-2](#p1-2-the-persona-doc-never-reaches-the-model))
- [ ] Pass `signature_tell` — populated in both presets, referenced nowhere in the codebase
- [ ] **Style-drift guard**: embed each new post, compare against the centroid of prior posts, trigger a revision if it drifts beyond a threshold. Makes consistency *measurable* instead of hoped-for, and reuses the embedding infrastructure already present.
- [ ] Programmatic check that the draft closes with a separated takeaway line, mirroring the existing forbidden-phrase check in [qa_judge.py:48-54](backend/app/agent/nodes/qa_judge.py#L48-L54)

### A-2. Memory that changes decisions, not just dedup

Judging criterion: **effective use of memory**. Most submissions will stop at deduplication; these go further.

- [ ] **Topic spacing** — the persona doc specifies avoiding back-to-back posts from the same narrow subfield. Nothing currently prevents five consecutive reasoning-paper posts.
- [ ] **Callbacks** — *"this connects to the training trick I wrote about two days ago."* The writer already retrieves topically-related past posts ([writer.py:33-38](backend/app/agent/nodes/writer.py#L33-L38)) and then ignores them.
- [ ] **Self-noticing** — *"three of my last five posts were about reasoning; here's why."* Reads as genuine continuity rather than a dedup checkbox.
- [ ] **Rejection memory** — the same rejected item is currently re-discovered and re-judged at full LLM cost every cycle for 48 hours.

### A-3. Transparency beyond the minimum

Judging criterion: **transparency of publishing rationale**.

- [ ] **"Why over other candidates"** — the spec's own example rationale includes it. The data exists (that cycle's rejections) and is unused ([P1-4](#p1-4-rationale-omits-why-over-other-candidates)).
- [ ] **Grounded "why now"** — currently invented. A live run claimed a September 2023 paper *"arrives while reproducibility and independent evaluation are hot concerns."* Compute recency from `published_at` and state it factually.
- [ ] **Visible editorial restraint** — the persona doc's *"Skipped two papers this round — both were just bigger models with the same trick"*. Puts judgment in the feed itself, not only in a debug endpoint.
- [ ] Fix the self-contradicting rejection log ([P1-6](#p1-6-qa-rejections-log-the-editorial-judges-reasoning))

### A-4. Editorial decision quality

Judging criterion: **quality of editorial decision-making**.

- [ ] Enforce thresholds in code, including `min_timeliness` ([P1-1](#p1-1-editorial-thresholds-are-never-enforced-in-code))
- [ ] **Source corroboration** — a story appearing across two or more independent sources should score higher on credibility than a single Ask HN post
- [ ] **Cheap pre-filter before the LLM** — recency and source-type priors, applied in discovery. Saves rate-limit budget and stops obviously-dead candidates consuming judge calls.

### A-5. Feed coherence across the window

Judging criterion: **overall quality and coherence of the generated feed**.

- [ ] Post-type variety (deep dive / quick take / occasional meta-post)
- [ ] Guard against topical monoculture across the full 48h

### A-6. Autonomy robustness

Judging criterion: **autonomous operation after initialization**.

- [ ] **Startup self-check** that the LLM answers a structured-output call, failing loudly on error. This is precisely the failure that would otherwise have produced zero posts for 48 hours with no visible symptom ([P0-1](#p0-1-structured-output-fails-on-the-default-model--mitigated)).
- [ ] Backoff for the 429s already observed on Groq's free tier ([P2-5](#p2-5-rate-limits))
- [ ] Deployment hardening ([P2-6](#p2-6-deployment))

---

## Suggested order

| # | Work | Why in this position |
|---|---|---|
| ✅ | ~~**P0-2** retry counter~~ | done — was silently burning whole cycles |
| ✅ | ~~**P0-3** dedup threshold~~ | done — was stalling the feed over time |
| ✅ | ~~**P2-7** + **P2-8**~~ | done — a full cycle now runs and prints end-to-end |
| **1** | **S0-1** AI Usage Log | Removes a disqualification risk for ~30 min of work. Outranks everything else — quality is irrelevant if the submission is never scored. |
| **2** | **P1-2** writer prompt (→ A-1) | Biggest visible quality gap. Every judge reads the feed; this is the weakest scoring area despite being the best-designed asset. |
| **3** | **P1-1** + **P1-3** | Two full rubric criteria, small edits |
| **4** | **P1-4** + **P1-6** + grounded why-now (A-3) | Transparency criterion |
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
