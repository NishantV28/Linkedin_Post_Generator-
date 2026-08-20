import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.app.core.config import settings
from backend.app.memory.db import init_db
from backend.app.api.routes import router as agent_router
from backend.app.agent.llm import validate_llm_configuration

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("autonomous_agent")

# How long startup will wait for the LLM health check before giving up on it and
# starting anyway. Deliberately shorter than a single LLM_TIMEOUT_SECONDS: the point
# is to learn whether the provider answers promptly, not to wait out a slow call.
STARTUP_LLM_CHECK_TIMEOUT_SECONDS = 20


from backend.app.core.scheduler import rearm_active_agents, stop_all_agent_tasks

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan event handler for startup and shutdown."""
    logger.info("Initializing SQLite database tables...")
    init_db()
    logger.info("Database initialization complete.")

    # Fail loudly, not silently. A model that cannot return structured output breaks
    # every node, and the symptom is an empty feed rather than an error - so this is
    # checked once at startup and surfaced on /health for a deployed instance.
    #
    # Bounded and off the event loop, because uvicorn runs lifespan startup BEFORE it
    # binds the socket. The check builds a full retry-and-fallback chain, so a slow or
    # rate-limited provider could hold the port closed for over ten minutes - which
    # reads to a host like Render as a failed deploy rather than a configuration
    # problem. The service should come up and report the fault on /health instead.
    try:
        llm_ok, llm_detail = await asyncio.wait_for(
            asyncio.to_thread(validate_llm_configuration),
            timeout=STARTUP_LLM_CHECK_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        llm_ok, llm_detail = False, (
            f"Startup LLM check did not finish within {STARTUP_LLM_CHECK_TIMEOUT_SECONDS}s. "
            "The service is running; the provider was slow or unreachable. "
            "Publishing will fail until this clears."
        )
    except Exception as exc:
        llm_ok, llm_detail = False, f"Startup LLM check raised {type(exc).__name__}: {exc}"

    app.state.llm_ok = llm_ok
    app.state.llm_detail = llm_detail
    if llm_ok:
        logger.info(llm_detail)
    else:
        logger.error("=" * 78)
        logger.error("LLM CONFIGURATION CHECK FAILED - the agent will not publish.")
        logger.error(llm_detail)
        logger.error("=" * 78)

    logger.info("Re-arming autonomous background scheduler tasks...")
    rearm_active_agents()
    yield
    logger.info("Application shutting down.")
    await stop_all_agent_tasks()


app = FastAPI(
    title="Autonomous AI Persona Agent API",
    description="Backend service powering autonomous AI persona agents with SQLite and LangGraph",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routes
app.include_router(agent_router)


@app.get("/health", tags=["health"])
def health_check():
    """
    Service health check.

    Reports the startup LLM check too: the process can be perfectly healthy while the
    agent is incapable of publishing, and that distinction is invisible from /feed.
    """
    llm_ok = getattr(app.state, "llm_ok", None)
    return {
        "status": "ok",
        "environment": settings.ENVIRONMENT,
        "llm": {
            "ok": llm_ok,
            "model": settings.LLM_MODEL or "(provider default)",
            "detail": getattr(app.state, "llm_detail", "not checked"),
        },
        "canPublish": bool(llm_ok),
    }


# Serve the Ada Desk dashboard from the same process/port as the API. Registered
# last so it only catches requests that don't match /health or /api/... above -
# FastAPI matches routes in the order they're added, and a mount is no exception.
# The directory only exists inside the Docker image (see Dockerfile); outside of
# that (e.g. running tests locally from the repo root) it's simply absent, so the
# mount is skipped rather than crashing startup.
FRONTEND_DIR = Path(os.environ.get("FRONTEND_DIR", "/app/frontend"))
if FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="dashboard")
    logger.info(f"Serving dashboard from '{FRONTEND_DIR}'.")
else:
    logger.info(f"Frontend directory '{FRONTEND_DIR}' not found - running API-only.")

