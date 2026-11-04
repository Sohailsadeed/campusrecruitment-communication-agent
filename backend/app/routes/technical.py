"""FastAPI routes for Technical Round mock interviews."""
import asyncio
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database.engine import get_db
from app.models.session import Session as SessionModel
from app.models.technical import TechnicalInterview
from app.models.user import User
from app.routes.auth import get_current_user, get_optional_current_user
from app.services import upload_store
from app.services.audio_ownership import audio_file_response, resolve_technical_audio_path
from app.services.emotion import analyze_speech_emotion, get_session_emotion_summary
from app.services.hr.hr_service import question_ref as live_question_ref
from app.services.hr.hr_service import resolve_answer_slot
from app.services.technical.evaluator import EvaluationUnavailable
from app.services.technical.interview_graph import interview_graph
from app.services.technical.memory import get_user_history, store_performance
from app.services.technical.rag import process_resume, retrieve_context
from app.services.technical.round_evaluation import evaluate_round
from app.services.technical.sentence_analysis import (
    build_sentences_from_text,
    build_sentences_from_words,
)
from app.services.transcription import transcribe_audio
from app.services.session_ownership import owned_round_session
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

    # The stored name comes from the authenticated user, never from the client, so no separator,
    # traversal or duplicate of another candidate's name can ever become a path here. One PDF per
    # user is what the profile supports, so one slot per user is what the filesystem needs. The
    # candidate's own filename survives only as display metadata in `resume_name`.
    dest_filename = f"user_{current_user.id}.pdf"

    tx = upload_store.transaction()
    try:
        staged = tx.stage(resume_dir, dest_filename)
        await staged.write_from_upload(file)
        file_path = staged.publish()

        # Update User model
        current_user.resume_path = str(file_path)
        current_user.resume_name = file.filename
        db.commit()
    except BaseException:
        # The profile still points at the PDF it pointed at before this request, which is the PDF
        # this request displaced and then put back.
        tx.rollback()
        raise
    tx.finalize()

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
    question_ref: Optional[str] = Form(default=None),
    audio_file: Optional[UploadFile] = File(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Store one answer and acknowledge it without transcribing, scoring or generating anything.

    `question_ref` names the question being answered (its id, or its text) and may be left empty, which
    means the live question. Only the live question is written: an answer naming a question the round has
    already moved past is refused with 409 before the clip is staged or the transcript is read, so a
    retried submit cannot land as a second entry for one question.

    Everything the candidate does not need this second is deferred: transcription and vocal delivery to
    `POST /api/technical/process/{session_id}`, the next question to `POST /api/technical/question/{session_id}`,
    and the scoring to `POST /api/technical/evaluate/{session_id}`. The answer is stored with
    `processing: "pending"`, so the work survives a restart: nothing is handed to a background task that
    could be lost with the request. `next_question` is null here for exactly that reason, and `evaluation`
    and `report` are null by design.
    """
    session = owned_round_session(db, session_id, current_user, round_type="technical")

    tech = session.technical_detail
    if not tech:
        raise HTTPException(status_code=404, detail="Technical session detail missing.")

    if not tech.current_question:
        # Reached two ways, and the candidate-facing difference matters: a scored round, and a round
        # whose answers are all queued but whose report has not been produced. Both answer the same
        # way -- `POST /api/technical/evaluate/{session_id}` -- which returns the stored report for the
        # first and produces it for the second. Wording it as "already completed" would tell a
        # candidate whose last submit was lost that there is nothing left to do.
        raise HTTPException(
            status_code=400,
            detail="No question is open for this round. Request the final evaluation to score the "
                   "answers already submitted.")

    curr_q = tech.current_question

    slot, slot_index = resolve_answer_slot(curr_q, tech.questions or [], question_ref)
    if slot != "live":
        # Nothing has been stored, transcribed or uploaded: a rejected submit leaves no trace, so a
        # retried one cannot land as a second entry for the same question.
        logger.info("Rejected technical answer for session %s (question_ref=%r is %s, live=%r)",
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

    # Save audio if uploaded. The recording is optional: a failure here costs the transcript and the
    # vocal-delivery report, never the submitted text answer, which is stored either way.
    tx = upload_store.transaction()
    audio_url = None
    audio_number: Optional[int] = None
    if audio_file:
        q_num = (tech.question_count or 0) + 1
        filename = f"session_{session.id}_q_{q_num}_{current_user.id}.webm"
        staged = None
        try:
            audio_dir = settings.upload_dir / "technical_audio"
            audio_dir.mkdir(parents=True, exist_ok=True)
            staged = tx.stage(audio_dir, filename)
            await staged.write_from_upload(audio_file)
            staged.publish()
            audio_url = f"/api/technical/audio/{filename}"
            # Only the question number travels with the answer. The process pass rebuilds the same
            # filename from it and the owner's id, so no stored field can point at another path, and the
            # playback grammar and its authorization stay the single source of truth they already are.
            audio_number = q_num
            logger.info("Saved technical spoken audio %s (session=%s question=%s)",
                        filename, session.id, q_num)
        except Exception as exc:
            # Identifiers and exception class only — see the same note in hr.py's answer handler.
            logger.warning("Failed to save spoken audio %s (session=%s question=%s user=%s): %s",
                           filename, session.id, q_num, current_user.id,
                           upload_store.fault_label(exc))
            if staged is not None:
                tx.discard(staged)
            audio_url = None
            audio_number = None

    try:
        round_meta = session.round_metadata or {}
        company_tier = round_meta.get("company_tier") or "tier1_product"
        state = {
            "session_id": session.id,
            "user_id": current_user.id,
            "request": "record_answer",
            "role": tech.role,
            "target_company": tech.target_company,
            "company_tier": company_tier,
            "resume_context": tech.resume_context or "",
            "questions": list(tech.questions or []),
            "current_question": tech.current_question,
            "answer": answer,
            # Sentence spans from the submitted text are cheap and deterministic, so the answer is stored
            # with them now; the process pass replaces them with the timed spans from the recording.
            "answer_sentences": build_sentences_from_text(answer),
            "audio_url": audio_url,
            "audio_question_number": audio_number,
            "vocal_delivery": {},
            "amend_index": slot_index,
            "evaluation": None,
            "question_count": tech.question_count,
            "max_questions": tech.max_questions,
            "is_complete": False,
            "report": None,
        }

        # Store the answer and close the request. No transcription, no scoring, no question generation:
        # all three are the process pass's work, and `next_question` is null until it has run.
        graph_res = await interview_graph.ainvoke(state)

        updated_questions = list(graph_res.get("questions", tech.questions) or [])
        next_q = graph_res.get("current_question")
        is_complete = bool(graph_res.get("is_complete"))

        tech.questions = updated_questions
        tech.question_count = graph_res.get("question_count", tech.question_count + 1)
        tech.current_question = next_q

        db.commit()
    except BaseException:
        # The row did not commit, so this clip belongs to no recorded answer. A previous clip in
        # this question's slot is restored rather than left replaced.
        tx.rollback()
        raise
    tx.finalize()

    return {
        "session_id": session.id,
        "evaluation": None,
        "next_question": next_q,
        "is_complete": is_complete,
        "report": None,
        "question_count": tech.question_count,
        "max_questions": tech.max_questions,
        "audio_url": audio_url,
        "vocal_delivery": {},
    }


# ---------------------------------------------------------------------------
# Deferred processing
# ---------------------------------------------------------------------------
# A claim is a lease, not a lock held across the transcription: an answer whose worker died stays
# `running` only until this window passes, after which it is claimable again. Comfortably longer than a
# real Whisper + prosody pass on one answer, short enough that a restart mid-analysis costs the candidate
# a wait rather than the round.
CLAIM_STALE_AFTER_SEC = 600.0


def _processing_state(entry: Any) -> str:
    if not isinstance(entry, dict):
        return ""
    return str(entry.get("processing") or "pending")


def _answer_is_unsettled(entry: Any) -> bool:
    """Anything but a finished pass: the final evaluation waits on all of these states."""
    return isinstance(entry, dict) and _processing_state(entry) != "done"


def _answer_is_claimable(entry: Any, now: float) -> bool:
    """Whether this pass may take the answer: owed, previously failed, or a lease nobody renewed.

    A fresh `running` claim is deliberately not claimable -- that is what keeps two overlapping requests
    (a background analysis kick and the one the report waits on) from transcribing the same clip twice and
    from one overwriting the other's result.
    """
    if not isinstance(entry, dict):
        return False
    state = _processing_state(entry)
    if state in ("pending", "failed"):
        return True
    if state == "running":
        claimed_at = entry.get("processing_claimed_at")
        return isinstance(claimed_at, (int, float)) and (now - float(claimed_at)) > CLAIM_STALE_AFTER_SEC
    return False


def _claim_unprocessed_answers(
    db: Session, tech: TechnicalInterview
) -> List[tuple[int, Dict[str, Any]]]:
    """Short locked transaction that moves every claimable answer to `running` under one lease token.

    Returns the claimed (index, entry) pairs. The claim commits on its own, so the transaction is over
    before Whisper starts -- no database connection is held for the length of an analysis.
    """
    now = time.time()
    row = (
        db.query(TechnicalInterview)
        .filter(TechnicalInterview.id == tech.id)
        .with_for_update()
        .one_or_none()
    )
    if row is None:
        db.rollback()
        return []
    entries = [dict(e) if isinstance(e, dict) else e for e in (row.questions or [])]
    claimed: List[tuple[int, Dict[str, Any]]] = []
    for index, entry in enumerate(entries):
        if _answer_is_claimable(entry, now):
            leased = {**entry, "processing": "running", "processing_claimed_at": now}
            entries[index] = leased
            claimed.append((index, leased))
    if not claimed:
        db.rollback()
        return []
    row.questions = entries
    db.commit()
    return claimed


def _publish_answer_result(
    db: Session, tech: TechnicalInterview, index: int, claimed: Dict[str, Any], updated: Dict[str, Any]
) -> bool:
    """Write one analysis result back only if the answer is still the take this pass claimed.

    The lease token is the compare-and-swap value: an amend that landed meanwhile reset the entry to
    `pending`, and another worker's claim carries a different token. Either way the newer state on the
    record wins and this result is dropped, so no stale transcript can overwrite a newer answer.
    """
    row = (
        db.query(TechnicalInterview)
        .filter(TechnicalInterview.id == tech.id)
        .with_for_update()
        .one_or_none()
    )
    if row is None:
        db.rollback()
        return False
    entries = list(row.questions or [])
    if index >= len(entries) or not isinstance(entries[index], dict):
        db.rollback()
        return False
    current = entries[index]
    if (
        _processing_state(current) != "running"
        or current.get("processing_claimed_at") != claimed.get("processing_claimed_at")
    ):
        logger.info(
            "Discarded stale technical analysis result for session %s answer %s", tech.id, index + 1
        )
        db.rollback()
        return False
    entries[index] = {**updated, "processing_claimed_at": None}
    row.questions = entries
    db.commit()
    return True


async def _process_one_answer(
    db: Session, current_user: User, session_id: int, entry: Dict[str, Any]
) -> Dict[str, Any]:
    """Transcribe and analyse one stored answer, or record precisely why it could not be.

    The clip is named from the answer's `audio_question_number` using the same grammar the playback
    route authorizes with, and resolved through that route's own helper -- so this pass reaches no path
    the candidate could not already reach, and a question keeps its own recording across retries.
    """
    answer = str(entry.get("answer") or "")
    audio_number = entry.get("audio_question_number")

    if audio_number is None:
        # A typed answer has no clip to transcribe. Text-derived spans and no vocal delivery are the
        # whole result here, not a partial one, so this is a clean finish rather than a failure.
        return {
            **entry,
            "sentences": entry.get("sentences") or build_sentences_from_text(answer),
            "vocal_delivery": entry.get("vocal_delivery") or {},
            "processing": "done",
            "processing_error": None,
        }

    filename = f"session_{session_id}_q_{audio_number}_{current_user.id}.webm"
    faults: List[str] = []
    try:
        audio_path = resolve_technical_audio_path(db, current_user, filename)
    except HTTPException:
        # The helper answers 404 for "absent, unreadable or not this round's clip", and logs no path.
        logger.warning(
            "Technical recording unavailable for session %s question %s", session_id, audio_number
        )
        faults.append("recording unavailable")
        audio_path = None

    transcription_res: Any = None
    emotion_res: Any = None
    if audio_path is not None:
        transcription_res, emotion_res = await asyncio.gather(
            asyncio.to_thread(transcribe_audio, audio_path, "small", False),
            asyncio.to_thread(analyze_speech_emotion, audio_path),
            return_exceptions=True,
        )

    updated = dict(entry)

    if audio_path is not None:
        if isinstance(transcription_res, Exception):
            # An ASR crash is the one fault that can leave a spoken answer looking finished while its
            # timed spans and delivery are quietly missing, so the answer stays `failed` and retryable.
            logger.warning(
                "Technical ASR failed for session %s question %s: %s",
                session_id,
                audio_number,
                transcription_res,
            )
            faults.append(f"transcription failed ({type(transcription_res).__name__})")
        else:
            asr_text = str((transcription_res or {}).get("text") or "").strip()
            asr_words = (transcription_res or {}).get("words") or []
            if asr_text:
                # The transcript replaces the submitted text as the answer on the record, exactly as the
                # synchronous pass did, so the report reads what was spoken.
                updated["answer"] = asr_text
                updated["sentences"] = (
                    build_sentences_from_words(asr_words)
                    if asr_words
                    else build_sentences_from_text(asr_text)
                )
            else:
                # No exception and no speech: a silent or unintelligible take. The candidate's own typed
                # answer and its text-derived spans stay on the record -- inventing a transcript would be
                # the misleading part, not this.
                logger.info(
                    "Technical ASR returned no speech for session %s question %s; keeping submitted text",
                    session_id,
                    audio_number,
                )
                updated["sentences"] = updated.get("sentences") or build_sentences_from_text(answer)

        if isinstance(emotion_res, Exception):
            # `analyze_speech_emotion` swallows its own faults and returns a neutral profile, so getting
            # here means the call itself died. Losing the delivery section is visible in the report as an
            # absent section; it is not worth holding the whole round hostage for.
            logger.warning(
                "Technical emotion analysis failed for session %s question %s: %s",
                session_id,
                audio_number,
                emotion_res,
            )
            updated["vocal_delivery"] = {}
        else:
            updated["vocal_delivery"] = emotion_res or {}

    updated["sentences"] = updated.get("sentences") or build_sentences_from_text(
        str(updated.get("answer") or "")
    )
    updated["processing"] = "failed" if faults else "done"
    # Exception class and situation only: no filesystem path, and nothing the client cannot be told.
    updated["processing_error"] = "; ".join(faults) if faults else None
    return updated


@router.post("/process/{session_id}")
async def process_technical_round(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Transcribe and analyse the recordings already on the record -- and nothing else.

    This is the recoverable half of the split submission, and it is deliberately kept away from the
    question path: Whisper and the prosody pass never delay what the candidate reads next. The queue is
    not a task table or an in-memory background job -- it is the `processing` field inside
    `tech.questions`, committed with the answer itself. A server restart mid-request leaves those answers
    `pending`, and the next call to this endpoint does the work; an answer that failed says `failed`, and
    a retry re-runs only it.

    Work is taken under a lease (see `_claim_unprocessed_answers`), so two overlapping calls -- the one the
    studio fires after a submit and the one the report waits on -- cannot transcribe the same clip twice or
    let the earlier result land over a newer answer.
    """
    session = owned_round_session(db, session_id, current_user, round_type="technical")

    tech = session.technical_detail
    if not tech:
        raise HTTPException(status_code=404, detail="Technical session detail missing.")

    claimed = _claim_unprocessed_answers(db, tech)

    errors: List[str] = []
    for index, entry in claimed:
        updated = await _process_one_answer(db, current_user, session.id, entry)
        if not _publish_answer_result(db, tech, index, entry, updated):
            # Someone else holds this answer now, or the candidate amended it. Either way their state is
            # the one on the record and this pass reports what is still outstanding, not a fabricated done.
            continue
        if updated.get("processing") == "failed":
            errors.append(f"question {index + 1}: {updated.get('processing_error')}")

    questions = list(tech.questions or [])
    max_questions = int(tech.max_questions or 5)
    unsettled = [q for q in questions if _answer_is_unsettled(q)]
    in_others_hands = any(_processing_state(q) == "running" for q in unsettled)
    status = "done"
    if unsettled:
        status = "running" if (in_others_hands and not errors) else "retry"

    return {
        "session_id": session.id,
        "next_question": tech.current_question,
        "question_count": len(questions),
        "max_questions": max_questions,
        "is_complete": len(questions) >= max_questions,
        # "done"  -> every answer analysed, the report may run.
        # "retry" -> at least one answer failed or is still owed; `errors` says which and why, and this
        #            same call is the retry.
        # "running" -> nothing failed, but another request's lease covers the outstanding work, so this
        #            call did not duplicate it. The evaluation still refuses until those land.
        "processing": status,
        "errors": errors,
        "unprocessed": [i + 1 for i, q in enumerate(questions) if _answer_is_unsettled(q)],
    }


@router.post("/question/{session_id}")
async def request_technical_question(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Return the question the candidate should answer now, generating it if none is open.

    The only model call on this path is the existing question generator, so the next question is as fast as
    that generator and waits on no transcription or emotion analysis. `tech.current_question` being null
    while answers remain unasked is itself the durable marker for the owed question: a reload or a restart
    between the submit and this call finds the same state, and the answers already stored are the generator's
    own context, so its ordering and no-repeat behaviour are unchanged.
    """
    session = owned_round_session(db, session_id, current_user, round_type="technical")

    tech = session.technical_detail
    if not tech:
        raise HTTPException(status_code=404, detail="Technical session detail missing.")

    questions = list(tech.questions or [])
    max_questions = int(tech.max_questions or 5)
    is_complete = len(questions) >= max_questions
    next_q = tech.current_question

    if next_q is None and questions and not is_complete:
        round_meta = session.round_metadata or {}
        graph_res = await interview_graph.ainvoke(
            {
                "session_id": session.id,
                "user_id": current_user.id,
                "request": "next_question",
                "role": tech.role,
                "target_company": tech.target_company,
                "company_tier": round_meta.get("company_tier") or "tier1_product",
                "resume_context": tech.resume_context or "",
                "questions": questions,
                "current_question": None,
                "is_complete": False,
            }
        )
        next_q = graph_res.get("current_question")
        if next_q is not None:
            tech.current_question = next_q
            tech.question_count = len(questions)
            db.commit()

    return {
        "session_id": session.id,
        "next_question": next_q,
        "question_count": len(questions),
        "max_questions": max_questions,
        "is_complete": is_complete,
    }


@router.post("/evaluate/{session_id}")
async def evaluate_technical_round(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Score the complete round in one pass and publish its report.

    Run once, after the last answer is queued. The in-round fallback scores (`6` for an answer, `75` for
    a report) exist so a live round keeps moving when one answer cannot be graded; a finished round is the
    opposite case, so this pass refuses them. When the model is unavailable the session stays
    `in_progress`, every answer stays on the record, and the caller gets a retryable 503 -- nothing is
    marked completed on a report the model never produced.

    A round that already carries a persisted report returns it as-is, so a retry after a lost response
    neither pays for a second evaluation nor is shown a different score.
    """
    session = owned_round_session(db, session_id, current_user, round_type="technical")

    tech = session.technical_detail
    if not tech:
        raise HTTPException(status_code=404, detail="Technical session detail missing.")

    questions = list(tech.questions or [])

    if session.report and session.status == "completed":
        return _round_report_response(session, tech, questions)

    remaining = max(0, int(tech.max_questions or 0) - len(questions))
    if tech.current_question or remaining:
        raise HTTPException(
            status_code=409,
            detail=f"The round still has {remaining} unanswered question(s). Answer them, or reload "
                   "the session, before requesting the final report.")

    # Every deferred transcript and delivery analysis has to be on the record first: an answer still
    # `pending` or `running` would be graded on the typed text alone, and a `failed` one on nothing at all.
    # All three land in the same retryable state -- the process endpoint re-runs exactly those answers.
    unprocessed = [i + 1 for i, entry in enumerate(questions) if _answer_is_unsettled(entry)]
    if unprocessed:
        listed = ", ".join(str(n) for n in unprocessed)
        logger.warning(
            "Technical round evaluation refused for session %s: answers %s unprocessed",
            session.id,
            listed,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"The recording analysis for question(s) {listed} has not finished. Nothing is "
                   "scored yet and no answers are lost — retry the processing step, then the report.",
        )

    try:
        result = await evaluate_round(
            questions,
            role=tech.role,
            resume_context=tech.resume_context or "",
        )
    except EvaluationUnavailable as exc:
        # Answers stay saved and the session stays open: the candidate retries this same call.
        logger.warning("Technical round evaluation failed for session %s: %s", session.id, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The final evaluation could not be completed right now. Every answer is saved and "
                   "this round is still open — retry to generate the report.",
        ) from exc

    scored = result["questions"]
    report = result["report"]
    report["vocal_delivery"] = get_session_emotion_summary(
        session.id, fallback=scored[-1].get("vocal_delivery") or {}
    )

    # One commit holds the whole result: the score list, the report and the completed status land
    # together, or the round stays open and retryable.
    tech.questions = scored
    tech.question_count = len(scored)
    tech.current_question = None
    session.report = report
    session.overall_score = float(report["total_score"])
    session.status = "completed"
    db.commit()

    await store_performance(
        current_user.id,
        {
            "role": tech.role,
            "total_score": session.overall_score,
            "strengths": report.get("strengths", []),
            "weaknesses": report.get("weaknesses", []),
        },
    )

    return _round_report_response(session, tech, scored)


def _round_report_response(session: SessionModel, tech: TechnicalInterview,
                           questions: List[Dict[str, Any]]) -> dict:
    """The shape a finished round reports, whether it was just scored or read back from the record."""
    return {
        "session_id": session.id,
        "report": session.report,
        "overall_score": session.overall_score,
        "questions": questions,
        "question_count": tech.question_count,
        "max_questions": tech.max_questions,
        "is_complete": session.status == "completed",
    }


@router.get("/session/{session_id}")
def get_technical_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Fetch active state of a technical interview for live studio or resume."""
    session = owned_round_session(db, session_id, current_user, round_type="technical")

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
    session = owned_round_session(db, session_id, current_user, round_type="technical")

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
def serve_technical_audio(
    filename: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FileResponse:
    """Serve one Technical recording, only after proving this candidate owns the session it belongs to."""
    return audio_file_response(resolve_technical_audio_path(db, current_user, filename))

