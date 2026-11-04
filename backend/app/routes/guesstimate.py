"""Guesstimate & Market Sizing Round API endpoints."""
import asyncio
import logging
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
from app.services import upload_store
from app.services.audio_ownership import audio_file_response, resolve_guesstimate_audio_path
from app.services.guesstimate.evaluator import evaluate_guesstimate
from app.services.guesstimate.question_bank import (
    get_metadata_summary,
    get_random_question,
)
from app.services.emotion import analyze_speech_emotion, get_session_emotion_summary
from app.services.laya import get_session_laya_metrics
from app.services.transcription import transcribe_audio
from app.services.session_ownership import owned_round_session
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
    session = owned_round_session(db, session_id, current_user,
                                  round_type="guesstimate")

    case = session.guesstimate_detail
    if not case:
        raise HTTPException(status_code=404, detail="Guesstimate case detail missing.")

    # Save candidate spoken audio if uploaded. The recording is optional: a failure here costs the
    # spoken answer and the ASR it feeds, never the written answer the candidate also submitted.
    tx = upload_store.transaction()
    audio_url = None
    clip = None
    if audio_file:
        filename = f"session_{session.id}_guesstimate_{current_user.id}.webm"
        staged = None
        try:
            audio_dir = settings.upload_dir / "guesstimate_audio"
            audio_dir.mkdir(parents=True, exist_ok=True)
            staged = tx.stage(audio_dir, filename)
            await staged.write_from_upload(audio_file)
            clip = staged.publish()
            audio_url = f"/api/guesstimate/audio/{filename}"
            logger.info("Saved guesstimate spoken audio %s (session=%s)", filename, session.id)
        except Exception as exc:
            # Identifiers and exception class only — see the same note in hr.py's answer handler.
            logger.warning("Failed to save guesstimate audio %s (session=%s user=%s): %s",
                           filename, session.id, current_user.id,
                           upload_store.fault_label(exc))
            if staged is not None:
                tx.discard(staged)
            audio_url = None
            clip = None

    candidate_answer = answer
    vocal_delivery = {}
    if clip is not None:
        transcription_res, emotion_res = await asyncio.gather(
            asyncio.to_thread(transcribe_audio, clip, "small", False),
            asyncio.to_thread(analyze_speech_emotion, clip),
            return_exceptions=True,
        )
        if not isinstance(transcription_res, Exception) and transcription_res.get("text"):
            candidate_answer = str(transcription_res["text"]).strip()
        elif isinstance(transcription_res, Exception):
            logger.warning("Guesstimate ASR failed for %s: %s", clip, transcription_res)

        if isinstance(emotion_res, Exception):
            logger.warning(
                "Guesstimate emotion analysis failed for %s: %s", clip, emotion_res
            )
        else:
            vocal_delivery = emotion_res or {}

    try:
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
    except BaseException:
        # The row did not commit, so this clip describes nothing. A clip that already occupied this
        # session's slot is restored rather than left overwritten by an unrecorded answer.
        tx.rollback()
        raise
    tx.finalize()

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
    session = owned_round_session(db, session_id, current_user,
                                  round_type="guesstimate")

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
    session = owned_round_session(db, session_id, current_user,
                                  round_type="guesstimate")

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
    db: Session = Depends(get_db),
) -> FileResponse:
    """Serve the round's recording, only after proving this candidate owns the session."""
    return audio_file_response(resolve_guesstimate_audio_path(db, current_user, filename))
