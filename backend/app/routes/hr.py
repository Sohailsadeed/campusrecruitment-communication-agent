"""HR & Behavioral Round API endpoints."""
import asyncio
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database.engine import get_db
from app.models.hr import HRInterview
from app.models.session import Session as SessionModel
from app.models.user import User
from app.routes.auth import get_current_user
from app.services.hr.evaluator import evaluate_hr_answer, generate_hr_report
from app.services.hr.hr_service import pick_next_hr_question
from app.services.hr.question_bank import get_hr_tracks, get_initial_hr_question, query_hr_questions
from app.services.emotion import analyze_speech_emotion, get_session_emotion_summary
from app.services.transcription import transcribe_audio
from config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/hr", tags=["HR Round"])


# ---------------------------------------------------------
# Request Schemas
# ---------------------------------------------------------
class StartHRRequest(BaseModel):
    role: str = Field(default="Software Engineer", description="Target role")
    target_company: Optional[str] = Field(default=None, description="Target company")
    interview_mode: str = Field(default="standard_hr", description="Behavioral track or standard_hr")
    max_questions: int = Field(default=4, ge=1, le=8, description="Total behavioral questions")


# ---------------------------------------------------------
# Endpoints
# ---------------------------------------------------------
@router.get("/tracks")
def get_behavioral_tracks() -> dict:
    """Return available behavioral interview tracks."""
    return {"tracks": get_hr_tracks()}


@router.get("/questions")
def get_behavioral_questions(
    category: Optional[str] = None,
    difficulty: Optional[str] = None,
    db: Session = Depends(get_db),
) -> dict:
    """Query canonical HR & behavioral questions directly from the database."""
    questions = query_hr_questions(db=db, category=category, difficulty=difficulty)
    return {"count": len(questions), "questions": questions}


