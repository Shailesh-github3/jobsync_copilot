import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, DeclarativeBase

# Load environment variables from .env file
load_dotenv()

# SQLite database URL (defaults to local file, can be overridden via env var in Docker)
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./jobsync_copilot.db")

# check_same_thread=False is required for SQLite with FastAPI
# because FastAPI may access the DB from different threads.
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False, "timeout": 10},
    echo=False,  # Avoid logging sensitive candidate PII to stdout
)

from sqlalchemy.engine import Engine

# Enforce foreign key constraints in SQLite
@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")  # Enable Write-Ahead Logging for better concurrency
    cursor.execute("PRAGMA busy_timeout=10000")  # Set busy timeout to 10000 ms
    cursor.close()

# Session factory. Each request gets its own Session instance.
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

# Base class for all ORM models.
class Base(DeclarativeBase):
    """Base class for all ORM models (SQLAlchemy 2.0 style)."""
    pass


def get_db():
    """FastAPI dependency. Yields a DB session, then closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()