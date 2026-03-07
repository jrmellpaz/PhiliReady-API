"""
SQLAlchemy engine + session factory for PostgreSQL.

Reads DATABASE_URL from environment. Normalizes postgres:// to postgresql://
for compatibility with Railway's auto-generated URLs.
"""
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

load_dotenv()

# ── Database URL ───────────────────────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL environment variable is not set. "
        "Set it in .env, e.g.: DATABASE_URL=postgresql://postgres:password@localhost:5432/bariready"
    )

# Railway sometimes generates postgres:// which psycopg2 doesn't accept
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# ── Engine ─────────────────────────────────────────────────────────────────
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,    # Drop stale connections before use
    pool_size=5,           # Sensible default for Railway free tier
    max_overflow=10,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """
    FastAPI dependency — yields a DB session, auto-closes after request.

    Usage in routers:
        @router.get("/example")
        def example(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
