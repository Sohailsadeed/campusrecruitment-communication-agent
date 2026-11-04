"""The HR answer contract: only the live question is written, and history is never overwritten.

No database is opened here. `owned_round_session`, the evaluator, the report generator and the
question picker are all replaced with fakes, so what these tests exercise is the route's own
decision -- which record an answer lands in, and what happens when it does not belong to the live
question. Real scoring is not under test; the stand-in evaluation is a fixed dict.
"""
from __future__ import annotations

import asyncio
import importlib

import pytest
from fastapi import HTTPException

from app.agents import hr_voice_agent
from app.routes import hr as hr_route
from app.services.hr import hr_service

# `app.database.__init__` re-exports the Engine instance under the name `engine`, which shadows the
# submodule on the package, so the module has to be taken from sys.modules by its real name.
engine_module = importlib.import_module("app.database.engine")

LIVE = {"id": "hr_q2", "track": "Ownership", "text": "Tell me about an outage you handled."}
ANSWERED = {"id": "hr_q1", "track": "Culture Fit", "text": "Why this company?",
            "answer": "Because of the mission.", "evaluation": {"overall_score": 70,
                                                                "evaluator_basis": "model"}}
EVALUATION = {"overall_score": 81, "personal_ownership_score": 84,
              "star_structure": {"situation": {"present": True, "summary": "s"},
                                 "task": {"present": True, "summary": "t"},
                                 "action": {"present": True, "summary": "a"},
                                 "result": {"present": True, "summary": "r"},
                                 "completeness_score": 80, "structure_critique": "ok"},
              "specificity_score": 79, "specificity_critique": "ok", "relevance_score": 88,
              "relevance_critique": "ok", "ownership_critique": "ok",
              "coaching_feedback": "Quantify more.", "ideal_star_script": "script",
              "evaluator_basis": "model", "evaluator_error": None}


class FakeHR:
    def __init__(self, current_question=LIVE, questions=None, max_questions=4):
        self.role = "Backend Engineer"
        self.target_company = "Acme"
        self.interview_mode = "standard_hr"
        self.max_questions = max_questions
        self.question_count = len(questions or [])
        self.questions = list(questions or [])
        self.current_question = current_question


class FakeSession:
    def __init__(self, hr):
        self.id = 4411
        self.user_id = 7
        self.status = "in_progress"
        self.overall_score = 0.0
        self.report = None
        self.hr_detail = hr


class FakeDB:
    def __init__(self):
        self.commits = 0

    def commit(self):
        self.commits += 1

    def rollback(self):
        raise AssertionError("the route only rolls back inside its audio transaction")


@pytest.fixture()
def wired(monkeypatch):
    """A route wired to fakes: nothing scores, nothing advances, nothing is stored anywhere real."""
    holder = {}

    async def fake_evaluate(**kwargs):
        holder["evaluate_kwargs"] = kwargs
        return dict(EVALUATION)

    async def fake_report(**kwargs):
        holder["report_called"] = True
        return {"total_score": 80, "strengths": [], "weaknesses": [],
                "executive_summary": "stub", "avg_ownership_score": 80,
                "avg_star_completeness": 80, "avg_specificity_score": 80}

    def fake_pick(**kwargs):
        return {"id": "hr_q3", "track": "Motivation", "text": "What motivates you?"}

    monkeypatch.setattr(hr_route, "evaluate_hr_answer", fake_evaluate)
    monkeypatch.setattr(hr_route, "generate_hr_report", fake_report)
    monkeypatch.setattr(hr_route, "pick_next_hr_question", fake_pick)
    # Real implementation reads the Redis emotion buffer; the report's copy of it is not under test.
    monkeypatch.setattr(hr_route, "get_session_emotion_summary",
                        lambda session_id, fallback=None: {"summary": "stubbed"})

    def _install(hr):
        session = FakeSession(hr)
        db = FakeDB()
        monkeypatch.setattr(hr_route, "owned_round_session",
                            lambda *a, **k: session)
        holder.update(session=session, hr=hr, db=db)
        return session, db

    holder["install"] = _install
    return holder


def submit(session, db, answer="I owned the rollback and wrote the runbook.",
           question_ref=None):
    return asyncio.run(hr_route.submit_hr_answer(
        session_id=session.id, answer=answer, question_ref=question_ref, audio_file=None,
        current_user=type("U", (), {"id": 7})(), db=db))


