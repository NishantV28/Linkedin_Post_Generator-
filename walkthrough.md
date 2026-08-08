# Phase 4 Runbook: Autonomous LinkedIn Post Generator

This guide starts the complete system from an empty local setup. After initialization, the scheduler discovers live topics, evaluates them, and writes approved posts to the feed without another API request.

## 1. What you need before starting

The system uses live data first and an LLM second. Configure the keys in this order:

| Step | Service | Is a key required? | Why it is used |
|---|---|---:|---|
| 1 | Hacker News Algolia | No | Live Hacker News stories. |
| 2 | arXiv API | No | Recent research papers. |
| 3 | GitHub Search API | No for local use | Recently updated repositories. Anonymous requests have a low rate limit; a GitHub token is not currently wired into this project. |
| 4 | Tavily | Optional, recommended | Better live web results. Without it, the app tries DuckDuckGo. |
| 5 | Groq **or** OpenAI | **Yes — choose one** | Editorial judging, post writing, and QA. No post can be generated without an LLM key. |
| 6 | Hugging Face model download | No token normally | On the first run, `sentence-transformers` downloads the local embedding model used for memory and duplicate detection. Internet access is required for that initial download. |

The minimum usable configuration is one LLM key. Groq is a good default for fast, low-cost local testing. Tavily improves discovery but is not mandatory.

## 2. Create the local environment

Run these commands in PowerShell from the repository root:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install --upgrade pip
py -m pip install -r requirements.txt
Copy-Item .env.example .env
```

If PowerShell blocks virtual-environment activation, run this once for the current terminal and retry:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

## 3. Configure `.env`

Open `.env` and set exactly one LLM provider key. Do not leave placeholder values in place.

```env
# Option A: recommended for local testing
GROQ_API_KEY=gsk_your_real_key
LLM_MODEL=llama-3.3-70b-versatile

# Option B: use this instead of GROQ_API_KEY
# OPENAI_API_KEY=sk-your_real_key
# LLM_MODEL=gpt-4o-mini

# Optional but recommended for broader web discovery
TAVILY_API_KEY=tvly-your_real_key

# Normal autonomous cadence and 48-hour safety cap
CADENCE_MIN_HOURS=2.0
CADENCE_MAX_HOURS=5.0
MAX_POSTS_48H=16
```

Keep `DATABASE_URL=sqlite:///./post_generator.db` unless you deliberately want the local database elsewhere. The SQLite database and `chroma_data` directory are persistent memory; do not delete them if you want the agent to remember prior posts after restarting.

## 4. Start the API

```powershell
py -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```

In another PowerShell window, confirm it is healthy:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

Expected response:

```json
{"status":"ok","environment":"development"}
```

## 5. Start an autonomous agent (the only required API call)

Create an agent once. This persists its persona and its first scheduled run timestamp, then starts a background scheduler task.

```powershell
$body = @{ persona = @{ name = "Distill"; domain = "AI Research" } } | ConvertTo-Json
$init = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/agent/init -ContentType "application/json" -Body $body
$agentId = $init.agentId
$agentId
```

Save the returned UUID. Calling `/init` again with the same name and domain returns the same active agent instead of creating a duplicate scheduler.

The normal first cycle runs after a random delay between `CADENCE_MIN_HOURS` and `CADENCE_MAX_HOURS`. That is intentional: it prevents synchronized posting and is persisted in SQLite. Inspect it with:

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/api/agent/status?agentId=$agentId"
```

## 6. Observe the autonomous cycle

When the scheduled time arrives, the agent performs this flow automatically:

```text
live sources → hybrid duplicate check → editorial judge → writer → QA → SQLite + Chroma → feed
```

Use these read-only endpoints while it runs:

```powershell
# Current scheduler state and next scheduled time
Invoke-RestMethod "http://127.0.0.1:8000/api/agent/status?agentId=$agentId"

# Approved posts, newest first
Invoke-RestMethod "http://127.0.0.1:8000/api/agent/feed?agentId=$agentId"

# Topics declined by editorial or QA checks
Invoke-RestMethod "http://127.0.0.1:8000/api/agent/rejected?agentId=$agentId"
```

`/feed` never triggers discovery or an LLM call; it only reads persisted posts. A published item contains its post text, selection/why-now rationale, and source URLs.

## 7. Fast local Phase 4 verification

Do not change your production cadence just to test scheduling. The included harness creates/uses a test agent with a 3.6–7.2 second cadence, runs for about 15 seconds, and reports cycle, post, and audit counts.

```powershell
py scripts/test_scheduler.py
```

It still needs the same LLM key and internet access because it runs real discovery and real editorial generation. Stop it with `Ctrl+C` after reviewing its summary.

For unit and integration checks, run:

```powershell
py -m pytest backend/tests -v
```

## 8. Restart behavior and limits

Stop the server with `Ctrl+C`, then start it again using the command in section 4. At startup the app finds all active agents and re-arms each one using its persisted `next_run_at`; it does not restart the cadence from zero.

An agent deactivates automatically when either condition is reached:

- 48 hours have elapsed since it was initialized.
- It has published `MAX_POSTS_48H` posts. Rejected/no-candidate cycles do not consume this post budget.

To begin a truly fresh demo, use a different persona name/domain. Existing SQLite and Chroma memory intentionally prevents repeat topic selection for an existing agent.

## 9. Docker option

After configuring `.env`, build and run the backend with persistent local storage mounted into the container:

```powershell
docker build -t linkedin-post-generator .
docker run --rm -p 8000:8000 --env-file .env -v "${PWD}\post_generator.db:/app/post_generator.db" -v "${PWD}\chroma_data:/app/chroma_data" linkedin-post-generator
```

Use the same `/health`, `/init`, `/status`, `/feed`, and `/rejected` commands above. For a 48-hour run, deploy it only to an always-on host with persistent storage; a serverless or sleeping service cannot keep the autonomous scheduler alive.
