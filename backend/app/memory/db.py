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

    if "status" not in existing:
        # Existing posts were live before review existed, so they become 'approved'
        # rather than appearing in the queue as a backlog of things to decide on.
        # New rows default to 'pending' through the ORM.
        with engine.begin() as connection:
            connection.execute(
                text("ALTER TABLE posts ADD COLUMN status VARCHAR(16) NOT NULL DEFAULT 'approved'")
            )
            connection.execute(
                text("ALTER TABLE posts ADD COLUMN reviewed_at DATETIME")
            )

    _backfill_initial_revisions()


def _backfill_initial_revisions() -> None:
    """
    Give posts that predate revision tracking a version 1 row.

    Without this, a post published before the feature shows an empty history, and its
    first reframe would look like version 1 - losing the original wording exactly as
    the old overwrite behaviour did. Runs once: posts that already have a revision are
    skipped, so repeated startups are a no-op.
    """
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if "posts" not in tables or "post_revisions" not in tables:
        return

    with engine.begin() as connection:
        connection.execute(text("""
            INSERT INTO post_revisions (id, post_id, version, text, rationale, feedback, source, created_at)
            SELECT
                lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' ||
                substr(lower(hex(randomblob(2))), 2) || '-a' ||
                substr(lower(hex(randomblob(2))), 2) || '-' || lower(hex(randomblob(6))),
                p.id, 1, p.text, p.rationale, NULL, 'original', p.created_at
            FROM posts p
            WHERE NOT EXISTS (SELECT 1 FROM post_revisions r WHERE r.post_id = p.id)
        """))


def get_db() -> Generator[Session, None, None]:
    """Dependency to yield a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
