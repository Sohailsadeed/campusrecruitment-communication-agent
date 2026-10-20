"""SQLAlchemy 2.0 engine and session management."""
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from config import settings


class Base(DeclarativeBase):
    """Declarative base class for all ORM models."""


engine_kwargs = {}
if settings.database_url.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(settings.database_url, **engine_kwargs)
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

