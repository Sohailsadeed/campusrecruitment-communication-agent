"""The provenance the HR report UI reads: what the evaluator records and what the routes surface.

Nothing here reaches a model. The client builder is replaced with a stand-in that either raises or
is asserted never to have been called, so each test exercises the service's own bookkeeping -- the
fields that tell a candidate whether a number came from a model that read their answer or from a
template. The two read routes are checked to pass those fields through untouched, because a
provenance flag dropped on the way to the browser is a fallback that reads like a real score.
"""
from __future__ import annotations

import asyncio
import json

import pytest
from fastapi import HTTPException
from langchain_core.runnables import RunnableLambda
from app.routes import hr as hr_route
from app.services.hr import evaluator as hr_evaluator

CANARY = "sk-CANARY-NEVER-SHOW-THIS"

MODEL_EVALUATION = {
    "overall_score": 88,
    "star_structure": {
        "situation": {"present": True, "summary": "s"},
        "task": {"present": True, "summary": "t"},
        "action": {"present": True, "summary": "a"},
        "result": {"present": True, "summary": "r"},
        "completeness_score": 85,
        "structure_critique": "ok",
    },
    "personal_ownership_score": 90,
    "ownership_critique": "ok",
    "specificity_score": 86,
    "specificity_critique": "ok",
    "relevance_score": 87,
    "relevance_critique": "ok",
    "coaching_feedback": "ok",
    "ideal_star_script": "script",
}


def refusing_llm(*a, **k):
    """Stand-in for the client builder's result: composing it into a chain is fine, invoking fails."""
    def _raise(payload):
        raise ConnectionError(f"Ollama refused the request (key {CANARY})")
    return RunnableLambda(_raise)


def canned_llm(payload_dict):
    """A model that answers with exactly this evaluation, as the JSON text the parser expects."""
    def _answer(payload):
        from langchain_core.messages import AIMessage
        return AIMessage(content=json.dumps(payload_dict))
    return RunnableLambda(_answer)


# ------------------------------------------------------------------ what the evaluator records ----

def test_an_answer_too_short_for_a_model_is_marked_heuristic(monkeypatch):
    """The brief-answer path never builds a client, so its basis is pure service bookkeeping."""
    def _never(**kwargs):
        raise AssertionError("a too-brief answer must not reach a provider")

    monkeypatch.setattr(hr_evaluator.llm_client, "build_chat_client", _never)
    result = asyncio.run(hr_evaluator.evaluate_hr_answer(
        role="Backend Engineer", company="Acme", track="Ownership",
        question="Tell me about a time you owned a failure.", candidate_answer="Hmm."))

    assert result["evaluator_basis"] == "heuristic"
    assert "too brief" in result["evaluator_error"]
    assert result["overall_score"] == 40, "the floor score, not a judgement of the content"


def test_a_provider_failure_is_recorded_as_fallback_with_a_cause(monkeypatch):
    monkeypatch.setattr(hr_evaluator, "_get_llm", refusing_llm)
    result = asyncio.run(hr_evaluator.evaluate_hr_answer(
        role="Backend Engineer", company="Acme", track="Ownership",
        question="Tell me about a time you owned a failure.",
        candidate_answer="I rerouted the traffic myself and wrote the postmortem."))

    assert result["evaluator_basis"] == "fallback"
    assert "ConnectionError" in result["evaluator_error"]
    assert len(result["evaluator_error"]) <= 300, "the cause is capped, not an unbounded dump"


def test_a_model_scored_answer_is_marked_as_such(monkeypatch):
    monkeypatch.setattr(hr_evaluator, "_get_llm", lambda *a, **k: canned_llm(MODEL_EVALUATION))
    result = asyncio.run(hr_evaluator.evaluate_hr_answer(
        role="Backend Engineer", company="Acme", track="Ownership",
        question="Tell me about a time you owned a failure.",
        candidate_answer="I rerouted the traffic myself and wrote the postmortem."))

    assert result["evaluator_basis"] == "model"
    assert result["evaluator_error"] is None


