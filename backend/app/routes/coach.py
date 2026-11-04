"""Autonomous Curriculum Coach API routes."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.database.engine import get_db
from app.models.coach import CurriculumPlan
from app.models.session import Session as SessionModel
from app.models.user import User
from app.routes.sessions import _get_optional_user
from app.services.coach.curriculum_agent import generate_curriculum_plan

logger = logging.getLogger("speakflow.coach.routes")

router = APIRouter(prefix="/api/coach", tags=["Curriculum Coach"])


class GeneratePlanRequest(BaseModel):
    target_role: Optional[str] = Field(default="General Placement", description="Target role / archetype")
    target_date: Optional[str] = Field(default=None, description="Interview target date, e.g. '2026-11-15'")
    force_replan: Optional[bool] = Field(default=False, description="Whether to overwrite existing active plan")


class CompleteDayRequest(BaseModel):
    plan_id: int
    day_number: int
    score_achieved: Optional[float] = None
    notes: Optional[str] = None


def _resolve_user_id(current_user: Optional[User]) -> int:
    return current_user.id if current_user else 1


@router.get("/active-plan")
def get_active_plan(
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(_get_optional_user),
) -> Dict[str, Any]:
    """Retrieve the current active 7-day curriculum plan for the candidate."""
    user_id = _resolve_user_id(current_user)
    plan = (
        db.scalars(
            select(CurriculumPlan)
            .where(
                (CurriculumPlan.user_id == user_id) | (CurriculumPlan.user_id.is_(None)),
                CurriculumPlan.status == "active",
            )
            .order_by(desc(CurriculumPlan.created_at))
        )
        .first()
    )

    if not plan:
        return {
            "has_plan": False,
            "plan": None,
        }

    return {
        "has_plan": True,
        "plan": {
            "id": plan.id,
            "target_role": plan.target_role,
            "roadmap_title": plan.roadmap_title,
            "status": plan.status,
            "target_date": plan.target_date,
            "identified_bottlenecks": plan.identified_bottlenecks,
            "days": plan.days,
            "meta_summary": plan.meta_summary,
            "created_at": plan.created_at.isoformat(),
            "updated_at": plan.updated_at.isoformat(),
        },
    }


@router.post("/generate-plan")
async def create_plan(
    payload: GeneratePlanRequest,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(_get_optional_user),
) -> Dict[str, Any]:
    """Invoke the LangGraph Curriculum Agent to synthesize a personalized roadmap."""
    user_id = _resolve_user_id(current_user)

    # Check for existing active plan
    existing_plan = (
        db.scalars(
            select(CurriculumPlan)
            .where(
                (CurriculumPlan.user_id == user_id) | (CurriculumPlan.user_id.is_(None)),
                CurriculumPlan.status == "active",
            )
            .order_by(desc(CurriculumPlan.created_at))
        )
        .first()
    )

    if existing_plan and not payload.force_replan:
        return {
            "has_plan": True,
            "reused_existing": True,
            "plan": {
                "id": existing_plan.id,
                "target_role": existing_plan.target_role,
                "roadmap_title": existing_plan.roadmap_title,
                "status": existing_plan.status,
                "target_date": existing_plan.target_date,
                "identified_bottlenecks": existing_plan.identified_bottlenecks,
                "days": existing_plan.days,
                "meta_summary": existing_plan.meta_summary,
                "created_at": existing_plan.created_at.isoformat(),
                "updated_at": existing_plan.updated_at.isoformat(),
            },
        }

    # Archive existing active plan if replanning
    if existing_plan:
        existing_plan.status = "archived"
        db.commit()

    target_role = payload.target_role or "General Placement"
    logger.info("Executing LangGraph Curriculum synthesis for user %s (role=%s)", user_id, target_role)

    agent_result = await generate_curriculum_plan(
        user_id=user_id,
        target_role=target_role,
    )

    plan_data = agent_result.get("plan", {})
    bottlenecks = agent_result.get("bottlenecks", [])
    history = agent_result.get("history_summary", {})

    new_plan = CurriculumPlan(
        user_id=user_id,
        target_role=target_role,
        roadmap_title=plan_data.get("roadmap_title", f"7-Day Placement Acceleration Roadmap: {target_role}"),
        status="active",
        target_date=payload.target_date,
        identified_bottlenecks=bottlenecks,
        days=plan_data.get("days", []),
        meta_summary={
            "focus_areas": plan_data.get("focus_areas", []),
            "history_snapshot": {
                "jam_sessions": history.get("jam", {}).get("completed_count", 0),
                "tech_sessions": history.get("technical", {}).get("completed_count", 0),
                "guesstimate_sessions": history.get("guesstimate", {}).get("completed_count", 0),
                "hr_sessions": history.get("hr", {}).get("completed_count", 0),
            },
        },
    )
    db.add(new_plan)
    db.commit()
    db.refresh(new_plan)

    return {
        "has_plan": True,
        "reused_existing": False,
        "plan": {
            "id": new_plan.id,
            "target_role": new_plan.target_role,
            "roadmap_title": new_plan.roadmap_title,
            "status": new_plan.status,
            "target_date": new_plan.target_date,
            "identified_bottlenecks": new_plan.identified_bottlenecks,
            "days": new_plan.days,
            "meta_summary": new_plan.meta_summary,
            "created_at": new_plan.created_at.isoformat(),
            "updated_at": new_plan.updated_at.isoformat(),
        },
    }


@router.post("/complete-day")
def complete_day(
    payload: CompleteDayRequest,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(_get_optional_user),
) -> Dict[str, Any]:
    """Mark a curriculum day as completed and unlock the next progressive drill."""
    user_id = _resolve_user_id(current_user)
    plan = db.get(CurriculumPlan, payload.plan_id)

    if not plan or (plan.user_id and plan.user_id != user_id and user_id != 1):
        raise HTTPException(status_code=404, detail="Curriculum plan not found")

    days: List[Dict[str, Any]] = list(plan.days)
    found = False
    all_completed = True

    for i, d in enumerate(days):
        if d.get("day_number") == payload.day_number:
            d["status"] = "completed"
            d["completed_at"] = datetime.utcnow().isoformat()
            if payload.score_achieved is not None:
                d["score_achieved"] = round(payload.score_achieved, 1)
            found = True

            # Unlock next day if it was pending
            if i + 1 < len(days) and days[i + 1].get("status") == "pending":
                days[i + 1]["status"] = "in_progress"

        if d.get("status") != "completed":
            all_completed = False

    if not found:
        raise HTTPException(status_code=400, detail=f"Day {payload.day_number} not found in plan")

    plan.days = days
    if all_completed:
        plan.status = "completed"

    flag_modified(plan, "days")
    db.commit()
    db.refresh(plan)

    return {
        "success": True,
        "plan": {
            "id": plan.id,
            "status": plan.status,
            "days": plan.days,
            "completed_day": payload.day_number,
        },
    }


@router.post("/auto-sync")
def auto_sync_recent_drills(
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(_get_optional_user),
) -> Dict[str, Any]:
    """Automatically check recent completed sessions and mark corresponding curriculum days as done."""
    user_id = _resolve_user_id(current_user)
    plan = (
        db.scalars(
            select(CurriculumPlan)
            .where(
                (CurriculumPlan.user_id == user_id) | (CurriculumPlan.user_id.is_(None)),
                CurriculumPlan.status == "active",
            )
            .order_by(desc(CurriculumPlan.created_at))
        )
        .first()
    )

    if not plan or not plan.days:
        return {"synced": False, "message": "No active curriculum plan found"}

    # Find the current in_progress day
    current_day = next((d for d in plan.days if d.get("status") == "in_progress"), None)
    if not current_day:
        return {"synced": False, "message": "No in-progress day to sync"}

    target_round = current_day.get("round_type")
    # Query latest session in that round
    user_filter = (
        (SessionModel.user_id == user_id)
        if user_id > 1
        else ((SessionModel.user_id == 1) | (SessionModel.user_id.is_(None)))
    )

    query = select(SessionModel).where(user_filter).order_by(desc(SessionModel.created_at))
    if target_round in ("jam", "general"):
        query = query.where(
            (SessionModel.round_type.is_(None))
            | (SessionModel.round_type == "jam")
            | (SessionModel.round_type == "general")
        )
    else:
        query = query.where(SessionModel.round_type == target_round)

    latest_session = db.scalars(query).first()
    if not latest_session:
        return {"synced": False, "message": "No session found for target round"}

    # Check if session was created after the plan creation
    if latest_session.created_at >= plan.created_at:
        # Extract score
        score = latest_session.overall_score
        if score is None and latest_session.analysis:
            score = latest_session.analysis.clarity_score

        # Auto-complete this day!
        days = list(plan.days)
        for i, d in enumerate(days):
            if d.get("day_number") == current_day["day_number"]:
                d["status"] = "completed"
                d["completed_at"] = latest_session.created_at.isoformat()
                d["score_achieved"] = round(float(score), 1) if score is not None else None
                if i + 1 < len(days) and days[i + 1].get("status") == "pending":
                    days[i + 1]["status"] = "in_progress"
                break

        plan.days = days
        if all(d.get("status") == "completed" for d in days):
            plan.status = "completed"

        flag_modified(plan, "days")
        db.commit()
        return {
            "synced": True,
            "completed_day": current_day["day_number"],
            "score_achieved": score,
            "session_id": latest_session.id,
        }

    return {"synced": False, "message": "No new session completed after plan generation"}
