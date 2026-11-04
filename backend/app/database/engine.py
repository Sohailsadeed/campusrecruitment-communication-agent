"""SQLAlchemy 2.0 engine and session management.

The configured database URL is the only datastore this process may bind. Initialization fails
closed: a backend that cannot be reached raises instead of being replaced by another database.
Diagnostics carry backend and driver names plus exception class names, never connection strings.
"""
from typing import Generator, Tuple

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

import logging
from config import settings

logger = logging.getLogger("speakflow.db")

SUPPORTED_BACKENDS = frozenset({"postgresql", "sqlite"})

SYNC_DRIVERS_BY_BACKEND = {
    "postgresql": frozenset({"", "psycopg", "psycopg2", "psycopg2cffi", "pg8000"}),
    "sqlite": frozenset({"", "pysqlite"}),
}

CONNECT_ARGS_BY_BACKEND = {
    "postgresql": {"connect_timeout": 3},
    "sqlite": {"check_same_thread": False},
}


class Base(DeclarativeBase):
    """Declarative base class for all ORM models."""


class DatabaseConfigurationError(RuntimeError):
    """The configured database URL is unusable; raised before any engine is constructed."""


class DatabaseConnectionError(RuntimeError):
    """The configured database is unreachable; no substitute database is ever bound."""

    def __init__(self, message: str, *, backend: str = "", cause_class: str = "") -> None:
        super().__init__(message)
        self.backend = backend
        self.cause_class = cause_class


def _scheme_of(configured: str) -> Tuple[str, str]:
    """Split a URL into (backend, driver) without importing a dialect plugin."""
    try:
        drivername = make_url(configured).drivername or ""
    except SQLAlchemyError:
        raise DatabaseConfigurationError(
            "DATABASE_URL could not be parsed as a SQLAlchemy database URL"
        ) from None
    backend, _, driver = drivername.partition("+")
    return backend, driver


def resolve_database_url(configured: str) -> str:
    """Validate the configured URL's backend and driver, then return it byte-for-byte unchanged."""
    if not configured:
        raise DatabaseConfigurationError("no database URL is configured")

    backend, driver = _scheme_of(configured)
    if backend not in SUPPORTED_BACKENDS:
        raise DatabaseConfigurationError(f"unsupported database backend: {backend or 'unknown'}")
    if driver not in SYNC_DRIVERS_BY_BACKEND[backend]:
        raise DatabaseConfigurationError(f"unsupported {backend} driver: {driver}")
    return configured


def build_engine(configured: str) -> Engine:
    """Construct exactly one lazy engine for the validated URL; performs no I/O."""
    resolved = resolve_database_url(configured)
    backend, _ = _scheme_of(resolved)
    return create_engine(resolved, connect_args=dict(CONNECT_ARGS_BY_BACKEND[backend]))


def verify_connectivity(db_engine: Engine) -> None:
    """Open and close one connection against the engine this process will actually use."""
    with db_engine.connect():
        pass


def init_database(configured: str) -> Engine:
    """Resolve, build and verify the configured database, or fail closed with no substitute."""
    resolved = resolve_database_url(configured)
    backend, driver = _scheme_of(resolved)
    db_engine = build_engine(resolved)

    try:
        verify_connectivity(db_engine)
    except Exception as err:
        logger.error(
            "database initialization failed backend=%s driver=%s cause=%s",
            backend,
            driver or "default",
            type(err).__name__,
        )
        raise DatabaseConnectionError(
            "configured database is unreachable",
            backend=backend,
            cause_class=type(err).__name__,
        ) from None

    logger.info("database initialized backend=%s driver=%s", backend, driver or "default")
    return db_engine


database_url = resolve_database_url(settings.database_url)
engine = init_database(database_url)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a database session."""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def check_and_apply_migrations() -> None:
    """Ensure newly introduced columns exist in database without losing data, dialect-agnostic."""
    from sqlalchemy import inspect, text

    with engine.connect() as conn:
        try:
            inspector = inspect(engine)
            table_names = set(inspector.get_table_names())

            # 1. Migrate sessions table
            if "sessions" in table_names:
                existing_cols = {col["name"] for col in inspector.get_columns("sessions")}
                if "round_type" not in existing_cols:
                    conn.execute(
                        text("ALTER TABLE sessions ADD COLUMN round_type VARCHAR(32) DEFAULT 'jam'")
                    )
                if "overall_score" not in existing_cols:
                    conn.execute(text("ALTER TABLE sessions ADD COLUMN overall_score FLOAT"))
                if "round_metadata" not in existing_cols:
                    conn.execute(
                        text("ALTER TABLE sessions ADD COLUMN round_metadata JSON DEFAULT '{}'")
                    )
                if "report" not in existing_cols:
                    conn.execute(text("ALTER TABLE sessions ADD COLUMN report JSON"))
                conn.commit()

            # 2. Migrate users table for multi-round resume support
            if "users" in table_names:
                user_cols = {col["name"] for col in inspector.get_columns("users")}
                if "resume_path" not in user_cols:
                    conn.execute(text("ALTER TABLE users ADD COLUMN resume_path VARCHAR(500)"))
                if "resume_name" not in user_cols:
                    conn.execute(text("ALTER TABLE users ADD COLUMN resume_name VARCHAR(255)"))
                conn.commit()
        except Exception:
            # Table might not exist yet; Base.metadata.create_all handles initial creation
            pass
