"""LangGraph state machine orchestrating technical interview progression."""
import logging
from typing import Any, Dict, List, Literal, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from app.services.technical.evaluator import generate_question

logger = logging.getLogger(__name__)


class InterviewState(TypedDict):
    """LangGraph state representing an active technical interview session."""
    session_id: int | str
    user_id: int | str
    role: str
    target_company: Optional[str]
    company_tier: Optional[str]
    resume_context: str
    questions: List[Dict[str, Any]]
    current_question: Optional[Dict[str, Any]]
    answer: Optional[str]
    answer_sentences: Optional[List[Dict[str, Any]]]
    audio_url: Optional[str]
    audio_question_number: Optional[int]
    vocal_delivery: Optional[Dict[str, Any]]
    amend_index: Optional[int]
    request: Optional[str]
    evaluation: Optional[Dict[str, Any]]
    question_count: int
    max_questions: int
    is_complete: bool
    report: Optional[Dict[str, Any]]


# ---------------------------------------------------------------------------
# LangGraph Nodes
# ---------------------------------------------------------------------------
async def generate_first_question_node(state: InterviewState) -> Dict[str, Any]:
    """Generate the initial question (Q1) grounded in target role, company calibration, and resume."""
    logger.info(
        "LangGraph Node: generate_first_question for session %s (tier=%s, company=%s)",
        state.get("session_id"),
        state.get("company_tier"),
        state.get("target_company"),
    )
    question = await generate_question(
        role=state["role"],
        resume_context=state.get("resume_context", ""),
        questions_asked=[],
        target_company=state.get("target_company"),
        company_tier=state.get("company_tier", "tier1_product"),
    )
    question["id"] = "q1"
    return {
        "current_question": question,
        "question_count": 0,
        "is_complete": False,
        "questions": [],
    }


async def record_answer_node(state: InterviewState) -> Dict[str, Any]:
    """Acknowledge the submitted answer: store it and mark it for processing. Nothing is analysed here.

    Three expensive passes sit between an answer and a report — transcription of the recording, the
    vocal-delivery read of it, and the model's scoring of the round. All three are off this path now: the
    entry lands with `processing: "pending"`, and the route's process pass fills in the transcript, the
    word spans and the delivery from the clip named by `audio_question_number`. `evaluated: False` says the
    scores are still missing rather than pretending they are merely absent.

    `amend_index` comes from the route's slot resolution: one entry per question, so a re-submitted live
    answer replaces its own record instead of doubling the count.
    """
    logger.info("LangGraph Node: record_answer for session %s", state.get("session_id"))
    curr_q = state.get("current_question") or {
        "id": f"q{state.get('question_count', 0) + 1}",
        "text": "Interview Question",
        "type": "behavioral",
    }

    recorded_question = {
        **curr_q,
        "answer": state.get("answer") or "",
        "sentences": state.get("answer_sentences") or [],
        "audio_url": state.get("audio_url"),
        "audio_question_number": state.get("audio_question_number"),
        "vocal_delivery": state.get("vocal_delivery") or {},
        "processing": "pending",
        "processing_error": None,
        # An amend lands as a fresh take: any lease the previous analysis was holding is dropped, so that
        # worker's late result can no longer overwrite this answer.
        "processing_claimed_at": None,
        "evaluated": False,
    }

    questions = list(state.get("questions", []))
    amend_index = state.get("amend_index")
    if amend_index is not None and 0 <= amend_index < len(questions):
        previous = questions[amend_index]
        # A re-submit that carries no recording keeps the clip already on the record, so correcting the
        # text of an answer cannot orphan the recording that was made for it. The delivery figures stay
        # with it because they describe that recording; a *new* clip brings neither, and the old ones
        # would otherwise be read out against audio the candidate replaced.
        if recorded_question["audio_url"] is None:
            recorded_question["audio_url"] = previous.get("audio_url")
            recorded_question["audio_question_number"] = previous.get("audio_question_number")
            if previous.get("vocal_delivery"):
                recorded_question["vocal_delivery"] = previous["vocal_delivery"]
        questions[amend_index] = {**previous, **recorded_question}
    else:
        questions.append(recorded_question)

    return {
        "questions": questions,
        "evaluation": None,
        "question_count": len(questions),
        # Asking the next question is not this request's job any more: the process pass generates it, so
        # an answer is acknowledged as soon as it is stored.
        "current_question": None,
        "is_complete": len(questions) >= state.get("max_questions", 5),
    }


async def generate_next_question_node(state: InterviewState) -> Dict[str, Any]:
    """Generate subsequent conversational questions, preventing repetition."""
    logger.info(
        "LangGraph Node: generate_next_question for session %s (tier=%s)",
        state.get("session_id"),
        state.get("company_tier"),
    )
    questions = state.get("questions", [])
    next_q = await generate_question(
        role=state["role"],
        resume_context=state.get("resume_context", ""),
        questions_asked=questions,
        target_company=state.get("target_company"),
        company_tier=state.get("company_tier", "tier1_product"),
    )
    next_q["id"] = f"q{len(questions) + 1}"
    return {
        "current_question": next_q,
        "answer": None,
        "answer_sentences": None,
        "audio_url": None,
        "vocal_delivery": None,
        "amend_index": None,
        "evaluation": None,
        "is_complete": False,
    }


async def finish_round_node(state: InterviewState) -> Dict[str, Any]:
    """Close the submit request: the answer is stored, no question is open, nothing is scored yet.

    `is_complete` is the comparison `record_answer_node` already made between the answer count and
    `max_questions`, so a mid-round submit ends with the round open and its next question left for the
    process pass to generate. Only the last answer of the round closes it.

    The report is deliberately not produced here. A round that has run out of questions has not yet been
    transcribed or evaluated, and `report: None` says exactly that — the route's process and evaluation
    passes turn it into a completed session, or leave it open when the model cannot deliver a report.
    """
    logger.info("LangGraph Node: finish_round for session %s", state.get("session_id"))
    return {
        "current_question": None,
        "answer": None,
        "evaluation": None,
        "report": None,
        "is_complete": bool(state.get("is_complete")),
    }


# ---------------------------------------------------------------------------
# Routing Logic
# ---------------------------------------------------------------------------
def route_entrypoint(state: InterviewState) -> str:
    """Where to enter: open the round, acknowledge an answer, or ask the next question.

    `request` names which of those the caller needs. Only `next_question` is a model call that is *not*
    the answer's own: it is what the process pass asks for after the answer is already stored, so the
    candidate's submit is never held up by question generation.
    """
    request = state.get("request")
    if request == "record_answer":
        return "record_answer"
    if request == "next_question":
        return "generate_next_question"
    if state.get("answer"):
        return "record_answer"
    return "generate_first_question"


# ---------------------------------------------------------------------------
# State Graph Construction
# ---------------------------------------------------------------------------
def _build_interview_graph():
    builder = StateGraph(InterviewState)

    builder.add_node("generate_first_question", generate_first_question_node)
    builder.add_node("record_answer", record_answer_node)
    builder.add_node("generate_next_question", generate_next_question_node)
    builder.add_node("finish_round", finish_round_node)

    builder.add_conditional_edges(
        START,
        route_entrypoint,
        {
            "generate_first_question": "generate_first_question",
            "record_answer": "record_answer",
            "generate_next_question": "generate_next_question",
        },
    )

    builder.add_edge("record_answer", "finish_round")
    builder.add_edge("generate_first_question", END)
    builder.add_edge("generate_next_question", END)
    builder.add_edge("finish_round", END)

    return builder.compile()


interview_graph = _build_interview_graph()
