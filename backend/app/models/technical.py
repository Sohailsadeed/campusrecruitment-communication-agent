"""Technical Round ORM model for mock interviews."""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.engine import Base


class TechnicalInterview(Base):
    """Detailed technical interview state linked to the universal Session model."""

    __tablename__ = "technical_interviews"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("sessions.id"), unique=True, nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(150), nullable=False)
    target_company: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    resume_context: Mapped[Optional[str]] = mapped_column(Text, default="", nullable=True)
    max_questions: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    question_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    questions: Mapped[dict] = mapped_column(JSON, default=list, nullable=False)
    current_question: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    session: Mapped["Session"] = relationship("Session", back_populates="technical_detail")  # type: ignore[name-defined]
