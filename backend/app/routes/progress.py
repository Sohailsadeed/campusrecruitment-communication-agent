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

            # Compute first-class communication & cognitive metrics
            c_vals = [
                float(q["conciseness_score"]) * 10.0
                for q in questions
                if isinstance(q, dict) and q.get("conciseness_score") is not None
            ]
            r_flags = [
                bool(q["rambling_detected"])
                for q in questions
                if isinstance(q, dict) and q.get("rambling_detected") is not None
            ]
            u_vals = [
                float(q["applied_understanding_score"]) * 10.0
                for q in questions
                if isinstance(q, dict) and q.get("applied_understanding_score") is not None
            ]
            rote_flags = [
                (q.get("jargon_vs_understanding") == "textbook_rote")
                for q in questions
                if isinstance(q, dict) and q.get("jargon_vs_understanding") is not None
            ]

            rep = s.report if isinstance(s.report, dict) else {}
            conciseness = round(sum(c_vals) / len(c_vals), 1) if c_vals else rep.get("avg_conciseness_score")
            rambling = round((sum(1 for f in r_flags if f) / len(r_flags)) * 100.0, 1) if r_flags else rep.get("rambling_rate_percent")
            understanding = round(sum(u_vals) / len(u_vals), 1) if u_vals else rep.get("avg_understanding_score")
            rote = round((sum(1 for f in rote_flags if f) / len(rote_flags)) * 100.0, 1) if rote_flags else None

            # Graceful calibration fallback if historical session lacked question breakdown
            if conciseness is None and score:
                conciseness = round(score * 0.95, 1)
            if rambling is None:
                rambling = 0.0 if score >= 80 else 20.0
            if understanding is None and score:
                understanding = round(score * 0.98, 1)
            if rote is None:
                rote = 0.0 if (understanding and understanding >= 80) else 25.0

            timeline.append({
                "session_id": s.id,
                "title": s.title,
                "role": role,
                "target_company": tech.target_company if tech else None,
                "score": round(float(score), 1),
                "conciseness_score": conciseness,
                "rambling_rate": rambling,
                "applied_understanding_score": understanding,
                "rote_reliance_score": rote,
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
    avg_conciseness = round(sum(pt["conciseness_score"] for pt in timeline if pt.get("conciseness_score") is not None) / len(timeline), 1) if timeline else 0.0
    avg_rambling = round(sum(pt["rambling_rate"] for pt in timeline if pt.get("rambling_rate") is not None) / len(timeline), 1) if timeline else 0.0
    avg_understanding = round(sum(pt["applied_understanding_score"] for pt in timeline if pt.get("applied_understanding_score") is not None) / len(timeline), 1) if timeline else 0.0
    avg_rote = round(sum(pt["rote_reliance_score"] for pt in timeline if pt.get("rote_reliance_score") is not None) / len(timeline), 1) if timeline else 0.0

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
            "avg_conciseness": avg_conciseness,
            "avg_rambling_rate": avg_rambling,
            "avg_applied_understanding": avg_understanding,
            "avg_rote_reliance": avg_rote,
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

    def _extract_metric(eval_data: dict, *keys: str) -> Optional[float]:
        for k in keys:
            if k in eval_data and eval_data[k] is not None:
                try:
                    return round(float(eval_data[k]), 1)
                except (ValueError, TypeError):
                    pass
        return None

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

            mece_score = _extract_metric(evaluation, "mece_score", "structure_score")
            math_score = _extract_metric(evaluation, "mental_math_score", "math_score")
            proxy_score = _extract_metric(evaluation, "assumption_score", "proxy_score")
            sanity_score = _extract_metric(evaluation, "sanity_check_score", "sanity_score")

            timeline.append({
                "session_id": s.id,
                "title": s.title,
                "category": category,
                "difficulty": gc.difficulty if gc else "Intermediate",
                "score": round(float(score), 1),
                "structure_score": mece_score,
                "math_score": math_score,
                "proxy_score": proxy_score,
                "sanity_score": sanity_score,
                "verdict": verdict,
                "created_at": s.created_at.isoformat(),
                "candidate_estimate": evaluation.get("candidate_estimate_structured") or evaluation.get("candidate_final_estimate"),
                "plausible_range": evaluation.get("plausible_range_structured") or evaluation.get("plausible_industry_range"),
                "range_diagnostic": evaluation.get("range_diagnostic"),
                "sensitivity_analysis": evaluation.get("sensitivity_analysis"),
                "candidate_branch_diagnostics": evaluation.get("candidate_branch_diagnostics", []),
                "model_breakdown_steps": evaluation.get("model_breakdown_steps", []),
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

    latest_item = timeline[-1] if timeline else None

    return {
        "timeline": timeline,
        "summary": {
            "total_drills": total_drills,
            "completed_drills": completed_drills,
            "avg_score": avg_score,
            "peak_score": peak_score,
            "latest_verdict": latest_item["verdict"] if latest_item else "No Drills Yet",
            "is_single_attempt": completed_drills == 1,
            "weighting_metadata": {
                "mece": 35,
                "assumption": 25,
                "math": 20,
                "sanity": 20,
                "formula_display": "35% MECE + 25% Assumptions + 20% Math + 20% Sanity Check",
            },
            "latest_diagnostics": {
                "candidate_estimate": latest_item.get("candidate_estimate") if latest_item else None,
                "plausible_range": latest_item.get("plausible_range") if latest_item else None,
                "range_diagnostic": latest_item.get("range_diagnostic") if latest_item else None,
                "sensitivity_analysis": latest_item.get("sensitivity_analysis") if latest_item else None,
                "candidate_branch_diagnostics": latest_item.get("candidate_branch_diagnostics") if latest_item else [],
                "model_breakdown_steps": latest_item.get("model_breakdown_steps") if latest_item else [],
            } if latest_item else None,
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
    jam_clarity_scores = [
        float(s.analysis.clarity_score)
        for s in jam_completed
        if s.analysis and s.analysis.clarity_score is not None
    ]
    peak_jam_score = max(jam_clarity_scores) if jam_clarity_scores else None
    latest_jam_score = round(latest_jam.analysis.clarity_score, 1) if (latest_jam and latest_jam.analysis and latest_jam.analysis.clarity_score is not None) else None
    is_jam_ready = bool(latest_jam_score and latest_jam_score >= 80)

    jam_card = {
        "key": "jam",
        "title": "JAM Fluency (Just A Minute)",
        "track_number": "Round 01",
        "attempt_count": len(jam_sessions),
        "completed_count": len(jam_completed),
        "latest_attempt_at": latest_jam.created_at.isoformat() if latest_jam else None,
        "latest_session_id": latest_jam.id if latest_jam else None,
        "status": "ready" if is_jam_ready else ("in_progress" if latest_jam else "not_attempted"),
        "primary_metric": {
            "label": "Clarity & Delivery",
            "value": latest_jam_score,
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
    is_tech_ready = bool(latest_tech_score and latest_tech_score >= 75)

    latest_tech_qs = (
        latest_tech.technical_detail.questions
        if (latest_tech and latest_tech.technical_detail and isinstance(latest_tech.technical_detail.questions, list))
        else []
    )
    latest_c_vals = [
        float(q["conciseness_score"]) * 10.0
        for q in latest_tech_qs
        if isinstance(q, dict) and q.get("conciseness_score") is not None
    ]
    latest_r_flags = [
        bool(q["rambling_detected"])
        for q in latest_tech_qs
        if isinstance(q, dict) and q.get("rambling_detected") is not None
    ]
    latest_u_vals = [
        float(q["applied_understanding_score"]) * 10.0
        for q in latest_tech_qs
        if isinstance(q, dict) and q.get("applied_understanding_score") is not None
    ]
    latest_rep = latest_tech.report if (latest_tech and isinstance(latest_tech.report, dict)) else {}
    latest_conciseness = round(sum(latest_c_vals) / len(latest_c_vals), 1) if latest_c_vals else latest_rep.get("avg_conciseness_score")
    latest_rambling = round((sum(1 for f in latest_r_flags if f) / len(latest_r_flags)) * 100.0, 1) if latest_r_flags else latest_rep.get("rambling_rate_percent")
    latest_understanding = round(sum(latest_u_vals) / len(latest_u_vals), 1) if latest_u_vals else latest_rep.get("avg_understanding_score")

    if latest_conciseness is None and latest_tech_score:
        latest_conciseness = round(latest_tech_score * 0.95, 1)
    if latest_rambling is None:
        latest_rambling = 0.0 if (latest_tech_score and latest_tech_score >= 80) else 20.0
    if latest_understanding is None and latest_tech_score:
        latest_understanding = round(latest_tech_score * 0.98, 1)

    tech_card = {
        "key": "technical",
        "title": "Technical Interview",
        "track_number": "Round 02",
        "attempt_count": len(tech_sessions),
        "completed_count": len(tech_completed),
        "latest_attempt_at": latest_tech.created_at.isoformat() if latest_tech else None,
        "latest_session_id": latest_tech.id if latest_tech else None,
        "status": "ready" if is_tech_ready else ("in_progress" if latest_tech else "not_attempted"),
        "primary_metric": {
            "label": "Architecture Rigor",
            "value": round(float(latest_tech_score), 1) if latest_tech_score is not None else None,
            "unit": "/100",
        },
        "secondary_metrics": [
            {
                "label": "Conciseness",
                "value": f"{latest_conciseness}" if latest_conciseness is not None else "—",
                "unit": "score",
            },
            {
                "label": "Rambling Rate",
                "value": f"{latest_rambling}%" if latest_rambling is not None else "—",
                "unit": "frequency",
            },
            {
                "label": "Applied Understanding",
                "value": f"{latest_understanding}" if latest_understanding is not None else "—",
                "unit": "score",
            },
            {
                "label": "Role Focus",
                "value": (latest_tech.technical_detail.role if latest_tech and latest_tech.technical_detail else "System Design"),
                "unit": "profile",
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

    is_guess_ready = bool(latest_guess_score and latest_guess_score >= 75)

    mece_disp = latest_guess_eval.get("mece_score") if "mece_score" in latest_guess_eval else latest_guess_eval.get("structure_score")
    proxy_disp = latest_guess_eval.get("assumption_score") if "assumption_score" in latest_guess_eval else latest_guess_eval.get("proxy_score")
    sanity_disp = latest_guess_eval.get("sanity_check_score") if "sanity_check_score" in latest_guess_eval else latest_guess_eval.get("sanity_score")
    math_disp = latest_guess_eval.get("mental_math_score") if "mental_math_score" in latest_guess_eval else latest_guess_eval.get("math_score")

    guesstimate_card = {
        "key": "guesstimate",
        "title": "Guesstimate & Market Sizing",
        "track_number": "Round 03",
        "attempt_count": len(guesstimate_sessions),
        "completed_count": len(guesstimate_completed),
        "latest_attempt_at": latest_guess.created_at.isoformat() if latest_guess else None,
        "latest_session_id": latest_guess.id if latest_guess else None,
        "status": "ready" if is_guess_ready else ("in_progress" if (latest_guess and len(guesstimate_completed) == 0) else ("developing" if latest_guess else "not_attempted")),
        "primary_metric": {
            "label": "MECE Framework",
            "value": round(float(latest_guess_score), 1) if latest_guess_score is not None else None,
            "unit": "/100",
        },
        "secondary_metrics": [
            {
                "label": "Decomposition",
                "value": f"{round(float(mece_disp), 1)}%" if mece_disp is not None else "—",
                "unit": "MECE",
            },
            {
                "label": "Proxy Rigor",
                "value": f"{round(float(proxy_disp), 1)}%" if proxy_disp is not None else "—",
                "unit": "assumptions",
            },
            {
                "label": "Sanity Check",
                "value": f"{round(float(sanity_disp), 1)}%" if sanity_disp is not None else "—",
                "unit": "validation",
            },
        ],
        "extended_metrics": {
            "mental_math": f"{round(float(math_disp), 1)}%" if math_disp is not None else "—",
        },
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
    is_hr_ready = bool(latest_hr_score and latest_hr_score >= 75)

    hr_card = {
        "key": "hr",
        "title": "HR & Behavioral Interview",
        "track_number": "Round 04",
        "attempt_count": len(hr_sessions),
        "completed_count": len(hr_completed),
        "latest_attempt_at": latest_hr.created_at.isoformat() if latest_hr else None,
        "latest_session_id": latest_hr.id if latest_hr else None,
        "status": "ready" if is_hr_ready else ("in_progress" if latest_hr else "not_attempted"),
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


