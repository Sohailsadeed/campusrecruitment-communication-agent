"""Analysis routes: run transcription + metrics for a session."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
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
from app.services.tts import synthesize_feedback_audio

router = APIRouter(prefix="/api/sessions", tags=["analysis"])



def _path_or_none(value: Optional[str]) -> Optional[Path]:
    return Path(value) if value else None


def _calculate_cadence_sparkline(words: list, duration_seconds: float, overall_pace: float) -> list[int]:
    """Calculate 5-6 interval cadence points (WPM) across the session for sparkline charts."""
    eff_duration = max(duration_seconds, 15.0)
    num_windows = 5
    window_sec = eff_duration / num_windows

    if words and len(words) >= 5:
        points = []
        for i in range(num_windows):
            w_start = i * window_sec
            w_end = (i + 1) * window_sec
            count = sum(1 for w in words if w_start <= float(w.get("start", 0)) < w_end)
            wpm = int((count / (window_sec / 60.0))) if window_sec > 0 else int(overall_pace)
            clamped = min(210, max(85, wpm if wpm > 0 else int(overall_pace * 0.85)))
            points.append(clamped)
        return points

    base = int(overall_pace) if 90 <= overall_pace <= 190 else 142
    return [base - 8, base + 2, max(95, base - 26), base + 4, base - 2]


def _extract_filler_timeline(words: list, filler_dict: dict) -> list[dict]:
    """Map occurrences of filler words and hesitations to timestamps for timeline rendering."""
    timeline = []
    filler_set = {
        "basically", "you know", "uh", "uhh", "um", "umm", "hmm",
        "like", "actually", "literally", "er", "ah"
    }
    hesitation_set = {"uh", "uhh", "um", "umm", "hmm", "er", "ah", "basically", "like"}
    
    for w in words:
        cleaned = str(w.get("word", "")).strip().lower().strip(".,!?")
        if cleaned in filler_set:
            sec = float(w.get("start", 0.0))
            mins = int(sec // 60)
            secs = int(sec % 60)
            timeline.append({
                "word": cleaned,
                "timestamp_sec": round(sec, 2),
                "timestamp_label": f"{mins:02d}:{secs:02d}",
                "level": "error" if cleaned in hesitation_set else "secondary",
            })
    return timeline[:15]




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

        # 2. Text & Disfluency metrics with pause analysis
        pause_data = {
            "total_pause_time": result.get("total_pause_time", 0.0),
            "pause_count": result.get("pause_count", 0),
            "longest_pause": result.get("longest_pause", 0.0),
            "pauses": result.get("pauses", []),
        }
        metrics = analyze_transcription(
            transcription_text,
            session.duration_seconds,
            pause_metrics=pause_data,
        )

        # 3. Video & Multimodal nonverbal metrics
        extracted_segments = result.get("segments", [])
        video_metrics = analyze_video(
            _path_or_none(session.video_path),
            utterances=extracted_segments,
        )

        combined = {**metrics, **video_metrics, **pause_data}

        filler_payload = {
            **combined["filler_words_list"],
            "_jam": {
                "jam_score": combined.get("jam_score", combined.get("clarity_score", 0)),
                "jam_verdict": combined.get("jam_verdict", "Qualified"),
                "hesitations_count": combined.get("hesitations_count", combined.get("filler_words_count", 0)),
                "repetitions_count": combined.get("repetitions_count", 0),
                "repeated_words": combined.get("repeated_words", {}),
                "jam_infractions": combined.get("jam_infractions", []),
                "total_pause_time": combined.get("total_pause_time", 0.0),
                "pause_count": combined.get("pause_count", 0),
                "longest_pause": combined.get("longest_pause", 0.0),
                "pauses": combined.get("pauses", []),
            }
        }

        if session.analysis:
            session.analysis.speaking_pace = float(combined["speaking_pace"])
            session.analysis.filler_words_count = int(combined["filler_words_count"])
            session.analysis.filler_words_list = filler_payload
            session.analysis.clarity_score = float(combined.get("jam_score", combined["clarity_score"]))
            session.analysis.eye_contact_percentage = float(combined["eye_contact_percentage"])
            session.analysis.posture_quality = float(combined["posture_quality"])
        else:
            session.analysis = SessionAnalysis(
                session_id=session.id,
                speaking_pace=float(combined["speaking_pace"]),
                filler_words_count=int(combined["filler_words_count"]),
                filler_words_list=filler_payload,
                clarity_score=float(combined.get("jam_score", combined["clarity_score"])),
                eye_contact_percentage=float(combined["eye_contact_percentage"]),
                posture_quality=float(combined["posture_quality"]),
            )

        # 4. AI feedback — evaluating topic adherence, hesitations, nonverbal congruence, and flow
        topic_name = session.title or "General Topic"
        feedback_payload = generate_feedback(combined, transcription_text, topic=topic_name)
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

        # 5. Populate standardized multi-round fields & VerbalIQ Telemetry
        final_score = float(combined.get("jam_score", combined.get("clarity_score", feedback_payload.get("score", 0))))
        session.overall_score = final_score

        # Cadence sparkline points & filler timeline
        extracted_words = result.get("words", [])
        cadence_sparkline = _calculate_cadence_sparkline(extracted_words, session.duration_seconds, float(combined.get("speaking_pace", 140)))
        filler_timeline = _extract_filler_timeline(extracted_words, combined.get("filler_words_list", {}))

        # Preserve any presets passed when creating session
        existing_meta = session.round_metadata or {}
        session.round_metadata = {
            **existing_meta,
            "topic": topic_name,
            "category": session.description or "Impromptu",
            "speaking_pace": float(combined.get("speaking_pace", 0.0)),
            "pause_time": combined.get("total_pause_time", 0.0),
            "pause_count": combined.get("pause_count", 0),
            "repetition_count": combined.get("repetitions_count", 0),
            "hesitation_count": combined.get("hesitations_count", combined.get("filler_words_count", 0)),
            "cardinal_infractions": combined.get("jam_infractions", []),
            "eye_contact_percentage": float(combined.get("eye_contact_percentage", 82.0)),
            "posture_quality": float(combined.get("posture_quality", 85.0)),
            "hand_gestures_count": int(combined.get("hand_gestures_count", 0)),
            "fidget_count": int(combined.get("fidget_count", 0)),
        }

        session.report = {
            "total_score": final_score,
            "verdict": combined.get("jam_verdict", "Qualified"),
            "feedback_content": str(feedback_payload["content"]),
            "suggestions": list(feedback_payload["suggestions"]),
            "congruence": feedback_payload.get("congruence", {
                "status": "High Alignment",
                "analysis": "Nonverbal delivery matched spoken messaging."
            }),
            "avatar_reaction": feedback_payload.get("avatar_reaction", {
                "expression": "empathic_nod",
                "gesture": "open_palm_welcome",
                "timing": "00:02"
            }),
            "rewrites": feedback_payload.get("rewrites", []),
            "competencies": feedback_payload.get("competencies", {}),
            "mastery_points": feedback_payload.get("mastery_points", []),
            "curated_drills": feedback_payload.get("curated_drills", []),
            "cadence_sparkline": cadence_sparkline,
            "filler_timeline": filler_timeline,
            "multimodal_timeline": combined.get("multimodal_timeline", []),
            "nonverbal_summary": combined.get("nonverbal_summary", {}),
            "metrics": {
                "speaking_pace": float(combined.get("speaking_pace", 0.0)),
                "filler_words_count": int(combined.get("filler_words_count", 0)),
                "total_pause_time": float(combined.get("total_pause_time", 0.0)),
                "pause_count": int(combined.get("pause_count", 0)),
                "repetitions_count": int(combined.get("repetitions_count", 0)),
                "eye_contact_percentage": float(combined.get("eye_contact_percentage", 82.0)),
                "posture_quality": float(combined.get("posture_quality", 85.0)),
            },
        }


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


@router.get("/{session_id}/tts")
async def get_session_tts(
    session_id: int,
    db: Session = Depends(get_db),
):
    """Synthesize and stream executive coach feedback audio."""
    session = db.get(SessionModel, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    report = session.report or {}
    text_to_speak = report.get("feedback_content")
    if not text_to_speak and session.feedback:
        text_to_speak = session.feedback[0].content
    if not text_to_speak:
        text_to_speak = "Session evaluated. Solid delivery with room for structural polish."

    verdict = report.get("verdict", "")
    full_speech = f"Verdict: {verdict}. {text_to_speak}" if verdict else text_to_speak

    audio_path = await synthesize_feedback_audio(session.id, full_speech)
    if not audio_path or not audio_path.exists():
        raise HTTPException(status_code=503, detail="TTS synthesis currently unavailable")

    return FileResponse(
        path=str(audio_path),
        media_type="audio/mpeg",
        filename=f"session_{session_id}_coach.mp3",
    )