@router.post("/start")
def start_hr_interview(
    req: StartHRRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Initialize a new HR & Behavioral mock interview session."""
    q1 = get_initial_hr_question(db=db, track=req.interview_mode, company=req.target_company)

    # Create universal Session record
    session = SessionModel(
        user_id=current_user.id,
        title=f"HR Behavioral: {req.role}",
        description=req.target_company or "Behavioral & Cultural Interview",
        status="in_progress",
        round_type="hr",
        duration_seconds=0.0,
        round_metadata={
            "role": req.role,
            "target_company": req.target_company,
            "interview_mode": req.interview_mode,
        },
    )
    db.add(session)
    db.flush()

    # Create detailed HRInterview record
    hr_detail = HRInterview(
        session_id=session.id,
        role=req.role,
        target_company=req.target_company,
        interview_mode=req.interview_mode,
        max_questions=req.max_questions,
        question_count=0,
        questions=[],
        current_question=q1,
    )
    db.add(hr_detail)
    db.commit()

    return {
        "session_id": session.id,
        "role": req.role,
        "target_company": req.target_company,
        "interview_mode": req.interview_mode,
        "current_question": q1,
        "question_count": 0,
        "max_questions": req.max_questions,
        "is_complete": False,
    }


@router.post("/answer")
async def submit_hr_answer(
    session_id: int = Form(...),
    answer: str = Form(...),
    audio_file: Optional[UploadFile] = File(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Submit candidate's behavioral answer, evaluate STAR and ownership, and advance."""
    session = db.get(SessionModel, session_id)
    if not session or session.round_type != "hr":
        raise HTTPException(status_code=404, detail="HR interview session not found.")

    hr = session.hr_detail
    if not hr:
        raise HTTPException(status_code=404, detail="HR interview detail missing.")

    if not hr.current_question:
        raise HTTPException(status_code=400, detail="Interview is already completed.")

    curr_q = hr.current_question

    # Save audio if uploaded
    audio_url = None
    dest = None
    if audio_file:
        try:
            audio_dir = settings.upload_dir / "hr_audio"
            audio_dir.mkdir(parents=True, exist_ok=True)
            q_num = hr.question_count + 1
            filename = f"session_{session.id}_hr_q_{q_num}_{current_user.id}.webm"
            dest = audio_dir / filename
            content = await audio_file.read()
            with open(dest, "wb") as f:
                f.write(content)
            audio_url = f"/api/hr/audio/{filename}"
            logger.info("Saved HR spoken audio: %s", dest)
        except Exception as exc:
            logger.warning("Failed to save HR spoken audio: %s", exc)

    candidate_answer = answer
    vocal_delivery = {}
    if dest and dest.exists():
        transcription_res, emotion_res = await asyncio.gather(
            asyncio.to_thread(transcribe_audio, dest, "small", False),
            asyncio.to_thread(analyze_speech_emotion, dest),
            return_exceptions=True,
        )
        if not isinstance(transcription_res, Exception) and transcription_res.get("text"):
            candidate_answer = str(transcription_res["text"]).strip()
        elif isinstance(transcription_res, Exception):
            logger.warning("HR ASR failed for %s: %s", dest, transcription_res)

        if isinstance(emotion_res, Exception):
            logger.warning("HR emotion analysis failed for %s: %s", dest, emotion_res)
        else:
            vocal_delivery = emotion_res or {}

    # Evaluate via Nemotron
    eval_result = await evaluate_hr_answer(
        role=hr.role,
        company=hr.target_company,
        track=curr_q.get("track", hr.interview_mode),
        question=curr_q.get("text", "Behavioral question"),
        candidate_answer=candidate_answer.strip(),
    )

    completed_question = {
        **curr_q,
        "answer": candidate_answer.strip(),
        "audio_url": audio_url,
        "vocal_delivery": vocal_delivery,
        "evaluation": eval_result,
    }

    updated_questions = list(hr.questions or [])
    updated_questions.append(completed_question)
    hr.questions = updated_questions
    hr.question_count = len(updated_questions)

    # Determine if round is complete
    is_complete = hr.question_count >= hr.max_questions
    report = None
    next_q = None

    if is_complete:
        hr.current_question = None
        report = await generate_hr_report(
            role=hr.role,
            company=hr.target_company,
            questions_asked=updated_questions,
        )
        session.status = "completed"
        session.overall_score = float(report.get("total_score", 75))
        report["vocal_delivery"] = get_session_emotion_summary(
            session.id, fallback=vocal_delivery
        )
        session.report = report
    else:
        next_q = pick_next_hr_question(
            track=hr.interview_mode,
            company=hr.target_company,
            questions_asked=updated_questions,
            db=db,
        )
        hr.current_question = next_q

    db.commit()

    return {
        "session_id": session.id,
        "evaluation": eval_result,
        "next_question": next_q,
        "is_complete": is_complete,
        "report": report,
        "question_count": hr.question_count,
        "max_questions": hr.max_questions,
        "audio_url": audio_url,
        "vocal_delivery": vocal_delivery,
    }


@router.get("/session/{session_id}")
def get_hr_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Fetch active or saved state of an HR interview session."""
    session = db.get(SessionModel, session_id)
    if not session or session.round_type != "hr":
        raise HTTPException(status_code=404, detail="HR interview session not found.")

    hr = session.hr_detail
    return {
        "session_id": session.id,
        "role": hr.role if hr else "HR Behavioral Interview",
        "target_company": hr.target_company if hr else None,
        "interview_mode": hr.interview_mode if hr else "standard_hr",
        "current_question": hr.current_question if hr else None,
        "question_count": hr.question_count if hr else 0,
        "max_questions": hr.max_questions if hr else 4,
        "is_complete": session.status == "completed",
        "questions": hr.questions if hr else [],
        "report": session.report,
        "overall_score": session.overall_score,
        "created_at": session.created_at.isoformat() if session.created_at else None,
    }


@router.get("/report/{session_id}")
def get_hr_report(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Fetch finalized HR behavioral scorecard and dossier."""
    session = db.get(SessionModel, session_id)
    if not session or session.round_type != "hr":
        raise HTTPException(status_code=404, detail="HR session not found.")

    if not session.report:
        raise HTTPException(status_code=400, detail="Report has not been generated for this session yet.")

    hr = session.hr_detail
    return {
        "session_id": session.id,
        "role": hr.role if hr else "Behavioral Candidate",
        "target_company": hr.target_company if hr else None,
        "interview_mode": hr.interview_mode if hr else "standard_hr",
        "overall_score": session.overall_score,
        "report": session.report,
        "questions": hr.questions if hr else [],
        "created_at": session.created_at.isoformat() if session.created_at else None,
    }


@router.get("/audio/{filename}")
def serve_hr_audio(
    filename: str,
    current_user: User = Depends(get_current_user),
) -> FileResponse:
    """Stream or serve candidate spoken HR audio recording."""
    safe_name = Path(filename).name
    audio_path = settings.upload_dir / "hr_audio" / safe_name
    if not audio_path.exists():
        raise HTTPException(status_code=404, detail="Audio recording file not found.")

    return FileResponse(
        path=str(audio_path),
        media_type="audio/webm",
        filename=safe_name,
    )