# ---------------------------------------------------------------------- the resolver itself ----

def test_no_reference_means_the_live_question():
    questions = [dict(ANSWERED)]
    assert hr_service.resolve_answer_slot(LIVE, questions, None) == ("live", None)


def test_the_live_question_is_live_even_when_it_is_already_on_the_record():
    """The typed-over-voice race: the entry exists, the round has not moved on yet."""
    answered_live = {**LIVE, "answer": "spoken first"}
    slot, index = hr_service.resolve_answer_slot(LIVE, [dict(ANSWERED), answered_live], "hr_q2")
    assert (slot, index) == ("live", 1)


def test_a_question_the_round_moved_past_is_history():
    slot, index = hr_service.resolve_answer_slot(LIVE, [dict(ANSWERED)], "hr_q1")
    assert (slot, index) == ("history", 0)


def test_a_reference_that_names_nothing_in_the_round_is_unknown():
    assert hr_service.resolve_answer_slot(LIVE, [dict(ANSWERED)], "hr_q99") == ("unknown", None)


def test_text_still_identifies_a_question_recorded_before_ids():
    legacy = {"text": "Why this company?", "answer": "old"}
    slot, index = hr_service.resolve_answer_slot(LIVE, [legacy], "Why this company?")
    assert (slot, index) == ("history", 0)


def test_a_live_question_without_an_id_is_matched_by_text():
    live = {"text": "Tell me about an outage you handled."}
    assert hr_service.resolve_answer_slot(live, [], "tell me about an outage you handled.") \
        == ("live", None)


def test_a_completed_round_reports_history_not_a_writable_slot():
    """The route already refuses a completed round with 400; the resolver never offers a live slot."""
    assert hr_service.resolve_answer_slot(None, [dict(ANSWERED)], "hr_q1") == ("history", 0)
    assert hr_service.resolve_answer_slot(None, [dict(ANSWERED)], None) == ("unknown", None)


# ------------------------------------------------------------------------- the typed route ----

def test_first_answer_for_the_live_question_is_appended(wired):
    hr = FakeHR()
    session, db = wired["install"](hr)
    result = submit(session, db)

    assert result["is_complete"] is False
    assert result["question_count"] == 1
    assert len(hr.questions) == 1
    assert hr.questions[0]["id"] == "hr_q2"
    assert hr.questions[0]["evaluation"]["evaluator_basis"] == "model"
    assert hr.current_question == {"id": "hr_q3", "track": "Motivation",
                                   "text": "What motivates you?"}
    assert result["speech"]["available"] is True, "the typed text is measured"
    assert result["speech"]["words_per_minute"] is None, "nothing was spoken, so no rate is claimed"


def test_a_typed_correction_amends_the_live_entry_instead_of_duplicating_it(wired):
    first = {**LIVE, "answer": "first attempt", "evaluation": {"overall_score": 40}}
    hr = FakeHR(current_question=LIVE, questions=[dict(ANSWERED), first])
    session, db = wired["install"](hr)
    result = submit(session, db, answer="corrected answer", question_ref="hr_q2")

    assert result["question_count"] == 2, "an amendment must not add a third answer"
    assert len(hr.questions) == 2
    assert hr.questions[1]["answer"] == "corrected answer"
    assert hr.questions[1]["evaluation"]["overall_score"] == 81
    assert hr.questions[0]["answer"] == "Because of the mission.", "history left alone"
    # Preserved from before the contract: an amended live answer still closes that question, so the
    # round moves on rather than asking it a third time.
    assert hr.current_question["id"] == "hr_q3"
    assert result["next_question"]["id"] == "hr_q3"


def test_answering_a_question_that_is_already_recorded_and_not_live_is_a_conflict(wired):
    hr = FakeHR(current_question={"id": "hr_q3", "track": "Motivation",
                                  "text": "What motivates you?"},
                questions=[dict(ANSWERED)])
    session, db = wired["install"](hr)

    with pytest.raises(HTTPException) as caught:
        submit(session, db, answer="a late second attempt", question_ref="hr_q1")

    assert caught.value.status_code == 409
    assert "no longer the live question" in caught.value.detail
    assert hr.questions == [dict(ANSWERED)], "the recorded answer must survive untouched"
    assert hr.questions[0]["answer"] == "Because of the mission."
    assert db.commits == 0, "a rejected submit must not write or advance"
    assert "evaluate_kwargs" not in wired, "a rejected submit must not score anything"