def test_a_report_with_no_model_behind_it_is_marked_empirical(monkeypatch):
    answers = [
        {"text": "Why this company?", "answer": "a",
         "evaluation": {"overall_score": 74, "evaluator_basis": "fallback",
                        "evaluator_error": "ConnectionError: down"}},
        {"text": "Tell me about a conflict.", "answer": "b",
         "evaluation": {"overall_score": 88, "evaluator_basis": "model"}},
    ]
    monkeypatch.setattr(hr_evaluator, "_get_llm", refusing_llm)
    report = asyncio.run(hr_evaluator.generate_hr_report(
        role="Backend Engineer", company="Acme", questions_asked=answers))

    assert report["report_basis"] == "empirical"
    assert "ConnectionError" in report["report_error"]
    assert report["answers_not_model_scored"] == 1, "only the fallback answer counts"
    assert report["total_score"] == 81, "the arithmetic still averages the real scores"


# ------------------------------------------------------------------- what the routes surface ----

class FakeHR:
    def __init__(self, questions, report=None):
        self.id = 900
        self.role = "Backend Engineer"
        self.target_company = "Acme"
        self.interview_mode = "standard_hr"
        self.max_questions = 2
        self.question_count = len(questions)
        self.questions = questions
        self.current_question = None
        self.created_at = None


class FakeSession:
    def __init__(self, hr, report):
        self.id = 4411
        self.user_id = 7
        self.status = "completed"
        self.hr_detail = hr
        self.report = report
        self.overall_score = 78.0
        self.created_at = None


ANSWERS = [
    {"id": "hr_q1", "track": "Culture Fit", "text": "Why this company?", "answer": "Because...",
     "speech": {"available": True},
     "evaluation": {"overall_score": 74, "evaluator_basis": "fallback",
                    "evaluator_error": "ConnectionError: Ollama refused"}},
]
REPORT = {"total_score": 74, "strengths": [], "weaknesses": [], "executive_summary": "stub",
          "avg_ownership_score": 72, "avg_star_completeness": 75, "avg_specificity_score": 75,
          "speech": {"answers": []}, "vocal_delivery": {},
          "report_basis": "empirical", "report_error": "ConnectionError: Ollama refused",
          "answers_not_model_scored": 1}


@pytest.fixture()
def served(monkeypatch):
    session = FakeSession(FakeHR([dict(a) for a in ANSWERS], dict(REPORT)), dict(REPORT))
    monkeypatch.setattr(hr_route, "owned_round_session", lambda *a, **k: session)
    return session


def test_the_report_route_carries_the_provenance_the_ui_reads(served):
    body = hr_route.get_hr_report(served.id, current_user=type("U", (), {"id": 7})(), db=None)

    assert body["report"]["report_basis"] == "empirical"
    assert body["report"]["report_error"] == "ConnectionError: Ollama refused"
    assert body["report"]["answers_not_model_scored"] == 1
    assert body["questions"][0]["evaluation"]["evaluator_basis"] == "fallback"
    assert body["questions"][0]["evaluation"]["evaluator_error"] == "ConnectionError: Ollama refused"


def test_the_session_route_surfaces_the_same_fields(served):
    body = hr_route.get_hr_session(served.id, current_user=type("U", (), {"id": 7})(), db=None)

    assert body["report"]["report_basis"] == "empirical"
    assert body["questions"][0]["evaluation"]["evaluator_basis"] == "fallback"


def test_a_report_written_before_provenance_existed_is_not_given_one(served):
    """Older rows simply lack the keys: the routes add nothing, so the UI can say 'not recorded'."""
    stripped = {k: v for k, v in served.report.items()
                if k not in ("report_basis", "report_error", "answers_not_model_scored")}
    served.report = stripped
    served.hr_detail.questions = [{**ANSWERS[0], "evaluation": {"overall_score": 74}}]

    body = hr_route.get_hr_report(served.id, current_user=type("U", (), {"id": 7})(), db=None)

    assert "report_basis" not in body["report"]
    assert "evaluator_basis" not in body["questions"][0]["evaluation"]


def test_a_round_without_a_report_is_refused_rather_than_invented(served):
    served.report = None
    with pytest.raises(HTTPException) as caught:
        hr_route.get_hr_report(served.id, current_user=type("U", (), {"id": 7})(), db=None)
    assert caught.value.status_code == 400
