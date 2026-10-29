"""Guesstimate & Market Sizing Round API endpoints."""
import asyncio
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database.engine import get_db
from app.models.guesstimate import GuesstimateCase
from app.models.session import Session as SessionModel
from app.models.user import User
from app.routes.auth import get_current_user
from app.services.guesstimate.evaluator import evaluate_guesstimate
from app.services.guesstimate.question_bank import (
    get_metadata_summary,
    get_random_question,
)
from app.services.emotion import analyze_speech_emotion, get_session_emotion_summary
from app.services.laya import get_session_laya_metrics
from app.services.transcription import transcribe_audio
from config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/guesstimate", tags=["Guesstimate Round"])


# ---------------------------------------------------------
# Request Schemas
# ---------------------------------------------------------
class StartGuesstimateRequest(BaseModel):
    category: str = Field(default="Market Sizing", description="Target estimation category")
    difficulty: str = Field(default="Intermediate", description="Beginner, Intermediate, Advanced")
    question: Optional[str] = Field(default=None, description="Optional chosen or custom question")
    approach_type: Optional[str] = Field(default="top_down", description="top_down, bottom_up, or volumetric")


# ---------------------------------------------------------
# Endpoints
# ---------------------------------------------------------
@router.get("/metadata")
def get_guesstimate_metadata() -> dict:
    """Return categories and difficulties breakdown and total counts."""
    return get_metadata_summary()


@router.get("/random")
def get_random_guesstimate(
    category: Optional[str] = None,
    difficulty: Optional[str] = None,
) -> dict:
    """Fetch a random curated question matching category & difficulty."""
    return get_random_question(category=category, difficulty=difficulty)


