"""SpeakFlow FastAPI application entry point."""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database.engine import Base, SessionLocal, check_and_apply_migrations, engine
from app.database.seed_hr import seed_hr_questions
from app.models import AIFeedback, HRInterview, HRQuestion, SessionAnalysis, SessionModel, Transcription, User  # noqa: F401
import sys
from logging.handlers import RotatingFileHandler
from app.routes import analysis, auth, feedback, guesstimate, hr, progress, sessions, technical
from config import settings

# Configure structured file and console logging
log_format = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

# 1. Console Stream Handler (real-time display)
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(log_format)
console_handler.setLevel(logging.INFO)

# 2. Main Persistent Log File (10 MB, up to 5 rotations)
app_log_file = settings.logs_dir / "speakflow.log"
file_handler = RotatingFileHandler(
    app_log_file,
    maxBytes=10 * 1024 * 1024,
    backupCount=5,
    encoding="utf-8",
)
file_handler.setFormatter(log_format)
file_handler.setLevel(logging.INFO)

# 3. Dedicated Error Log File
error_log_file = settings.logs_dir / "error.log"
error_handler = RotatingFileHandler(
    error_log_file,
    maxBytes=5 * 1024 * 1024,
    backupCount=3,
    encoding="utf-8",
)
error_handler.setFormatter(log_format)
error_handler.setLevel(logging.ERROR)

# Root logger setup
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.handlers = [console_handler, file_handler, error_handler]

logger = logging.getLogger("speakflow")
logger.info("Persistent logging initialized: saving to %s", app_log_file)


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.debug,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Core & Round Routers
    app.include_router(auth.router)
    app.include_router(sessions.router)
    app.include_router(analysis.router)
    app.include_router(feedback.router)
    app.include_router(progress.router)

    # Modular Round Routers (Blueprint alignment)
    app.include_router(sessions.router, prefix="/api/jam", tags=["JAM Round"])
    app.include_router(analysis.router, prefix="/api/jam", tags=["JAM Round"])
    app.include_router(technical.router)
    app.include_router(guesstimate.router)
    app.include_router(hr.router)

    @app.on_event("startup")
    def on_startup() -> None:
        logger.info("Creating database tables and applying migrations")
        Base.metadata.create_all(bind=engine)
        check_and_apply_migrations()
        with SessionLocal() as db:
            seed_hr_questions(db)
        logger.info("SpeakFlow API ready with multi-round database schema and HR question bank")

    @app.get("/")
    def root() -> dict:
        return {
            "name": settings.app_name,
            "version": settings.app_version,
            "status": "ok",
        }

    @app.get("/health")
    def health() -> dict:
        return {"status": "healthy"}

    return app


app = create_app()


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
