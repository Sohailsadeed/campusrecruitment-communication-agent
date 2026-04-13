"""Progress / dashboard endpoints."""
from typing import Any, Dict, List

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.engine import get_db
from app.models.session import Session as SessionModel, SessionAnalysis

router = APIRouter(prefix="/api/progress", tags=["progress"])


@router.get("/summary")
def get_summary(db: Session = Depends(get_db)) -> Dict[str, Any]:
    sessions = db.scalars(select(SessionModel)).all()
    analyses = db.scalars(select(SessionAnalysis)).all()

    total_sessions = len(sessions)
    completed = sum(1 for s in sessions if s.status == "completed")
    total_duration = sum(s.duration_seconds for s in sessions)

    if analyses:
        avg_clarity = round(
            sum(a.clarity_score for a in analyses) / len(analyses), 2
        )
        avg_pace = round(sum(a.speaking_pace for a in analyses) / len(analyses), 2)
        avg_eye = round(
            sum(a.eye_contact_percentage for a in analyses) / len(analyses), 2
        )
        avg_posture = round(sum(a.posture_quality for a in analyses) / len(analyses), 2)
        best_pace = max((a.speaking_pace for a in analyses), default=0)
        best_clarity = max((a.clarity_score for a in analyses), default=0)
        total_filler_words = sum(a.filler_words_count for a in analyses)
    else:
        avg_clarity = avg_pace = avg_eye = avg_posture = 0.0
        best_pace = best_clarity = 0.0
        total_filler_words = 0

    return {
        "total_sessions": total_sessions,
        "completed_sessions": completed,
        "total_duration_seconds": round(total_duration, 2),
        "avg_clarity_score": avg_clarity,
        "avg_speaking_pace": avg_pace,
        "avg_eye_contact": avg_eye,
        "avg_posture_quality": avg_posture,
        "best_pace": best_pace,
        "best_clarity": best_clarity,
        "total_filler_words": total_filler_words,
    }


@router.get("/metrics")
def get_metrics(db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    """Return per-session metrics sorted chronologically for time-series charts."""
    sessions = db.scalars(
        select(SessionModel).order_by(SessionModel.created_at.asc())
    ).all()
    output: List[Dict[str, Any]] = []
    for s in sessions:
        if not s.analysis:
            continue
        output.append(
            {
                "session_id": s.id,
                "title": s.title,
                "created_at": s.created_at.isoformat(),
                "speaking_pace": s.analysis.speaking_pace,
                "clarity_score": s.analysis.clarity_score,
                "filler_words_count": s.analysis.filler_words_count,
                "eye_contact_percentage": s.analysis.eye_contact_percentage,
                "posture_quality": s.analysis.posture_quality,
            }
        )
    return output
