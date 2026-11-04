"""ORM model for Autonomous Curriculum Coach Agent."""
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.engine import Base


class CurriculumPlan(Base):
    """Personalized multi-day placement curriculum roadmap synthesized by the Coach Agent."""

    __tablename__ = "curriculum_plans"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    target_role: Mapped[str] = mapped_column(
        String(100), default="General Placement", nullable=False
    )
    roadmap_title: Mapped[str] = mapped_column(
        String(255), default="7-Day Placement Acceleration Roadmap", nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(32), default="active", nullable=False
    )  # active, completed, archived
    target_date: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Structured telemetry & roadmap definitions
    identified_bottlenecks: Mapped[List[Dict[str, Any]]] = mapped_column(
        JSON, default=list, nullable=False
    )
    days: Mapped[List[Dict[str, Any]]] = mapped_column(
        JSON, default=list, nullable=False
    )
    meta_summary: Mapped[Dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped[Optional["User"]] = relationship("User")  # type: ignore[name-defined]
