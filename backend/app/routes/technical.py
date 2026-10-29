"""FastAPI routes for Technical Round mock interviews."""
import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database.engine import get_db
from app.models.session import Session as SessionModel
from app.models.technical import TechnicalInterview
from app.models.user import User
from app.routes.auth import get_current_user, get_optional_current_user
from app.services.emotion import analyze_speech_emotion, get_session_emotion_summary
from app.services.technical.interview_graph import interview_graph
from app.services.technical.memory import get_user_history, store_performance
from app.services.technical.rag import process_resume, retrieve_context
from app.services.technical.sentence_analysis import (
    build_sentences_from_text,
    build_sentences_from_words,
)
from app.services.transcription import transcribe_audio
from config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/technical", tags=["Technical Round"])


# ---------------------------------------------------------
# Request & Response Schemas
# ---------------------------------------------------------
class StartInterviewRequest(BaseModel):
    role: str = Field(default="Full Stack Engineer", description="Target engineering role")
    target_company: Optional[str] = Field(default=None, description="Optional target company")
    company_tier: Optional[str] = Field(
        default="tier1_product",
        description="Company calibration tier (tier1_product, growth_startup, enterprise_service, early_seed)",
    )
    max_questions: int = Field(default=5, ge=1, le=10, description="Total questions for the round")


class SubmitAnswerRequest(BaseModel):
    session_id: int = Field(description="Active session ID")
    answer: str = Field(description="Candidate's spoken or written answer")


class QuestionResponse(BaseModel):
    id: str
    text: str
    type: str


# ---------------------------------------------------------
# Route Handlers
# ---------------------------------------------------------
@router.post("/resume/upload")
async def upload_resume(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Upload PDF resume, save locally, and index embeddings into ChromaDB."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF resume files are supported.",
        )

    resume_dir = settings.resume_upload_dir
    resume_dir.mkdir(parents=True, exist_ok=True)

    dest_filename = f"user_{current_user.id}_{file.filename}"
    file_path = resume_dir / dest_filename

    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    # Update User model
    current_user.resume_path = str(file_path)
    current_user.resume_name = file.filename
    db.commit()

    # Ingest and vector-index resume into ChromaDB
    try:
        await process_resume(current_user.id, str(file_path))
    except Exception as exc:
        logger.warning("ChromaDB resume indexing warning: %s", exc)

    return {
        "status": "success",
        "message": f"Resume '{file.filename}' uploaded and indexed successfully.",
        "resume_name": file.filename,
    }


@router.get("/resume/status")
def get_resume_status(
    current_user: Optional[User] = Depends(get_optional_current_user),
) -> dict:
    """Check if current authenticated user has an active indexed resume. Guests return has_resume: False."""
    if not current_user:
        return {
            "has_resume": False,
            "resume_name": None,
        }

    has_resume = bool(
        current_user.resume_path
        and Path(current_user.resume_path).exists()
    )
    active_name = current_user.resume_name
    if has_resume and not active_name and current_user.resume_path:
        raw_name = Path(current_user.resume_path).name
        prefix = f"user_{current_user.id}_"
        active_name = raw_name[len(prefix):] if raw_name.startswith(prefix) else raw_name

    return {
        "has_resume": has_resume,
        "resume_name": active_name if has_resume else None,
    }