def test_a_reference_matching_no_question_in_the_round_is_also_refused(wired):
    hr = FakeHR(questions=[dict(ANSWERED)])
    session, db = wired["install"](hr)

    with pytest.raises(HTTPException) as caught:
        submit(session, db, question_ref="hr_q42")

    assert caught.value.status_code == 409
    assert "does not match a question in this round" in caught.value.detail
    assert len(hr.questions) == 1
    assert db.commits == 0


def test_a_reference_naming_the_live_question_is_accepted_and_appended(wired):
    """What the corrected frontend now sends: the id of the question actually on screen."""
    hr = FakeHR()
    session, db = wired["install"](hr)
    result = submit(session, db, question_ref="hr_q2")

    assert result["question_count"] == 1
    assert hr.questions[0]["id"] == "hr_q2"


def test_a_stale_browser_without_a_reference_answers_the_live_question(wired):
    """Clients that predate the contract send no reference: they must keep working, not 409."""
    hr = FakeHR(questions=[dict(ANSWERED)])
    session, db = wired["install"](hr)
    result = submit(session, db)
    assert result["question_count"] == 2
    assert hr.questions[1]["id"] == "hr_q2"


def test_legacy_entries_without_ids_are_amended_by_text(wired):
    legacy_live = {"text": LIVE["text"], "answer": "spoken"}
    hr = FakeHR(current_question=LIVE, questions=[legacy_live])
    session, db = wired["install"](hr)
    result = submit(session, db, answer="typed correction")

    assert result["question_count"] == 1
    assert hr.questions[0]["answer"] == "typed correction"
    assert hr.questions[0]["text"] == LIVE["text"]


def test_the_answered_question_is_evaluated_against_the_live_question_text(wired):
    hr = FakeHR()
    session, db = wired["install"](hr)
    submit(session, db)
    assert wired["evaluate_kwargs"]["question"] == LIVE["text"]
    assert wired["evaluate_kwargs"]["track"] == "Ownership"


def test_a_round_without_hr_detail_is_reported_missing(wired, monkeypatch):
    """The route's own 404: no detail row means there is nothing to answer, and nothing is written."""
    session = FakeSession(None)
    db = FakeDB()
    monkeypatch.setattr(hr_route, "owned_round_session", lambda *a, **k: session)

    with pytest.raises(HTTPException) as caught:
        submit(session, db)

    assert caught.value.status_code == 404
    assert caught.value.detail == "HR interview detail missing."
    assert db.commits == 0


def test_a_completed_round_is_refused(wired):
    hr = FakeHR(current_question=None, questions=[dict(ANSWERED)])
    session, db = wired["install"](hr)

    with pytest.raises(HTTPException) as caught:
        submit(session, db, question_ref="hr_q1")
    assert caught.value.status_code == 400
    assert len(hr.questions) == 1


def test_a_session_that_is_not_this_candidates_never_reaches_the_write(wired):
    hr = FakeHR()
    session, db = wired["install"](hr)

    def _denied(*a, **k):
        raise HTTPException(status_code=404, detail="Session not found")

    original = hr_route.owned_round_session
    hr_route.owned_round_session = _denied
    try:
        with pytest.raises(HTTPException) as caught:
            submit(session, db)
        assert caught.value.status_code == 404
        assert caught.value.detail == "Session not found"
    finally:
        hr_route.owned_round_session = original
    assert hr.questions == [], "denial must leave nothing behind"
    assert db.commits == 0


def test_the_last_answer_completes_the_round_and_writes_a_report(wired):
    hr = FakeHR(current_question=LIVE, questions=[dict(ANSWERED)], max_questions=2)
    session, db = wired["install"](hr)
    result = submit(session, db)

    assert result["is_complete"] is True
    assert result["report"]["total_score"] == 80
    assert "speech" in result["report"], "the delivery section is still attached"
    assert hr.current_question is None
    assert session.status == "completed"
    assert db.commits == 1


# --------------------------------------------------------------------- the voice writer ----
# The voice lane reaches the same table through no route, so the contract is re-asserted here
# against the agent's own writer. SessionLocal is replaced by an in-memory stand-in: the agent
# imports it inside the function, and no database session is ever constructed.

