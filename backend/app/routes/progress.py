"""Progress / dashboard endpoints."""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.engine import get_db
from app.models.session import Session as SessionModel, SessionAnalysis
from app.models.guesstimate import GuesstimateCase
from app.models.hr import HRInterview
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


@router.get("/guesstimate")
def get_guesstimate_progress(
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(_get_optional_user),
) -> Dict[str, Any]:
    """Return guesstimate & market sizing scores, MECE structure progression, and accuracy."""
    sessions = db.scalars(
        select(SessionModel)
        .where(
            _user_session_filter(current_user),
            SessionModel.round_type == "guesstimate",
        )
        .order_by(SessionModel.created_at.asc())
    ).all()

    timeline: List[Dict[str, Any]] = []
    category_scores: Dict[str, List[float]] = {}
    completed_scores: List[float] = []

    for s in sessions:
        score = s.overall_score
        gc = s.guesstimate_detail
        evaluation = gc.evaluation if (gc and isinstance(gc.evaluation, dict)) else {}
        if score is None and evaluation:
            score = evaluation.get("overall_score")

        if score is not None:
            completed_scores.append(float(score))
            verdict = "Needs Structuring Rigor"
            if score >= 85:
                verdict = "MBB / Tier-1 Ready"
            elif score >= 70:
                verdict = "Competitive Consultant"
            elif score >= 55:
                verdict = "Promising Structure"

            category = gc.category if gc else "General Sizing"
            category_scores.setdefault(category, []).append(float(score))

            timeline.append({
                "session_id": s.id,
                "title": s.title,
                "category": category,
                "difficulty": gc.difficulty if gc else "Intermediate",
                "score": round(float(score), 1),
                "structure_score": evaluation.get("structure_score", 0),
                "math_score": evaluation.get("math_score", 0),
                "proxy_score": evaluation.get("proxy_score", 0),
                "sanity_score": evaluation.get("sanity_score", 0),
                "verdict": verdict,
                "created_at": s.created_at.isoformat(),
            })

    total_drills = len(sessions)
    completed_drills = len(completed_scores)
    avg_score = round(sum(completed_scores) / len(completed_scores), 1) if completed_scores else 0.0
    peak_score = round(max(completed_scores), 1) if completed_scores else 0.0

    categories = [
        {"category": cat, "avg_score": round(sum(scores) / len(scores), 1), "drills_count": len(scores)}
        for cat, scores in category_scores.items()
    ]
    categories.sort(key=lambda c: c["avg_score"], reverse=True)

    return {
        "timeline": timeline,
        "summary": {
            "total_drills": total_drills,
            "completed_drills": completed_drills,
            "avg_score": avg_score,
            "peak_score": peak_score,
            "latest_verdict": timeline[-1]["verdict"] if timeline else "No Drills Yet",
        },
        "categories": categories,
    }