@router.delete("/resume")
def clear_resume(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Detach active resume from user profile so interview runs without resume grounding."""
    current_user.resume_path = None
    current_user.resume_name = None
    db.commit()
    return {
        "status": "success",
        "message": "Resume detached. Interview will run with general role questions.",
    }


@router.post("/start")
async def start_technical_interview(
    req: StartInterviewRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Start a new Technical Round interview session and generate Question 1."""
    # 1. Retrieve RAG context from resume
    resume_ctx = ""
    if current_user.resume_path:
        resume_ctx = await retrieve_context(current_user.id, req.role)

    # 2. Inject previous session weak areas from Mem0 memory
    history = await get_user_history(current_user.id)
    if history:
        resume_ctx += f"\n\nCandidate Historical Weak Areas:\n{str(history[:2])}"

    # 3. Create universal Session record
    company_tier = req.company_tier or "tier1_product"
    session = SessionModel(
        user_id=current_user.id,
        title=f"Technical Interview: {req.role}",
        description=req.target_company or "General Technical Round",
        status="in_progress",
        round_type="technical",
        duration_seconds=0.0,
        round_metadata={
            "role": req.role,
            "target_company": req.target_company,
            "company_tier": company_tier,
        },
    )
    db.add(session)
    db.flush()

    # 4. Run LangGraph node to generate initial question (Q1)
    state_input = {
        "session_id": session.id,
        "user_id": current_user.id,
        "role": req.role,
        "target_company": req.target_company,
        "company_tier": company_tier,
        "resume_context": resume_ctx,
        "questions": [],
        "current_question": None,
        "answer": None,
        "evaluation": None,
        "question_count": 0,
        "max_questions": req.max_questions,
        "is_complete": False,
        "report": None,
    }

    graph_res = await interview_graph.ainvoke(
        state_input,
        {"recursion_limit": 10},
    )

    q1 = graph_res.get("current_question") or {
        "id": "q1",
        "text": f"Can you walk me through the architecture of a major system you built as a {req.role}?",
        "type": "behavioral",
    }

    # 5. Persist TechnicalInterview state
    tech_detail = TechnicalInterview(
        session_id=session.id,
        role=req.role,
        target_company=req.target_company,
        resume_context=resume_ctx,
        max_questions=req.max_questions,
        question_count=0,
        questions=[],
        current_question=q1,
    )
    db.add(tech_detail)
    db.commit()

    return {
        "session_id": session.id,
        "role": req.role,
        "target_company": req.target_company,
        "company_tier": company_tier,
        "current_question": q1,
        "question_count": 0,
        "max_questions": req.max_questions,
        "is_complete": False,
    }


@router.post("/answer")
async def submit_technical_answer(
    session_id: int = Form(...),
    answer: str = Form(...),
    audio_file: Optional[UploadFile] = File(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Submit candidate's answer to the active question, evaluate, and fetch next question or final report."""
    session = db.get(SessionModel, session_id)
    if not session or session.round_type != "technical":
        raise HTTPException(status_code=404, detail="Technical interview session not found.")

    tech = session.technical_detail
    if not tech:
        raise HTTPException(status_code=404, detail="Technical session detail missing.")

    if not tech.current_question:
        raise HTTPException(status_code=400, detail="Interview is already completed.")

    # Save audio if uploaded
    audio_url = None
    audio_path: Optional[Path] = None
    if audio_file:
        try:
            audio_dir = settings.upload_dir / "technical_audio"
            audio_dir.mkdir(parents=True, exist_ok=True)
            q_num = (tech.question_count or 0) + 1
            filename = f"session_{session.id}_q_{q_num}_{current_user.id}.webm"
            audio_path = audio_dir / filename
            content = await audio_file.read()
            with open(audio_path, "wb") as f:
                f.write(content)
            audio_url = f"/api/technical/audio/{filename}"
            logger.info("Saved technical spoken audio: %s", audio_path)
        except Exception as exc:
            logger.warning("Failed to save spoken audio: %s", exc)
            audio_path = None

    # Server-side ASR gives deterministic sentence spans for the report. Mock
    # transcripts are disabled for graded rounds; fall back to submitted text.
    candidate_answer = answer
    answer_sentences: List[Dict[str, Any]] = []
    vocal_delivery: Dict[str, Any] = {}
    if audio_path:
        transcription_res, emotion_res = await asyncio.gather(
            asyncio.to_thread(transcribe_audio, audio_path, "small", False),
            asyncio.to_thread(analyze_speech_emotion, audio_path),
            return_exceptions=True,
        )

        if isinstance(transcription_res, Exception):
            logger.warning(
                "Technical ASR failed for %s: %s", audio_path, transcription_res
            )
        else:
            asr_text = str(transcription_res.get("text") or "").strip()
            asr_words = transcription_res.get("words") or []
            if asr_words:
                answer_sentences = build_sentences_from_words(asr_words)
            if asr_text:
                candidate_answer = asr_text

        if isinstance(emotion_res, Exception):
            logger.warning(
                "Technical emotion analysis failed for %s: %s", audio_path, emotion_res
            )
        else:
            vocal_delivery = emotion_res or {}

    if not answer_sentences:
        answer_sentences = build_sentences_from_text(candidate_answer)

    # Prepare LangGraph state
    round_meta = session.round_metadata or {}
    company_tier = round_meta.get("company_tier") or "tier1_product"
    state = {
        "session_id": session.id,
        "user_id": current_user.id,
        "role": tech.role,
        "target_company": tech.target_company,
        "company_tier": company_tier,
        "resume_context": tech.resume_context or "",
        "questions": list(tech.questions or []),
        "current_question": tech.current_question,
        "answer": candidate_answer,
        "answer_sentences": answer_sentences,
        "evaluation": None,
        "question_count": tech.question_count,
        "max_questions": tech.max_questions,
        "is_complete": False,
        "report": None,
    }

    # Step through evaluation & routing
    graph_res = await interview_graph.ainvoke(state)

    evaluation = graph_res.get("evaluation") or {"score": 7, "feedback": "Good response."}
    next_q = graph_res.get("current_question")
    is_complete = bool(graph_res.get("is_complete"))
    report = graph_res.get("report")

    # Update DB state and attach audio_url to the completed question
    updated_questions = list(graph_res.get("questions", tech.questions) or [])
    if updated_questions and audio_url:
        updated_questions[-1]["audio_url"] = audio_url
    if updated_questions:
        updated_questions[-1]["vocal_delivery"] = vocal_delivery

    tech.questions = updated_questions
    tech.question_count = graph_res.get("question_count", tech.question_count + 1)
    tech.current_question = next_q

    if is_complete and report:
        session.status = "completed"
        session.overall_score = float(report.get("total_score", 75))
        report["vocal_delivery"] = get_session_emotion_summary(
            session.id, fallback=vocal_delivery
        )
        session.report = report

        # Store Mem0 cross-session memory
        await store_performance(
            current_user.id,
            {
                "role": tech.role,
                "total_score": session.overall_score,
                "strengths": report.get("strengths", []),
                "weaknesses": report.get("weaknesses", []),
            },
        )

    db.commit()

    return {
        "session_id": session.id,
        "evaluation": evaluation,
        "next_question": next_q,
        "is_complete": is_complete,
        "report": report,
        "question_count": tech.question_count,
        "max_questions": tech.max_questions,
        "audio_url": audio_url,
        "vocal_delivery": vocal_delivery,
    }


@router.get("/session/{session_id}")
def get_technical_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Fetch active state of a technical interview for live studio or resume."""
    session = db.get(SessionModel, session_id)
    if not session or session.round_type != "technical":
        raise HTTPException(status_code=404, detail="Technical interview not found.")

    tech = session.technical_detail
    round_meta = session.round_metadata or {}
    return {
        "session_id": session.id,
        "role": tech.role if tech else "Technical Interview",
        "target_company": tech.target_company if tech else None,
        "company_tier": round_meta.get("company_tier", "tier1_product"),
        "current_question": tech.current_question if tech else None,
        "question_count": tech.question_count if tech else 0,
        "max_questions": tech.max_questions if tech else 5,
        "is_complete": session.status == "completed",
        "questions": tech.questions if tech else [],
        "report": session.report,
        "overall_score": session.overall_score,
    }


@router.get("/report/{session_id}")
def get_technical_report(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Fetch finalized technical interview scorecard and recommendations."""
    session = db.get(SessionModel, session_id)
    if not session or session.round_type != "technical":
        raise HTTPException(status_code=404, detail="Technical session not found.")

    if not session.report:
        raise HTTPException(status_code=400, detail="Report has not been generated for this session yet.")

    tech = session.technical_detail
    round_meta = session.round_metadata or {}
    return {
        "session_id": session.id,
        "role": tech.role if tech else "Software Engineer",
        "target_company": tech.target_company if tech else None,
        "company_tier": round_meta.get("company_tier", "tier1_product"),
        "overall_score": session.overall_score,
        "report": session.report,
        "questions": tech.questions if tech else [],
        "created_at": session.created_at.isoformat() if session.created_at else None,
    }


@router.get("/audio/{filename}")
def stream_technical_audio(filename: str):
    """Safely stream recorded candidate audio file."""
    from fastapi.responses import FileResponse
    # Clean filename to avoid path traversal
    safe_name = Path(filename).name
    file_path = settings.upload_dir / "technical_audio" / safe_name
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Audio recording not found.")
    return FileResponse(file_path, media_type="audio/webm")

