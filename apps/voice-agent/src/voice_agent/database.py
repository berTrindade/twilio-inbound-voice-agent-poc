"""Database configuration and session management."""

from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import settings

# Provide SQLite fallback compilation for JSONB to support unit tests


@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(type_, compiler, **_):  # pragma: no cover - simple shim
    """Render JSONB columns as JSON when running on SQLite."""

    return "JSON"


# Create SQLAlchemy engine
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,  # Verify connections before using them
    echo=settings.sql_echo,  # Log SQL queries, true or false
)

# Create SessionLocal class for database sessions
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create Base class for declarative models
Base = declarative_base()
