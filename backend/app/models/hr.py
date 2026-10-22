"""HR & Behavioral Round ORM model for mock interviews."""
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.engine import Base


class HRInterview(Base):
    """Detailed HR & Behavioral interview state linked to the universal Session model."""

    __tablename__ = "hr_interviews"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("sessions.id"), unique=True, nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(150), nullable=False)
    target_company: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    interview_mode: Mapped[str] = mapped_column(String(50), default="standard_hr", nullable=False)
    max_questions: Mapped[int] = mapped_column(Integer, default=4, nullable=False)
    question_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    questions: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    current_question: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    session: Mapped["Session"] = relationship("Session", back_populates="hr_detail")  # type: ignore[name-defined]


class HRQuestion(Base):
    """Canonical behavioral interview questions stored in the database."""

    __tablename__ = "hr_questions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    question_key: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    question_text: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    category: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    difficulty: Mapped[str] = mapped_column(String(50), default="Medium", nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), default="Behavioral", nullable=False)
    keywords: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    rubric: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

