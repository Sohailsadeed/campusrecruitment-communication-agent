"""Guesstimate Round ORM model for market sizing and consulting estimation drills."""
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.engine import Base


class GuesstimateCase(Base):
    """Detailed Guesstimate session state linked to the universal Session model."""

    __tablename__ = "guesstimate_cases"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("sessions.id"), unique=True, nullable=False, index=True
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    difficulty: Mapped[str] = mapped_column(String(50), nullable=False)
    approach_type: Mapped[Optional[str]] = mapped_column(String(50), default="top_down", nullable=True)
    candidate_answer: Mapped[Optional[str]] = mapped_column(Text, default="", nullable=True)
    audio_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    evaluation: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    session: Mapped["Session"] = relationship("Session", back_populates="guesstimate_detail")  # type: ignore[name-defined]