class FakeCtxDB:
    """The `with SessionLocal() as db:` the agent uses, with a commit counter."""

    def __init__(self, db):
        self._db = db

    def __enter__(self):
        return self._db

    def __exit__(self, *exc):
        return False


def voice(monkeypatch, hr, status="in_progress"):
    """Wire the agent's writer to a fake owned row and return (db, call helper)."""
    session = FakeSession(hr)
    session.status = status
    db = FakeDB()

    monkeypatch.setattr(hr_voice_agent, "_owned_hr", lambda *a, **k: (session, hr))
    monkeypatch.setattr(engine_module, "SessionLocal", lambda: FakeCtxDB(db))

    def _write(question=LIVE, answer="I ran the rollback and wrote the runbook.",
               evaluation=None, speech=None):
        return hr_voice_agent._write_voice_answer(
            session.id, session.user_id, dict(question), answer,
            dict(evaluation if evaluation is not None else EVALUATION), speech)

    return db, _write


def test_a_spoken_answer_for_the_live_question_is_appended(monkeypatch):
    hr = FakeHR()
    db, write = voice(monkeypatch, hr)
    outcome = write()

    assert outcome["count"] == 1 and outcome["complete"] is False
    assert hr.questions[0]["id"] == "hr_q2"
    assert hr.questions[0]["answered_by"] == "voice_agent"
    assert hr.questions[0]["audio_url"] is None, "the voice round keeps no recording"
    assert hr.questions[0]["evaluation"]["evaluator_basis"] == "model"
    assert db.commits == 1


def test_a_late_spoken_answer_cannot_replace_the_typed_answer_on_record(monkeypatch):
    """The legitimate race, in the direction that matters: typed first, voice arrives after."""
    typed = {**LIVE, "answer": "typed correction", "evaluation": {"overall_score": 81}}
    hr = FakeHR(current_question=LIVE, questions=[dict(ANSWERED), typed])
    db, write = voice(monkeypatch, hr)
    outcome = write(answer="the same words heard again")

    assert outcome["count"] == 2, "a re-heard live answer must not add a third entry"
    assert len(hr.questions) == 2
    assert hr.questions[1]["answered_by"] == "voice_agent"
    assert hr.questions[0]["answer"] == "Because of the mission.", "history left alone"


def test_a_voice_answer_for_a_question_the_round_moved_past_is_refused(monkeypatch):
    hr = FakeHR(current_question={"id": "hr_q3", "text": "What motivates you?"},
                questions=[dict(ANSWERED)])
    db, write = voice(monkeypatch, hr)
    outcome = write(question=dict(ANSWERED))

    assert outcome is None
    assert hr.questions == [dict(ANSWERED)], "the recorded answer stands"
    assert db.commits == 0, "a refusal must not write or advance"


def test_a_voice_answer_for_a_question_this_round_never_held_is_refused(monkeypatch):
    hr = FakeHR(questions=[dict(ANSWERED)])
    db, write = voice(monkeypatch, hr)
    outcome = write(question={"id": "hr_q99", "text": "Some other question."})

    assert outcome is None
    assert len(hr.questions) == 1
    assert db.commits == 0


def test_a_round_the_candidate_does_not_own_is_never_written(monkeypatch):
    """_owned_hr returns (None, None) for a foreign or missing session, exactly as the route 404s."""
    db, write = voice(monkeypatch, FakeHR())
    monkeypatch.setattr(hr_voice_agent, "_owned_hr", lambda *a, **k: (None, None))

    assert write() is None
    assert db.commits == 0


def test_a_completed_round_on_record_refuses_a_voice_answer(monkeypatch):
    """The route 400s this; the writer has no route, so it carries the same refusal."""
    hr = FakeHR(current_question=None, questions=[dict(ANSWERED)])
    db, write = voice(monkeypatch, hr, status="completed")

    assert write() is None
    assert hr.questions == [dict(ANSWERED)]
    assert db.commits == 0


def test_the_last_spoken_answer_reports_the_round_complete(monkeypatch):
    hr = FakeHR(current_question=LIVE, questions=[dict(ANSWERED)], max_questions=2)
    db, write = voice(monkeypatch, hr)
    outcome = write()

    assert outcome["complete"] is True
    assert outcome["count"] == outcome["max_questions"] == 2
    assert outcome["role"] == "Backend Engineer" and outcome["company"] == "Acme"
    assert db.commits == 1
