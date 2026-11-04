"""Feedback endpoints."""
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.engine import get_db
from app.models.feedback import AIFeedback
from app.models.user import User
from app.routes.auth import get_current_user
from app.schemas.feedback import AIFeedbackOut
from app.services.session_ownership import owned_session

router = APIRouter(prefix="/api/sessions", tags=["feedback"])


@router.get("/{session_id}/feedback", response_model=List[AIFeedbackOut])
def get_feedback(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[AIFeedbackOut]:
    # The rows were reached by session id alone; ownership is proven against the parent first, so a
    # foreign id refuses like an unknown one instead of listing the analysis it points at.
    session = owned_session(db, session_id, current_user)
    rows = db.scalars(
        select(AIFeedback)
        .where(AIFeedback.session_id == session.id)
        .order_by(AIFeedback.created_at.desc())
    ).all()
    if not rows:
        raise HTTPException(status_code=404, detail="No feedback for session")
    return [AIFeedbackOut.model_validate(r) for r in rows]
