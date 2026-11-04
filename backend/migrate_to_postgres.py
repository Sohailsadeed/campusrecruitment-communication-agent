"""Database migration script: Transfer data from SQLite to PostgreSQL."""
import sys
from pathlib import Path
from sqlalchemy import create_engine, inspect, text, select
from sqlalchemy.orm import sessionmaker

# Ensure backend root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.database.engine import Base
from app.models import (
    User,
    SessionModel,
    Transcription,
    SessionAnalysis,
    AIFeedback,
    TechnicalInterview,
)

SQLITE_URL = f"sqlite:///{Path(__file__).resolve().parent / 'speakflow.db'}"
POSTGRES_URL = "postgresql://speakflow:speakflow@localhost:5432/speakflow"

def copy_model_records(model, s_db, pg_db):
    records = s_db.scalars(select(model).order_by(model.id)).all()
    print(f"[MIGRATE] {model.__tablename__} found in SQLite: {len(records)}")
    cols = [c.name for c in model.__table__.columns]
    for r in records:
        existing = pg_db.scalar(select(model).where(model.id == r.id))
        if not existing:
            data = {col: getattr(r, col) for col in cols}
            pg_db.add(model(**data))
    pg_db.commit()

def migrate():
    print("=" * 60)
    print("SPEAKFLOW: SQLITE -> POSTGRESQL MIGRATION")
    print("=" * 60)
    
    # Engines
    sqlite_engine = create_engine(SQLITE_URL)
    pg_engine = create_engine(POSTGRES_URL)
    
    # Test PG connection
    try:
        with pg_engine.connect() as conn:
            res = conn.execute(text("SELECT version();")).scalar()
            print(f"[OK] Connected to PostgreSQL: {res}")
    except Exception as exc:
        print(f"[ERROR] Cannot connect to PostgreSQL: {exc}")
        sys.exit(1)
        
    # Create all tables in PostgreSQL
    print("[INFO] Creating schema in PostgreSQL...")
    Base.metadata.create_all(bind=pg_engine)
    print("[OK] Schema created successfully.")

    # Sessions
    SqliteSession = sessionmaker(bind=sqlite_engine)
    PgSession = sessionmaker(bind=pg_engine)
    
    with SqliteSession() as s_db, PgSession() as pg_db:
        # Order matters for foreign keys:
        # 1. User
        copy_model_records(User, s_db, pg_db)
        # 2. SessionModel
        copy_model_records(SessionModel, s_db, pg_db)
        # 3. Transcription
        copy_model_records(Transcription, s_db, pg_db)
        # 4. SessionAnalysis
        copy_model_records(SessionAnalysis, s_db, pg_db)
        # 5. AIFeedback
        copy_model_records(AIFeedback, s_db, pg_db)
        # 6. TechnicalInterview
        copy_model_records(TechnicalInterview, s_db, pg_db)

    # Reset postgres serial sequences to avoid primary key collisions on future inserts
    print("[INFO] Updating PostgreSQL sequence counters...")
    with pg_engine.connect() as conn:
        for table in ["users", "sessions", "transcriptions", "session_analyses", "ai_feedback", "technical_interviews"]:
            try:
                conn.execute(text(f"""
                    SELECT setval(
                        pg_get_serial_sequence('{table}', 'id'),
                        COALESCE((SELECT MAX(id) FROM {table}), 1)
                    );
                """))
                conn.commit()
            except Exception as e:
                print(f"[WARN] Sequence update for {table}: {e}")

    print("[SUCCESS] All tables migrated cleanly to PostgreSQL!")

if __name__ == "__main__":
    migrate()
