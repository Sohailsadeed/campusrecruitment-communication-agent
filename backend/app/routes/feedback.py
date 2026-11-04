"""Feedback endpoints."""
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.engine import get_db
from app.models.feedback import AIFeedback
from app.schemas.feedback import AIFeedbackOut

router = APIRouter(prefix="/api/sessions", tags=["feedback"])


@router.get("/{session_id}/feedback", response_model=List[AIFeedbackOut])
def get_feedback(session_id: int, db: Session = Depends(get_db)) -> List[AIFeedbackOut]:
    rows = db.scalars(
        select(AIFeedback)
        .where(AIFeedback.session_id == session_id)
        .order_by(AIFeedback.created_at.desc())
    ).all()
    if not rows:
        raise HTTPException(status_code=404, detail="No feedback for session")
    return [AIFeedbackOut.model_validate(r) for r in rows]
