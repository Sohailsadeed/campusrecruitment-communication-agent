"""Analysis routes: run transcription + metrics for a session."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from app.database.engine import get_db
from app.models.feedback import AIFeedback
from app.models.session import (
    Session as SessionModel,
    SessionAnalysis,
    Transcription,
)
from app.schemas.session import SessionAnalysisOut, SessionDetailOut, TranscriptionOut
from app.services.analysis import analyze_transcription
from app.services.feedback import generate_feedback
from app.services.tracking import analyze_video
from app.services.transcription import transcribe_audio

router = APIRouter(prefix="/api/sessions", tags=["analysis"])


def _path_or_none(value: Optional[str]) -> Optional[Path]:
    return Path(value) if value else None


@router.post("/{session_id}/analyze", response_model=SessionDetailOut)
def analyze_session(session_id: int, db: Session = Depends(get_db)) -> SessionDetailOut:
    session = db.get(SessionModel, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    session.status = "processing"
    db.commit()

    try:
        # 1. Transcription
        audio_path = _path_or_none(session.audio_path) or _path_or_none(session.video_path)
        result = transcribe_audio(audio_path)
        transcription_text = str(result["text"])

        if session.transcription:
            session.transcription.text = transcription_text
            session.transcription.language = str(result["language"])
            session.transcription.confidence = float(result["confidence"])
        else:
            session.transcription = Transcription(
                session_id=session.id,
                text=transcription_text,
                language=str(result["language"]),
                confidence=float(result["confidence"]),
            )

        # 2. Text metrics
        metrics = analyze_transcription(transcription_text, session.duration_seconds)

        # 3. Video metrics
        video_metrics = analyze_video(_path_or_none(session.video_path))

        combined = {**metrics, **video_metrics}

        if session.analysis:
            session.analysis.speaking_pace = float(combined["speaking_pace"])
            session.analysis.filler_words_count = int(combined["filler_words_count"])
            session.analysis.filler_words_list = combined["filler_words_list"]
            session.analysis.clarity_score = float(combined["clarity_score"])
            session.analysis.eye_contact_percentage = float(combined["eye_contact_percentage"])
            session.analysis.posture_quality = float(combined["posture_quality"])
        else:
            session.analysis = SessionAnalysis(
                session_id=session.id,
                speaking_pace=float(combined["speaking_pace"]),
                filler_words_count=int(combined["filler_words_count"]),
                filler_words_list=combined["filler_words_list"],
                clarity_score=float(combined["clarity_score"]),
                eye_contact_percentage=float(combined["eye_contact_percentage"]),
                posture_quality=float(combined["posture_quality"]),
            )

        # 4. AI feedback — upsert to avoid duplicate rows on re-analysis
        feedback_payload = generate_feedback(combined, transcription_text)
        existing_feedback = next(
            (f for f in session.feedback if f.feedback_type == "overall"), None
        )
        if existing_feedback:
            existing_feedback.content = str(feedback_payload["content"])
            existing_feedback.score = float(feedback_payload["score"])
            existing_feedback.suggestions = list(feedback_payload["suggestions"])
        else:
            db.add(AIFeedback(
                session_id=session.id,
                feedback_type="overall",
                content=str(feedback_payload["content"]),
                score=float(feedback_payload["score"]),
                suggestions=list(feedback_payload["suggestions"]),
            ))

        session.status = "completed"
        db.commit()
        db.refresh(session)
        return SessionDetailOut.model_validate(session)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Analysis failed for session %s", session_id)
        session.status = "failed"
        db.commit()
        raise HTTPException(status_code=500, detail="Analysis failed. Please try again.")


@router.get("/{session_id}/analysis", response_model=SessionAnalysisOut)
def get_analysis(session_id: int, db: Session = Depends(get_db)) -> SessionAnalysisOut:
    session = db.get(SessionModel, session_id)
    if not session or not session.analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return SessionAnalysisOut.model_validate(session.analysis)


@router.get("/{session_id}/transcription", response_model=TranscriptionOut)
def get_transcription(
    session_id: int, db: Session = Depends(get_db)
) -> TranscriptionOut:
    session = db.get(SessionModel, session_id)
    if not session or not session.transcription:
        raise HTTPException(status_code=404, detail="Transcription not found")
    return TranscriptionOut.model_validate(session.transcription)
