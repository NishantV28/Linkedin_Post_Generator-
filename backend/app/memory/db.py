from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator
from backend.app.core.config import settings
from backend.app.memory.models import Base

# SQLite configuration for multi-thread access
engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {},
    echo=False
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db() -> None:
    """Initialize database schema, creating tables if they do not exist."""
    Base.metadata.create_all(bind=engine)
    _apply_lightweight_migrations()


def _apply_lightweight_migrations() -> None:
    """
    Add columns introduced after a database was first created.

    `create_all` only creates missing tables, never alters existing ones, so an agent
    running against a database from an earlier version would fail on the new column.
    Kept deliberately minimal - this is not a migration framework.
    """
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    if "posts" not in inspector.get_table_names():
        return

    existing = {col["name"] for col in inspector.get_columns("posts")}
    if "kind" not in existing:
        with engine.begin() as connection:
            connection.execute(
                text("ALTER TABLE posts ADD COLUMN kind VARCHAR(32) NOT NULL DEFAULT 'topic'")
            )

def get_db() -> Generator[Session, None, None]:
    """Dependency to yield a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
