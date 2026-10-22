"""SpeakFlow FastAPI application entry point."""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database.engine import Base, check_and_apply_migrations, engine
from app.models import AIFeedback, SessionAnalysis, SessionModel, Transcription, User  # noqa: F401
from app.routes import analysis, auth, feedback, guesstimate, hr, progress, sessions, technical
from config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("speakflow")


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
        logger.info("SpeakFlow API ready with multi-round database schema")

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
