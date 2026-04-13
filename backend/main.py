"""SpeakFlow FastAPI application entry point."""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database.engine import Base, engine
from app.models import AIFeedback, SessionAnalysis, SessionModel, Transcription, User  # noqa: F401
from app.routes import analysis, auth, feedback, progress, sessions
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

    app.include_router(auth.router)
    app.include_router(sessions.router)
    app.include_router(analysis.router)
    app.include_router(feedback.router)
    app.include_router(progress.router)

    @app.on_event("startup")
    def on_startup() -> None:
        logger.info("Creating database tables")
        Base.metadata.create_all(bind=engine)
        logger.info("SpeakFlow API ready")

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
