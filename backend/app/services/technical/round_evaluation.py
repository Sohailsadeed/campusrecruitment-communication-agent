"""Score a finished technical round in one pass, and fail loudly when the model cannot.

The live round no longer scores anything: `record_answer_node` in `interview_graph.py` queues each
answer and moves on, so the candidate waits for the next question only. This module is the other half
— the whole interview evaluated once, after the last answer.

Nothing here invents a number. `strict=True` on both calls means an unavailable model or an
unparseable response raises `EvaluationUnavailable` rather than the in-round fallback score, and the
route turns that into a retryable failure with the session still open.
"""
import logging
from typing import Any, Dict, List

from app.services.technical.evaluator import evaluate_answer, generate_report

logger = logging.getLogger(__name__)


async def evaluate_round(questions: List[Dict[str, Any]], *, role: str,
                         resume_context: str) -> Dict[str, Any]:
    """Evaluate every queued answer, then write the round report over those evaluations.

    Returns ``{"questions": [each answer with its scores], "report": {...}}``. The report is built
    from the same scored questions the studio's per-question panels show, so no number in it comes
    from a different place than the one the candidate can read.
    """
    scored: List[Dict[str, Any]] = []
    for question in questions:
        evaluation = await evaluate_answer(
            question=question,
            answer=str(question.get("answer") or ""),
            resume_context=resume_context,
            sentences=question.get("sentences") or None,
            strict=True,
        )
        scored.append({**question, **evaluation, "evaluated": True})

    report = await generate_report(questions_asked=scored, role=role, strict=True)
    logger.info("Technical round evaluated for role %s across %s answer(s)", role, len(scored))
    return {"questions": scored, "report": report}
