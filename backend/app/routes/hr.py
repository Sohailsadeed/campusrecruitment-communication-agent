"""HR & Behavioral Round API endpoints."""
import asyncio
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database.engine import get_db
from app.models.hr import HRInterview
from app.models.session import Session as SessionModel
from app.models.user import User
from app.routes.auth import get_current_user
from app.services import upload_store
from app.services.audio_ownership import audio_file_response, resolve_hr_audio_path
from app.services.hr.evaluator import evaluate_hr_answer, generate_hr_report
from app.services.hr.hr_service import (
    pick_next_hr_question,
    question_ref as live_question_ref,
    resolve_answer_slot,
)
from app.services.hr.question_bank import get_hr_tracks, get_initial_hr_question, query_hr_questions
from app.services.session_ownership import owned_round_session
from app.services.speech_analytics import analyze_answer, round_report_block, session_metrics, trends
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
    question_ref: Optional[str] = Form(default=None),
    audio_file: Optional[UploadFile] = File(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Submit candidate's behavioral answer, evaluate STAR and ownership, and advance.

    `question_ref` names the question being answered (its id, or its text) and may be left empty.
    Either way, only the question this round is currently on is written: an answer naming a question
    the round has already moved past is refused with 409 instead of replacing the recorded answer.
    """
    session = owned_round_session(db, session_id, current_user, round_type="hr")

    hr = session.hr_detail
    if not hr:
        raise HTTPException(status_code=404, detail="HR interview detail missing.")

    if not hr.current_question:
        raise HTTPException(status_code=400, detail="Interview is already completed.")

    curr_q = hr.current_question

    slot, slot_index = resolve_answer_slot(curr_q, hr.questions or [], question_ref)
    if slot != "live":
        # Nothing has been stored, evaluated or uploaded: a rejected submit leaves no trace, so a
        # retried one cannot land as a second entry for the same question.
        logger.info("Rejected HR answer for session %s (question_ref=%r is %s, live=%r)",
                    session.id, question_ref, slot, live_question_ref(curr_q))
        if slot == "history":
            raise HTTPException(
                status_code=409,
                detail="That question is already answered on the record and is no longer the live "
                       "question. Answers to earlier questions are not overwritten through this "
                       f"endpoint. The round is on question {live_question_ref(curr_q)}.")
        raise HTTPException(
            status_code=409,
            detail="That answer does not match a question in this round. The round is on question "
                   f"{live_question_ref(curr_q)}; reload the session and answer that one.")

    # Save audio if uploaded. The recording is optional: a failure here costs the spoken answer and
    # the ASR it feeds, never the typed answer the candidate also submitted.
    tx = upload_store.transaction()
    audio_url = None
    clip = None
    if audio_file:
        q_num = hr.question_count + 1
        filename = f"session_{session.id}_hr_q_{q_num}_{current_user.id}.webm"
        staged = None
        try:
            audio_dir = settings.upload_dir / "hr_audio"
            audio_dir.mkdir(parents=True, exist_ok=True)
            staged = tx.stage(audio_dir, filename)
            await staged.write_from_upload(audio_file)
            clip = staged.publish()
            audio_url = f"/api/hr/audio/{filename}"
            logger.info("Saved HR spoken audio %s (session=%s question=%s)",
                        filename, session.id, q_num)
        except Exception as exc:
            # Identifiers and exception class only: the slot says which recording failed, and
            # `fault_label` keeps the absolute paths that an os-level error quotes out of this line.
            logger.warning("Failed to save HR spoken audio %s (session=%s question=%s user=%s): %s",
                           filename, session.id, q_num, current_user.id,
                           upload_store.fault_label(exc))
            if staged is not None:
                tx.discard(staged)
            audio_url = None
            clip = None

    candidate_answer = answer
    vocal_delivery = {}
    asr: dict = {}
    if clip is not None:
        transcription_res, emotion_res = await asyncio.gather(
            asyncio.to_thread(transcribe_audio, clip, "small", False),
            asyncio.to_thread(analyze_speech_emotion, clip),
            return_exceptions=True,
        )
        if not isinstance(transcription_res, Exception) and transcription_res.get("text"):
            candidate_answer = str(transcription_res["text"]).strip()
            asr = transcription_res          # word timings travel with the transcript they produced
        elif isinstance(transcription_res, Exception):
            logger.warning("HR ASR failed for %s: %s", clip, transcription_res)

        if isinstance(emotion_res, Exception):
            logger.warning("HR emotion analysis failed for %s: %s", clip, emotion_res)
        else:
            vocal_delivery = emotion_res or {}

    # How the answer was delivered, measured from the transcript and the word timings that produced
    # it. A typed answer with no recording keeps its text metrics and reports the clock ones as
    # unavailable, rather than inventing a speaking rate for words never heard.
    speech = analyze_answer(candidate_answer.strip(), asr.get("words"), asr.get("segments"),
                            question=curr_q.get("text"))

    try:
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
            "speech": speech,
            "evaluation": eval_result,
        }

        updated_questions = list(hr.questions or [])
        # One entry per question, keyed on its id and falling back to its text. The voice round answers
        # a question as soon as the candidate has spoken, while this record still shows that question
        # as the live one until the next question reaches the candidate — so a typed submit can
        # legitimately arrive for a question that is already on the record. Appending there would
        # double-count it and could complete the round on a question answered twice. Amending keeps the
        # newest answer for the live question, leaves the count alone, and lets the round advance.
        # The slot was resolved before any of this work started; a question that is not the live one
        # never reaches here.
        index = slot_index
        if index is None:
            updated_questions.append(completed_question)
        else:
            updated_questions[index] = {**updated_questions[index], **completed_question}
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
            # The report gains a delivery section; every score it already carried is untouched.
            report["speech"] = round_report_block(updated_questions)
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
    except BaseException:
        # The row did not commit, so neither may the clip it was going to describe. An identical
        # clip that already existed here is put back rather than left replaced.
        tx.rollback()
        raise
    tx.finalize()

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
        "speech": speech,
    }


@router.get("/session/{session_id}")
def get_hr_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Fetch active or saved state of an HR interview session."""
    session = owned_round_session(db, session_id, current_user, round_type="hr")

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
    session = owned_round_session(db, session_id, current_user, round_type="hr")

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


@router.get("/speech/trends")
def get_hr_speech_trends(
    limit: int = Query(default=8, ge=2, le=25),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """How this candidate's delivery has moved across their finished HR rounds, oldest first.

    Only what both compared rounds actually measured is reported, so a round recorded before speech
    analytics existed shows up under ``not_compared`` instead of reading as an improvement. Older
    rounds still give up everything their stored transcripts can prove — filler words, conciseness —
    while anything that needs the clock stays unavailable for them.
    """
    rounds = (
        db.query(SessionModel)
        .filter(SessionModel.user_id == current_user.id,
                SessionModel.round_type == "hr",
                SessionModel.status == "completed")
        .order_by(SessionModel.created_at.desc())
        .limit(limit)
        .all()
    )
    # The newest rounds, oldest first: a candidate who has practised more times than the window holds
    # has to see how their delivery is moving now, not how it started.
    rounds = sorted(rounds, key=lambda item: item.created_at or datetime.min)

    rows: list[dict] = []
    for round_session in rounds:
        hr = round_session.hr_detail
        if hr is None:
            continue
        report = round_session.report if isinstance(round_session.report, dict) else {}
        block = report.get("speech") if isinstance(report.get("speech"), dict) else None
        metrics = block.get("averages") if block else None
        if not metrics:
            reanalysed = [
                {"speech": analyze_answer(q.get("answer"), question=q.get("text"))}
                for q in (hr.questions or []) if isinstance(q, dict) and q.get("answer")
            ]
            metrics = session_metrics(reanalysed)
        if metrics:
            rows.append({"session_id": round_session.id, "metrics": metrics})

    return {
        "rounds_with_speech_data": len(rows),
        "rounds": rows,
        "compared": trends(rows),
    }


@router.get("/audio/{filename}")
def serve_hr_audio(
    filename: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FileResponse:
    """Serve one HR recording, only after proving this candidate owns the session it belongs to."""
    return audio_file_response(resolve_hr_audio_path(db, current_user, filename))
