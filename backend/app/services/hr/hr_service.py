"""HR interview state machine managing multi-question behavioral progression."""
import logging
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from app.services.hr.question_bank import (
    get_next_hr_question,
    get_initial_hr_question,
)

logger = logging.getLogger(__name__)


def pick_next_hr_question(
    track: str,
    company: Optional[str],
    questions_asked: List[Dict[str, Any]],
    db: Optional[Session] = None,
) -> Dict[str, Any]:
    """Pick next behavioral question querying the database, avoiding duplicates and rotating tracks."""
    asked_texts = [q.get("text", "") for q in questions_asked if q.get("text")]
    chosen = get_next_hr_question(
        db=db,
        asked_texts=asked_texts,
        preferred_track=track if track != "standard_hr" else None,
    )

    if not chosen:
        q_index = len(questions_asked)
        return {
            "id": f"hr_q{q_index + 1}",
            "track": track,
            "text": "Reflecting on your past experiences, what is one professional habit or mindset you developed that most sets you apart?",
            "rubric": {
                "green_flags": ["Clear STAR structure", "Quantified personal ownership"],
                "red_flags": ["Vague claims", "Passive language"],
            },
        }

    text = chosen["text"]
    if chosen.get("track") in ("Culture Fit", "Motivation") and company:
        text = text.replace("our company", company).replace("the company", company)

    return {
        "id": chosen["id"],
        "track": chosen["track"],
        "text": text,
        "difficulty": chosen.get("difficulty", "Medium"),
        "source_type": chosen.get("source_type", "Behavioral"),
        "keywords": chosen.get("keywords", []),
        "rubric": chosen.get("rubric", {}),
    }


# --------------------------------------------------------------------------- answer slots ----

def question_ref(question: Optional[Dict[str, Any]]) -> str:
    """The identifier a question is recognised by: its id when it has one, otherwise its text.

    Entries written before ids were stored still resolve by text, so an in-flight round is not
    orphaned by this change.
    """
    if not question:
        return ""
    ref = str(question.get("id") or "").strip().lower()
    return ref or str(question.get("text", "")).strip().lower()


def same_question(first: Optional[Dict[str, Any]], second: Optional[Dict[str, Any]]) -> bool:
    """Whether two question dicts describe the same question, by id first and text as a fallback.

    A probe re-asks the same question, so matching on text alone is kept: the round has no separate
    identity for a follow-up, and both callers need one entry per question, not one per asking.
    """
    if not first or not second:
        return False
    first_ref, second_ref = question_ref(first), question_ref(second)
    if not first_ref or not second_ref:
        return False
    if first_ref == second_ref:
        return True
    first_text = str(first.get("text", "")).strip().lower()
    second_text = str(second.get("text", "")).strip().lower()
    return bool(first_text) and first_text == second_text


def find_answered(questions: List[Dict[str, Any]], question: Optional[Dict[str, Any]]) -> Optional[int]:
    """Index of the recorded answer for this question, if one has been recorded."""
    return next((i for i, asked in enumerate(questions or [])
                 if same_question(asked, question)), None)


def _ref_matches(ref: str, question: Optional[Dict[str, Any]]) -> bool:
    """Whether a submitted reference names this question, by id first and text as a fallback."""
    if not question or not ref:
        return False
    return ref == question_ref(question) or ref == str(question.get("text", "")).strip().lower()


def resolve_answer_slot(live_question: Optional[Dict[str, Any]],
                        questions: List[Dict[str, Any]],
                        submitted_ref: Optional[str] = None) -> tuple:
    """Decide which record an incoming answer belongs to, before anything is written.

    `submitted_ref` is what the client says it is answering -- a question id, or its text. An empty
    reference means the live question, which is what every client that predates this contract sends.
    Only the live question may be amended: an answer naming a question the round has already moved
    past is a conflict, because recording it would replace a historical answer through the ordinary
    answer endpoint.

    Returns ("live", index), ("history", index) or ("unknown", None).
    """
    ref = str(submitted_ref or "").strip().lower()
    if not ref or _ref_matches(ref, live_question):
        if not live_question:
            return "unknown", None
        return "live", find_answered(questions or [], live_question)

    for index, asked in enumerate(questions or []):
        if _ref_matches(ref, asked):
            return "history", index
    return "unknown", None
