import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
    llm_ok, llm_detail = validate_llm_configuration()
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