@router.get("/hr")
def get_hr_progress(
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(_get_optional_user),
) -> Dict[str, Any]:
    """Return HR & behavioral scores, STAR completeness, and personal ownership progression."""
    sessions = db.scalars(
        select(SessionModel)
        .where(
            _user_session_filter(current_user),
            SessionModel.round_type == "hr",
        )
        .order_by(SessionModel.created_at.asc())
    ).all()

    timeline: List[Dict[str, Any]] = []
    track_scores: Dict[str, List[float]] = {}
    completed_scores: List[float] = []

    for s in sessions:
        score = s.overall_score
        hr = s.hr_detail
        report = s.report if isinstance(s.report, dict) else {}
        if score is None and report:
            score = report.get("total_score")

        questions = hr.questions if (hr and isinstance(hr.questions, list)) else []
        for q in questions:
            if isinstance(q, dict) and "evaluation" in q and isinstance(q["evaluation"], dict):
                ev = q["evaluation"]
                q_score = ev.get("overall_score")
                if q_score is not None:
                    track_name = q.get("track", "leadership_ownership").replace("_", " ").title()
                    track_scores.setdefault(track_name, []).append(float(q_score))

        if score is not None:
            completed_scores.append(float(score))
            verdict = "Developing Behavioral Presence"
            if score >= 85:
                verdict = "Executive Leadership Ready"
            elif score >= 70:
                verdict = "Strong STAR Practitioner"
            elif score < 50:
                verdict = "Needs Structural Rigor"

            timeline.append({
                "session_id": s.id,
                "title": s.title,
                "role": hr.role if hr else "General Candidate",
                "target_company": hr.target_company if hr else None,
                "mode": hr.interview_mode if hr else "standard_hr",
                "score": round(float(score), 1),
                "avg_ownership_score": report.get("avg_ownership_score", 0),
                "avg_star_completeness": report.get("avg_star_completeness", 0),
                "avg_specificity_score": report.get("avg_specificity_score", 0),
                "verdict": verdict,
                "created_at": s.created_at.isoformat(),
            })

    total_drills = len(sessions)
    completed_drills = len(completed_scores)
    avg_score = round(sum(completed_scores) / len(completed_scores), 1) if completed_scores else 0.0
    peak_score = round(max(completed_scores), 1) if completed_scores else 0.0

    competencies = [
        {"track": tr, "avg_score": round(sum(scores) / len(scores), 1), "drills_count": len(scores)}
        for tr, scores in track_scores.items()
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


@router.get("/placement-readiness")
def get_placement_readiness(
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(_get_optional_user),
) -> Dict[str, Any]:
    """Standardized 3-layer cross-round evaluation contracts across all four modules."""
    user_filter = _user_session_filter(current_user)

    # 1. JAM Sessions
    jam_sessions = db.scalars(
        select(SessionModel)
        .where(
            user_filter,
            (SessionModel.round_type.is_(None)) | (SessionModel.round_type == "jam") | (SessionModel.round_type == "general"),
        )
        .order_by(SessionModel.created_at.desc())
    ).all()
    jam_completed = [s for s in jam_sessions if s.status == "completed" and s.analysis]
    latest_jam = jam_completed[0] if jam_completed else None

    jam_card = {
        "key": "jam",
        "title": "JAM Fluency (Just A Minute)",
        "track_number": "Round 01",
        "attempt_count": len(jam_sessions),
        "completed_count": len(jam_completed),
        "latest_attempt_at": latest_jam.created_at.isoformat() if latest_jam else None,
        "latest_session_id": latest_jam.id if latest_jam else None,
        "status": "ready" if (latest_jam and latest_jam.analysis.clarity_score >= 80) else ("in_progress" if latest_jam else "not_attempted"),
        "primary_metric": {
            "label": "Clarity & Delivery",
            "value": round(latest_jam.analysis.clarity_score, 1) if latest_jam else None,
            "unit": "/100",
        },
        "secondary_metrics": [
            {
                "label": "Speaking Pace",
                "value": f"{round(latest_jam.analysis.speaking_pace, 1)}" if latest_jam else "—",
                "unit": "WPM",
            },
            {
                "label": "Filler Words",
                "value": f"{latest_jam.analysis.filler_words_count}" if latest_jam else "—",
                "unit": "detected",
            },
            {
                "label": "Eye Contact",
                "value": f"{round(latest_jam.analysis.eye_contact_percentage, 1)}%" if latest_jam else "—",
                "unit": "adherence",
            },
        ],
        "drill_path": "/record",
        "report_path": f"/analysis/{latest_jam.id}" if latest_jam else None,
    }

    # 2. Technical Sessions
    tech_sessions = db.scalars(
        select(SessionModel)
        .where(user_filter, SessionModel.round_type == "technical")
        .order_by(SessionModel.created_at.desc())
    ).all()
    tech_completed = [s for s in tech_sessions if s.overall_score is not None or s.status == "completed"]
    latest_tech = tech_completed[0] if tech_completed else None
    latest_tech_score = (
        latest_tech.overall_score if latest_tech and latest_tech.overall_score is not None
        else (latest_tech.report.get("total_score") if latest_tech and isinstance(latest_tech.report, dict) else None)
    )

    tech_card = {
        "key": "technical",
        "title": "Technical Interview",
        "track_number": "Round 02",
        "attempt_count": len(tech_sessions),
        "completed_count": len(tech_completed),
        "latest_attempt_at": latest_tech.created_at.isoformat() if latest_tech else None,
        "latest_session_id": latest_tech.id if latest_tech else None,
        "status": "ready" if (latest_tech_score and latest_tech_score >= 75) else ("in_progress" if latest_tech else "not_attempted"),
        "primary_metric": {
            "label": "Architecture Rigor",
            "value": round(float(latest_tech_score), 1) if latest_tech_score is not None else None,
            "unit": "/100",
        },
        "secondary_metrics": [
            {
                "label": "Role Focus",
                "value": (latest_tech.technical_detail.role if latest_tech and latest_tech.technical_detail else "System Design"),
                "unit": "profile",
            },
            {
                "label": "Questions Answered",
                "value": f"{len(latest_tech.technical_detail.questions)}" if latest_tech and latest_tech.technical_detail and isinstance(latest_tech.technical_detail.questions, list) else "—",
                "unit": "prompts",
            },
            {
                "label": "Benchmark Status",
                "value": "Tier-1 Competitive" if (latest_tech_score and latest_tech_score >= 80) else "Developing",
                "unit": "tier",
            },
        ],
        "drill_path": "/technical",
        "report_path": f"/technical/report/{latest_tech.id}" if latest_tech else None,
    }

    # 3. Guesstimate Sessions
    guesstimate_sessions = db.scalars(
        select(SessionModel)
        .where(user_filter, SessionModel.round_type == "guesstimate")
        .order_by(SessionModel.created_at.desc())
    ).all()
    guesstimate_completed = [
        s for s in guesstimate_sessions
        if s.overall_score is not None or (s.guesstimate_detail and s.guesstimate_detail.evaluation)
    ]
    latest_guess = guesstimate_completed[0] if guesstimate_completed else None
    latest_guess_eval = (
        latest_guess.guesstimate_detail.evaluation
        if latest_guess and latest_guess.guesstimate_detail and isinstance(latest_guess.guesstimate_detail.evaluation, dict)
        else {}
    )
    latest_guess_score = (
        latest_guess.overall_score if latest_guess and latest_guess.overall_score is not None
        else latest_guess_eval.get("overall_score")
    )

    guesstimate_card = {
        "key": "guesstimate",
        "title": "Guesstimate & Market Sizing",
        "track_number": "Round 03",
        "attempt_count": len(guesstimate_sessions),
        "completed_count": len(guesstimate_completed),
        "latest_attempt_at": latest_guess.created_at.isoformat() if latest_guess else None,
        "latest_session_id": latest_guess.id if latest_guess else None,
        "status": "ready" if (latest_guess_score and latest_guess_score >= 75) else ("in_progress" if latest_guess else "not_attempted"),
        "primary_metric": {
            "label": "MECE Framework",
            "value": round(float(latest_guess_score), 1) if latest_guess_score is not None else None,
            "unit": "/100",
        },
        "secondary_metrics": [
            {
                "label": "Decomposition",
                "value": f"{latest_guess_eval.get('structure_score', 0)}%" if latest_guess_eval else "—",
                "unit": "MECE",
            },
            {
                "label": "Math Sanity",
                "value": f"{latest_guess_eval.get('math_score', 0)}%" if latest_guess_eval else "—",
                "unit": "accuracy",
            },
            {
                "label": "Proxy Rigor",
                "value": f"{latest_guess_eval.get('proxy_score', 0)}%" if latest_guess_eval else "—",
                "unit": "assumptions",
            },
        ],
        "drill_path": "/guesstimate",
        "report_path": f"/guesstimate/report/{latest_guess.id}" if latest_guess else None,
    }

    # 4. HR & Behavioral Sessions
    hr_sessions = db.scalars(
        select(SessionModel)
        .where(user_filter, SessionModel.round_type == "hr")
        .order_by(SessionModel.created_at.desc())
    ).all()
    hr_completed = [
        s for s in hr_sessions
        if s.overall_score is not None or (s.report and isinstance(s.report, dict))
    ]
    latest_hr = hr_completed[0] if hr_completed else None
    latest_hr_report = (
        latest_hr.report if latest_hr and isinstance(latest_hr.report, dict) else {}
    )
    latest_hr_score = (
        latest_hr.overall_score if latest_hr and latest_hr.overall_score is not None
        else latest_hr_report.get("total_score")
    )

    hr_card = {
        "key": "hr",
        "title": "HR & Behavioral Interview",
        "track_number": "Round 04",
        "attempt_count": len(hr_sessions),
        "completed_count": len(hr_completed),
        "latest_attempt_at": latest_hr.created_at.isoformat() if latest_hr else None,
        "latest_session_id": latest_hr.id if latest_hr else None,
        "status": "ready" if (latest_hr_score and latest_hr_score >= 75) else ("in_progress" if latest_hr else "not_attempted"),
        "primary_metric": {
            "label": "Behavioral Fit",
            "value": round(float(latest_hr_score), 1) if latest_hr_score is not None else None,
            "unit": "/100",
        },
        "secondary_metrics": [
            {
                "label": "STAR Completeness",
                "value": f"{latest_hr_report.get('avg_star_completeness', 0)}%" if latest_hr_report else "—",
                "unit": "coverage",
            },
            {
                "label": "Personal Ownership",
                "value": f"{latest_hr_report.get('avg_ownership_score', 0)}%" if latest_hr_report else "—",
                "unit": "'I' agency",
            },
            {
                "label": "Evidence Rigor",
                "value": f"{latest_hr_report.get('avg_specificity_score', 0)}%" if latest_hr_report else "—",
                "unit": "metrics",
            },
        ],
        "drill_path": "/hr",
        "report_path": f"/hr/report/{latest_hr.id}" if latest_hr else None,
    }

    all_cards = [jam_card, tech_card, guesstimate_card, hr_card]
    attempted_count = sum(1 for c in all_cards if c["attempt_count"] > 0)
    ready_count = sum(1 for c in all_cards if c["status"] == "ready")

    return {
        "cards": all_cards,
        "attempted_count": attempted_count,
        "ready_count": ready_count,
        "total_rounds": 4,
        "evaluation_rule": "Round metrics are evaluated on distinct specialized rubrics without artificial single-score blurring.",
    }


