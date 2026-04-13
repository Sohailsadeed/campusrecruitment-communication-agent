"""Session, Transcription, and SessionAnalysis ORM models."""
from datetime import datetime
from typing import List, Optional

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.engine import Base


class Session(Base):
    """A single public speaking practice session."""

    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    duration_seconds: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    video_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    audio_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    user: Mapped[Optional["User"]] = relationship("User", back_populates="sessions")  # type: ignore[name-defined]
    transcription: Mapped[Optional["Transcription"]] = relationship(
        "Transcription",
        back_populates="session",
        uselist=False,
        cascade="all, delete-orphan",
    )
    analysis: Mapped[Optional["SessionAnalysis"]] = relationship(
        "SessionAnalysis",
        back_populates="session",
        uselist=False,
        cascade="all, delete-orphan",
    )
    feedback: Mapped[List["AIFeedback"]] = relationship(  # type: ignore[name-defined]
        "AIFeedback", back_populates="session", cascade="all, delete-orphan"
    )


class Transcription(Base):
    """Whisper transcription attached to a session."""

    __tablename__ = "transcriptions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("sessions.id"), unique=True, nullable=False
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String(16), default="en", nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    session: Mapped["Session"] = relationship("Session", back_populates="transcription")


class SessionAnalysis(Base):
    """Computed metrics for a session."""

    __tablename__ = "session_analyses"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("sessions.id"), unique=True, nullable=False
    )
    speaking_pace: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    filler_words_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    filler_words_list: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    clarity_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    eye_contact_percentage: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    posture_quality: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    session: Mapped["Session"] = relationship("Session", back_populates="analysis")
