"""LangGraph state machine orchestrating technical interview progression."""
import logging
from typing import Any, Dict, List, Literal, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from app.services.technical.evaluator import (
    evaluate_answer,
    generate_question,
    generate_report,
)

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


async def evaluate_answer_node(state: InterviewState) -> Dict[str, Any]:
    """Evaluate candidate's answer against the current question and resume context."""
    logger.info("LangGraph Node: evaluate_answer for session %s", state.get("session_id"))
    curr_q = state.get("current_question") or {
        "id": f"q{state.get('question_count', 0) + 1}",
        "text": "Interview Question",
        "type": "behavioral",
    }
    answer = state.get("answer") or ""

    evaluation = await evaluate_answer(
        question=curr_q,
        answer=answer,
        resume_context=state.get("resume_context", ""),
        sentences=state.get("answer_sentences"),
    )

    completed_question = {
        **curr_q,
        "answer": answer,
        "score": evaluation.get("score", 7),
        "feedback": evaluation.get("feedback", "Good response."),
        "conciseness_score": evaluation.get("conciseness_score", 8),
        "rambling_detected": evaluation.get("rambling_detected", False),
        "rambling_critique": evaluation.get("rambling_critique", "Direct delivery."),
        "jargon_vs_understanding": evaluation.get("jargon_vs_understanding", "applied_intuition"),
        "applied_understanding_score": evaluation.get("applied_understanding_score", 8),
        "jargon_critique": evaluation.get("jargon_critique", "Explained with applied intuition."),
        "star_breakdown": evaluation.get("star_breakdown", {}),
        "ideal_concise_script": evaluation.get("ideal_concise_script", ""),
        "conclusion_checkpoint_index": evaluation.get("conclusion_checkpoint_index"),
        "sentences": evaluation.get("sentences", []),
    }

    questions = list(state.get("questions", []))
    questions.append(completed_question)
    q_count = state.get("question_count", 0) + 1

    return {
        "questions": questions,
        "evaluation": evaluation,
        "question_count": q_count,
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
        "evaluation": None,
        "is_complete": False,
    }


async def generate_report_node(state: InterviewState) -> Dict[str, Any]:
    """Compile final interview performance report and score when round is complete."""
    logger.info("LangGraph Node: generate_report for session %s", state.get("session_id"))
    questions = state.get("questions", [])
    report = await generate_report(
        questions_asked=questions,
        role=state["role"],
    )
    return {
        "report": report,
        "is_complete": True,
        "current_question": None,
    }


# ---------------------------------------------------------------------------
# Routing Logic
# ---------------------------------------------------------------------------
def route_after_evaluation(state: InterviewState) -> Literal["generate_next_question", "generate_report"]:
    """Determine whether to ask next question or compile final report."""
    q_count = state.get("question_count", 0)
    max_q = state.get("max_questions", 5)
    if q_count >= max_q:
        return "generate_report"
    return "generate_next_question"


def route_entrypoint(state: InterviewState) -> str:
    if state.get("answer"):
        return "evaluate_answer"
    return "generate_first_question"


# ---------------------------------------------------------------------------
# State Graph Construction
# ---------------------------------------------------------------------------
def _build_interview_graph():
    builder = StateGraph(InterviewState)

    builder.add_node("generate_first_question", generate_first_question_node)
    builder.add_node("evaluate_answer", evaluate_answer_node)
    builder.add_node("generate_next_question", generate_next_question_node)
    builder.add_node("generate_report", generate_report_node)

    builder.add_conditional_edges(
        START,
        route_entrypoint,
        {
            "generate_first_question": "generate_first_question",
            "evaluate_answer": "evaluate_answer",
        },
    )

    builder.add_conditional_edges(
        "evaluate_answer",
        route_after_evaluation,
        {
            "generate_next_question": "generate_next_question",
            "generate_report": "generate_report",
        },
    )

    builder.add_edge("generate_first_question", END)
    builder.add_edge("generate_next_question", END)
    builder.add_edge("generate_report", END)

    return builder.compile()


interview_graph = _build_interview_graph()
