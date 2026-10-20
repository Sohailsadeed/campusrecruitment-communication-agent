"""Progress / dashboard endpoints."""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.engine import get_db
from app.models.session import Session as SessionModel, SessionAnalysis
from app.models.user import User
from app.routes.sessions import _get_optional_user

router = APIRouter(prefix="/api/progress", tags=["progress"])


def _user_session_filter(current_user: Optional[User]):
    """Isolate telemetry to the logged-in candidate, or fallback to User 1 for guest sandbox."""
    if current_user is not None:
        return SessionModel.user_id == current_user.id
    return (SessionModel.user_id == 1) | (SessionModel.user_id.is_(None))


@router.get("/summary")
def get_summary(
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(_get_optional_user),
) -> Dict[str, Any]:
    sessions = db.scalars(
        select(SessionModel).where(_user_session_filter(current_user))
    ).all()
    session_ids = [s.id for s in sessions]
    analyses = (
        db.scalars(
            select(SessionAnalysis).where(SessionAnalysis.session_id.in_(session_ids))
        ).all()
        if session_ids
        else []
    )

    total_sessions = len(sessions)
    completed = sum(1 for s in sessions if s.status == "completed")
    total_duration = sum(s.duration_seconds for s in sessions)

    if analyses:
        avg_clarity = round(
            sum(a.clarity_score for a in analyses) / len(analyses), 2
        )
        avg_eye = round(
            sum(a.eye_contact_percentage for a in analyses) / len(analyses), 2
        )
        avg_posture = round(sum(a.posture_quality for a in analyses) / len(analyses), 2)
        best_clarity = max((a.clarity_score for a in analyses), default=0)
        total_filler_words = sum(a.filler_words_count for a in analyses)

        # Filter out extreme pace outliers (e.g. <5s scratch tests)
        valid_paces = [a.speaking_pace for a in analyses if 40 <= a.speaking_pace <= 240]
        if valid_paces:
            avg_pace = round(sum(valid_paces) / len(valid_paces), 1)
            # In public speaking, ideal pace is ~145 WPM (130-160 range).
            # The "best pace" is the session closest to optimal delivery, not an auctioneer sprint.
            best_pace = round(min(valid_paces, key=lambda p: abs(p - 145.0)), 1)
        else:
            avg_pace = round(sum(a.speaking_pace for a in analyses) / len(analyses), 2)
            best_pace = round(min(analyses, key=lambda a: abs(a.speaking_pace - 145.0)).speaking_pace, 1)
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
def get_metrics(
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(_get_optional_user),
) -> List[Dict[str, Any]]:
    """Return per-session metrics sorted chronologically for time-series charts."""
    sessions = db.scalars(
        select(SessionModel)
        .where(_user_session_filter(current_user))
        .order_by(SessionModel.created_at.asc())
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


@router.get("/technical")
def get_technical_progress(
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(_get_optional_user),
) -> Dict[str, Any]:
    """Return technical interview scores, progression over time, and competency benchmarks."""
    sessions = db.scalars(
        select(SessionModel)
        .where(
            _user_session_filter(current_user),
            SessionModel.round_type == "technical",
        )
        .order_by(SessionModel.created_at.asc())
    ).all()

    timeline: List[Dict[str, Any]] = []
    category_scores: Dict[str, List[float]] = {}
    completed_scores: List[float] = []

    for s in sessions:
        score = s.overall_score
        if score is None and s.report and isinstance(s.report, dict):
            score = s.report.get("total_score")

        tech = s.technical_detail
        questions = tech.questions if (tech and isinstance(tech.questions, list)) else []

        # Process question categories
        for q in questions:
            if isinstance(q, dict) and "score" in q and q["score"] is not None:
                q_type = q.get("type", "Architecture").title()
                category_scores.setdefault(q_type, []).append(float(q["score"]) * 10.0)

        # Only include in progression timeline if completed or has score
        if score is not None:
            completed_scores.append(float(score))
            role = tech.role if (tech and tech.role) else s.title.replace("Technical Interview: ", "")
            verdict = "Needs Focus"
            if score >= 85:
                verdict = "Strong Hire"
            elif score >= 70:
                verdict = "Competitive Hire"
            elif score >= 55:
                verdict = "Lean Hire"

            timeline.append({
                "session_id": s.id,
                "title": s.title,
                "role": role,
                "target_company": tech.target_company if tech else None,
                "score": round(float(score), 1),
                "benchmark": 85.0,  # Staff Strong Hire Threshold
                "competitive_threshold": 70.0,
                "questions_count": len(questions),
                "verdict": verdict,
                "created_at": s.created_at.isoformat(),
            })

    total_drills = len(sessions)
    completed_drills = len(completed_scores)
    avg_score = round(sum(completed_scores) / len(completed_scores), 1) if completed_scores else 0.0
    peak_score = round(max(completed_scores), 1) if completed_scores else 0.0

    competencies = [
        {"category": cat, "avg_score": round(sum(scores) / len(scores), 1), "challenges_count": len(scores)}
        for cat, scores in category_scores.items()
    ]
    competencies.sort(key=lambda c: c["avg_score"], reverse=True)

    return {
        "timeline": timeline,
        "summary": {
            "total_drills": total_drills,
            "completed_drills": completed_drills,
            "avg_score": avg_score,
            "peak_score": peak_score,
            "latest_verdict": timeline[-1]["verdict"] if timeline else "No Drills Yet",
        },
        "competencies": competencies,
    }

