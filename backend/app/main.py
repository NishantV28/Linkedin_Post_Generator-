import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.core.config import settings
from backend.app.memory.db import init_db
from backend.app.api.routes import router as agent_router

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
    """Service health check endpoint."""
    return {"status": "ok", "environment": settings.ENVIRONMENT}
