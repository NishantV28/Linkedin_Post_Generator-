# Autonomous AI Persona Agent

An autonomous publishing agent that digests AI research publications (from Hacker News, arXiv, GitHub, and web searches), evaluates them through a multi-stage editorial rubric, and publishes insights in a distinct persona voice.

*Distill is an AI research translator that publishes only when it has found the real story inside a paper — not just its highest number.*

---

## Project Structure

- `backend/app/`: FastAPI application containing API routes, core settings, memory schema, and presets.
- `backend/tests/`: Integration tests to verify API endpoints and contracts.
- `requirements.txt`: Python package dependencies.
- `.env.example`: Configuration template for API keys and DB paths.
- `Dockerfile`: Production deployment Docker image specification.
- `walkthrough.md`: Complete Phase 4 setup, API-key, scheduling, restart, and verification guide.

---

## Quick Start

### 1. Setup Environment
```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt
Copy-Item .env.example .env
```

### 2. Start the FastAPI Service
```powershell
py -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```

### 3. Run Integration Tests
```powershell
py -m pytest backend/tests -v
```

For exact live-data/API-key setup and the autonomous Phase 4 walkthrough, see [walkthrough.md](walkthrough.md).
