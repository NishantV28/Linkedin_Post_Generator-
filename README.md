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
- `walkthrough.md`: Detailed documentation on validating Phase 1.

---

## Quick Start

### 1. Setup Environment
```bash
pip install -r requirements.txt
cp .env.example .env
```

### 2. Start the FastAPI Service
```bash
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 3. Run Integration Tests
```bash
python -m pytest backend/tests/test_phase1.py
```

For more detailed API validation steps, refer to [walkthrough.md](file:///c:/Users/Nishant%20Varshney/OneDrive/Desktop/post_generator/walkthrough.md).