@router.post("/start")
def start_guesstimate_session(
    req: StartGuesstimateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Initialize a new Guesstimate interview session."""
    active_q = (req.question or "").strip()
    if not active_q:
        sampled = get_random_question(category=req.category, difficulty=req.difficulty)
        active_q = sampled["question"]

    # Create universal Session record
    session = SessionModel(
        user_id=current_user.id,
        title=f"Guesstimate: {req.category}",
        description=active_q[:120] + "..." if len(active_q) > 120 else active_q,
        status="in_progress",
        round_type="guesstimate",
        duration_seconds=0.0,
        round_metadata={
            "category": req.category,
            "difficulty": req.difficulty,
            "approach_type": req.approach_type or "top_down",
        },
    )
    db.add(session)
    db.flush()

    # Create detailed GuesstimateCase record
    case_detail = GuesstimateCase(
        session_id=session.id,
        question=active_q,
        category=req.category,
        difficulty=req.difficulty,
        approach_type=req.approach_type or "top_down",
        candidate_answer="",
        evaluation=None,
    )
    db.add(case_detail)
    db.commit()

    return {
        "session_id": session.id,
        "question": active_q,
        "category": req.category,
        "difficulty": req.difficulty,
        "approach_type": req.approach_type or "top_down",
        "status": "in_progress",
    }


@router.post("/submit")
async def submit_guesstimate_answer(
    session_id: int = Form(...),
    answer: str = Form(...),
    approach_type: Optional[str] = Form(default="top_down"),
    audio_file: Optional[UploadFile] = File(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Submit candidate's verbal or written solution for consulting evaluation."""
    session = db.get(SessionModel, session_id)
    if not session or session.round_type != "guesstimate":
        raise HTTPException(status_code=404, detail="Guesstimate session not found.")

    case = session.guesstimate_detail
    if not case:
        raise HTTPException(status_code=404, detail="Guesstimate case detail missing.")

    # Save candidate spoken audio if uploaded
    audio_url = None
    dest = None
    if audio_file:
        try:
            audio_dir = settings.upload_dir / "guesstimate_audio"
            audio_dir.mkdir(parents=True, exist_ok=True)
            filename = f"session_{session.id}_guesstimate_{current_user.id}.webm"
            dest = audio_dir / filename
            content = await audio_file.read()
            with open(dest, "wb") as f:
                f.write(content)
            audio_url = f"/api/guesstimate/audio/{filename}"
            logger.info("Saved guesstimate spoken audio: %s", dest)
        except Exception as exc:
            logger.warning("Failed to save guesstimate audio: %s", exc)

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
            logger.warning("Guesstimate ASR failed for %s: %s", dest, transcription_res)

        if isinstance(emotion_res, Exception):
            logger.warning(
                "Guesstimate emotion analysis failed for %s: %s", dest, emotion_res
            )
        else:
            vocal_delivery = emotion_res or {}

    # Evaluate via Nemotron LLM
    eval_result = await evaluate_guesstimate(
        question=case.question,
        category=case.category,
        difficulty=case.difficulty,
        candidate_answer=candidate_answer.strip(),
        approach_type=approach_type or case.approach_type or "top_down",
    )
    final_vocal_delivery = get_session_emotion_summary(
        session.id, fallback=vocal_delivery
    )
    eval_result["vocal_delivery"] = final_vocal_delivery
    eval_result["laya_metrics"] = get_session_laya_metrics(session.id)

    # Update GuesstimateCase record
    case.candidate_answer = candidate_answer.strip()
    case.approach_type = approach_type or case.approach_type or "top_down"
    case.audio_url = audio_url or case.audio_url
    case.evaluation = eval_result

    # Update SessionModel
    session.status = "completed"
    session.overall_score = float(eval_result.get("overall_score", 75))
    session.report = eval_result

    db.commit()

    return {
        "session_id": session.id,
        "overall_score": session.overall_score,
        "evaluation": eval_result,
        "audio_url": case.audio_url,
        "vocal_delivery": final_vocal_delivery,
    }


@router.get("/session/{session_id}")
def get_guesstimate_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Fetch active or saved guesstimate interview session state."""
    session = db.get(SessionModel, session_id)
    if not session or session.round_type != "guesstimate":
        raise HTTPException(status_code=404, detail="Guesstimate session not found.")

    case = session.guesstimate_detail
    return {
        "session_id": session.id,
        "question": case.question if case else "Guesstimate Problem",
        "category": case.category if case else "Market Sizing",
        "difficulty": case.difficulty if case else "Intermediate",
        "approach_type": case.approach_type if case else "top_down",
        "candidate_answer": case.candidate_answer if case else "",
        "audio_url": case.audio_url if case else None,
        "is_complete": session.status == "completed",
        "overall_score": session.overall_score,
        "evaluation": session.report or (case.evaluation if case else None),
        "created_at": session.created_at.isoformat() if session.created_at else None,
    }


@router.get("/report/{session_id}")
def get_guesstimate_report(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Fetch finalized guesstimate assessment dossier."""
    session = db.get(SessionModel, session_id)
    if not session or session.round_type != "guesstimate":
        raise HTTPException(status_code=404, detail="Guesstimate session not found.")

    if not session.report:
        raise HTTPException(status_code=400, detail="Report has not been generated for this session yet.")

    case = session.guesstimate_detail
    return {
        "session_id": session.id,
        "question": case.question if case else "Guesstimate Problem",
        "category": case.category if case else "Market Sizing",
        "difficulty": case.difficulty if case else "Intermediate",
        "approach_type": case.approach_type if case else "top_down",
        "candidate_answer": case.candidate_answer if case else "",
        "audio_url": case.audio_url if case else None,
        "overall_score": session.overall_score,
        "evaluation": session.report,
        "created_at": session.created_at.isoformat() if session.created_at else None,
    }


@router.get("/audio/{filename}")
def serve_guesstimate_audio(
    filename: str,
    current_user: User = Depends(get_current_user),
) -> FileResponse:
    """Stream or serve candidate spoken guesstimate audio."""
    safe_name = Path(filename).name
    audio_path = settings.upload_dir / "guesstimate_audio" / safe_name
    if not audio_path.exists():
        raise HTTPException(status_code=404, detail="Audio recording file not found.")

    return FileResponse(
        path=str(audio_path),
        media_type="audio/webm",
        filename=safe_name,
    )
