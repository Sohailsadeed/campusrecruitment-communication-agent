"""AUTH-C fixtures: the five routers whose handlers key on a caller-supplied session id.

conftest.py owns the environment (DATABASE_URL / UPLOAD_DIR / LOGS_DIR inside a temp dir outside
the repository) and the db_session fixture. Nothing here imports main.py, so no startup DDL, no
ALTER TABLE migration, no HR seed, no rotating log handler and no emotion-model warm-up can run.

Every external processor a session-keyed handler can reach — Whisper, wav2vec2, the Nemotron
evaluators, the technical LangGraph, Mem0, the Redis-backed emotion summary and the Laya metrics
read — is replaced by a recording stub *at the attribute the route module imported*, the same way
AUTH-B patched the curriculum agent. A test that reaches one of those attributes is therefore
proving the handler ran, not that a billable call happened; a test asserting zero calls is proving
the request was refused before any work.

The guest-pool defect keys on the *literal* user id 1, so accounts are created with an explicit id
rather than relying on insertion order.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from conftest import BACKEND_DIR, TEMP_ROOT
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.database.engine import get_db
from app.models.feedback import AIFeedback
from app.models.guesstimate import GuesstimateCase
from app.models.hr import HRInterview
from app.models.session import (
    Session as SessionModel,
    SessionAnalysis,
    Transcription,
)
from app.models.technical import TechnicalInterview
from app.models.user import User
from app.routes import analysis as analysis_module
from app.routes import feedback as feedback_module
from app.routes import guesstimate as guesstimate_module
from app.routes import hr as hr_module
from app.routes import progress as progress_module
from app.routes import sessions as sessions_module
from app.routes import technical as technical_module
from app.routes.auth import create_access_token
from config import settings

ROUTES_DIR = BACKEND_DIR / "app" / "routes"
SERVICES_DIR = BACKEND_DIR / "app" / "services"

# AUTH-A's uniform 401 body, inherited by every endpoint that binds get_current_user.
UNAUTHENTICATED = "Could not validate credentials"
WWW_AUTHENTICATE = "Bearer"
# The single not-found detail AUTH-C must use at every session-keyed site (§3), so a foreign, an
# orphaned and an absent session are indistinguishable to the caller.
NOT_FOUND_DETAIL = "Session not found"

GUEST_ID = 1
VICTIM_ID = 2
CALLER_ID = 3

# Marker bytes only: no real recording is decoded, and the ASR stub returns no text, so nothing
# here is presented as a transcript or a measurement.
CLIP_BODY = b"\x1a\x45\xdf\xa3auth-c-fixture-clip"
FIXTURE_ANSWER = "Fixture answer text submitted by the AUTH-C test."

QUESTION = {
    "track": "standard_hr",
    "text": "Tell me about a time you owned a failure.",
    "category": "Ownership",
}


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Account:
    id: int
    email: str
    token: str

    @property
    def auth(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}


BAD_AUTH_HEADERS: List[Any] = [
    pytest.param(None, id="no-authorization-header"),
    pytest.param("Bearer ", id="bearer-without-token"),
    pytest.param("Bearer not.a.real.jwt", id="malformed-token"),
    pytest.param("Basic dXNlcjpwYXNz", id="non-bearer-scheme"),
]


# ---------------------------------------------------------------------------
# Endpoint registry — the 22 AUTH-C handlers, exactly
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Endpoint:
    name: str
    router_file: str
    handler: str
    method: str
    path: str
    round_type: Optional[str] = None
    needs_detail: bool = False
    needs_report: bool = False
    needs_current_question: bool = False
    writes_disk: bool = False
    commits: bool = False
    form: Dict[str, Any] = field(default_factory=dict)
    json_body: Optional[Dict[str, Any]] = None
    by_id: bool = False


BY_ID_ENDPOINTS: Tuple[Endpoint, ...] = (
    Endpoint("jam.get", "sessions.py", "get_session", "get",
             "/api/sessions/{sid}", round_type="jam", by_id=True),
    Endpoint("jam.audio", "sessions.py", "get_session_audio", "get",
             "/api/sessions/{sid}/audio", round_type="jam", by_id=True),
    Endpoint("jam.update", "sessions.py", "update_session", "patch",
             "/api/sessions/{sid}", round_type="jam", by_id=True, commits=True,
             json_body={"title": "Rewritten by AUTH-C"}),
    Endpoint("jam.delete", "sessions.py", "delete_session", "delete",
             "/api/sessions/{sid}", round_type="jam", by_id=True, commits=True),
    Endpoint("hr.answer", "hr.py", "submit_hr_answer", "post", "/api/hr/answer",
             round_type="hr", needs_detail=True, needs_current_question=True,
             writes_disk=True, commits=True, by_id=True,
             form={"answer": FIXTURE_ANSWER}),
    Endpoint("hr.session", "hr.py", "get_hr_session", "get",
             "/api/hr/session/{sid}", round_type="hr", by_id=True),
    Endpoint("hr.report", "hr.py", "get_hr_report", "get",
             "/api/hr/report/{sid}", round_type="hr", needs_report=True, by_id=True),
    Endpoint("guesstimate.submit", "guesstimate.py", "submit_guesstimate_answer", "post",
             "/api/guesstimate/submit", round_type="guesstimate", needs_detail=True,
             writes_disk=True, commits=True, by_id=True,
             form={"answer": FIXTURE_ANSWER, "approach_type": "top_down"}),
    Endpoint("guesstimate.session", "guesstimate.py", "get_guesstimate_session", "get",
             "/api/guesstimate/session/{sid}", round_type="guesstimate", by_id=True),
    Endpoint("guesstimate.report", "guesstimate.py", "get_guesstimate_report", "get",
             "/api/guesstimate/report/{sid}", round_type="guesstimate",
             needs_report=True, by_id=True),
    Endpoint("technical.answer", "technical.py", "submit_technical_answer", "post",
             "/api/technical/answer", round_type="technical", needs_detail=True,
             needs_current_question=True, writes_disk=True, commits=True, by_id=True,
             form={"answer": FIXTURE_ANSWER}),
    Endpoint("technical.session", "technical.py", "get_technical_session", "get",
             "/api/technical/session/{sid}", round_type="technical", by_id=True),
    Endpoint("technical.report", "technical.py", "get_technical_report", "get",
             "/api/technical/report/{sid}", round_type="technical",
             needs_report=True, by_id=True),
)

COLLECTION_ENDPOINTS: Tuple[Endpoint, ...] = (
    Endpoint("jam.list", "sessions.py", "list_sessions", "get", "/api/sessions"),
    Endpoint("jam.create", "sessions.py", "create_session", "post", "/api/sessions",
             commits=True, form={"title": "AUTH-C created", "duration_seconds": "12.5",
                                 "round_type": "jam"}),
    Endpoint("jam.create_json", "sessions.py", "create_session_json", "post",
             "/api/sessions/json", commits=True,
             json_body={"title": "AUTH-C json", "duration_seconds": 7.0,
                        "round_type": "jam"}),
    Endpoint("progress.summary", "progress.py", "get_summary", "get", "/api/progress/summary"),
    Endpoint("progress.metrics", "progress.py", "get_metrics", "get", "/api/progress/metrics"),
    Endpoint("progress.technical", "progress.py", "get_technical_progress", "get",
             "/api/progress/technical"),
    Endpoint("progress.guesstimate", "progress.py", "get_guesstimate_progress", "get",
             "/api/progress/guesstimate"),
    Endpoint("progress.hr", "progress.py", "get_hr_progress", "get", "/api/progress/hr"),
    Endpoint("progress.readiness", "progress.py", "get_placement_readiness", "get",
             "/api/progress/placement-readiness"),
)

ALL_ENDPOINTS: Tuple[Endpoint, ...] = BY_ID_ENDPOINTS + COLLECTION_ENDPOINTS
ENDPOINTS_BY_NAME: Dict[str, Endpoint] = {e.name: e for e in ALL_ENDPOINTS}

# The 22 handler names, grouped for the static guards.
HANDLER_COUNTS = {"sessions.py": 7, "progress.py": 6, "hr.py": 3,
                  "guesstimate.py": 3, "technical.py": 3}


def endpoint(name: str) -> Endpoint:
    found = ENDPOINTS_BY_NAME.get(name)
    if found is None:
        raise AssertionError(f"unknown AUTH-C endpoint {name!r}")
    return found


# ---------------------------------------------------------------------------
# AUTH-D registry — additive. The 22 handlers above are AUTH-C's accepted inventory and are not
# touched: no entry is appended to ALL_ENDPOINTS and HANDLER_COUNTS keeps its AUTH-C meaning, so the
# guard asserting exactly 22 keeps testing exactly what it tested when AUTH-C was accepted.
# ---------------------------------------------------------------------------
AUTHD_ENDPOINTS: Tuple[Endpoint, ...] = (
    Endpoint("analysis.analyze", "analysis.py", "analyze_session", "post",
             "/api/sessions/{sid}/analyze", round_type="jam", by_id=True, commits=True),
    Endpoint("analysis.get", "analysis.py", "get_analysis", "get",
             "/api/sessions/{sid}/analysis", round_type="jam", by_id=True),
    Endpoint("analysis.transcription", "analysis.py", "get_transcription", "get",
             "/api/sessions/{sid}/transcription", round_type="jam", by_id=True),
    Endpoint("analysis.tts", "analysis.py", "get_session_tts", "get",
             "/api/sessions/{sid}/tts", round_type="jam", by_id=True),
    Endpoint("feedback.list", "feedback.py", "get_feedback", "get",
             "/api/sessions/{sid}/feedback", round_type="jam", by_id=True),
)
AUTHD_ENDPOINTS_BY_NAME: Dict[str, Endpoint] = {e.name: e for e in AUTHD_ENDPOINTS}
AUTHD_HANDLER_COUNTS = {"analysis.py": 4, "feedback.py": 1}

# The child-resource 404s an *owner* may still see (D-A4), and the rows each endpoint needs.
CHILD_DETAIL = {
    "analysis.get": ("Analysis not found", "analysis"),
    "analysis.transcription": ("Transcription not found", "transcription"),
    "feedback.list": ("No feedback for session", "feedback"),
}


def authd_endpoint(name: str) -> Endpoint:
    found = AUTHD_ENDPOINTS_BY_NAME.get(name)
    if found is None:
        raise AssertionError(f"unknown AUTH-D endpoint {name!r}")
    return found



# ---------------------------------------------------------------------------
# Recording stubs for every external processor a session-keyed handler can reach
# ---------------------------------------------------------------------------
@dataclass
class ProcessingStub:
    """Call log plus the originals, so a test can prove the real processor was swapped out."""

    calls: List[str] = field(default_factory=list)
    real: Dict[str, Any] = field(default_factory=dict)

    def count(self, name: Optional[str] = None) -> int:
        if name is None:
            return len(self.calls)
        return sum(1 for entry in self.calls if entry == name)

    @property
    def names(self) -> List[str]:
        return sorted(set(self.calls))


class _GraphStub:
    """The technical LangGraph stand-in: `ainvoke` returns a non-completing step."""

    def __init__(self, stub: ProcessingStub, real: Any) -> None:
        self._stub = stub
        self.real = real

    async def ainvoke(self, state: Dict[str, Any]) -> Dict[str, Any]:
        self._stub.calls.append("technical.interview_graph.ainvoke")
        return {
            "questions": [{**QUESTION, "answer": state.get("answer")}],
            "question_count": (state.get("question_count") or 0) + 1,
            "current_question": QUESTION,
            "evaluation": None,
            "is_complete": False,
            "report": None,
        }


def _transcribe_stub(stub: ProcessingStub, label: str):
    def _fake(path, *args, **kwargs):
        stub.calls.append(f"{label}.transcribe_audio")
        # No fabricated transcript: the handler falls back to the submitted answer text.
        return {"text": "", "words": [], "language": "en", "confidence": 0.0}

    return _fake


def _emotion_stub(stub: ProcessingStub, label: str):
    def _fake(path, *args, **kwargs):
        stub.calls.append(f"{label}.analyze_speech_emotion")
        return {}

    return _fake


def _summary_stub(stub: ProcessingStub, label: str):
    def _fake(session_id, fallback=None, *args, **kwargs):
        stub.calls.append(f"{label}.get_session_emotion_summary")
        return dict(fallback) if isinstance(fallback, dict) else {}

    return _fake


@pytest.fixture(autouse=True)
def stubbed_processing(monkeypatch) -> ProcessingStub:
    """Patch the attributes the five route modules actually imported, for every test here.

    Patching the service module instead would leave the route calling the real Whisper /
    wav2vec2 / LLM / Mem0 / Redis chain, exactly as AUTH-B found for the curriculum agent.
    """
    stub = ProcessingStub()

    for label, module in (("hr", hr_module), ("guesstimate", guesstimate_module),
                          ("technical", technical_module)):
        if hasattr(module, "transcribe_audio"):
            stub.real[f"{label}.transcribe_audio"] = getattr(module, "transcribe_audio")
            monkeypatch.setattr(module, "transcribe_audio", _transcribe_stub(stub, label))
        if hasattr(module, "analyze_speech_emotion"):
            stub.real[f"{label}.analyze_speech_emotion"] = getattr(module, "analyze_speech_emotion")
            monkeypatch.setattr(module, "analyze_speech_emotion", _emotion_stub(stub, label))
        if hasattr(module, "get_session_emotion_summary"):
            stub.real[f"{label}.get_session_emotion_summary"] = getattr(
                module, "get_session_emotion_summary")
            monkeypatch.setattr(module, "get_session_emotion_summary",
                                _summary_stub(stub, label))

    async def _evaluate_hr(**kwargs):
        stub.calls.append("hr.evaluate_hr_answer")
        return {}

    async def _hr_report(**kwargs):
        stub.calls.append("hr.generate_hr_report")
        return {"total_score": 0.0, "strengths": [], "weaknesses": []}

    def _next_hr_question(**kwargs):
        stub.calls.append("hr.pick_next_hr_question")
        return dict(QUESTION)

    stub.real["hr.evaluate_hr_answer"] = hr_module.evaluate_hr_answer
    stub.real["hr.generate_hr_report"] = hr_module.generate_hr_report
    stub.real["hr.pick_next_hr_question"] = hr_module.pick_next_hr_question
    stub.real["hr.audio_file_response"] = hr_module.audio_file_response
    monkeypatch.setattr(hr_module, "evaluate_hr_answer", _evaluate_hr)
    monkeypatch.setattr(hr_module, "generate_hr_report", _hr_report)
    monkeypatch.setattr(hr_module, "pick_next_hr_question", _next_hr_question)
    # AUTH-E's audio serving is out of scope, but no test here may reach the real resolver.
    monkeypatch.setattr(hr_module, "audio_file_response",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("AUTH-E audio")))

    async def _evaluate_guesstimate(**kwargs):
        stub.calls.append("guesstimate.evaluate_guesstimate")
        return {}

    def _laya(session_id, *args, **kwargs):
        stub.calls.append("guesstimate.get_session_laya_metrics")
        return {}

    stub.real["guesstimate.evaluate_guesstimate"] = guesstimate_module.evaluate_guesstimate
    stub.real["guesstimate.get_session_laya_metrics"] = guesstimate_module.get_session_laya_metrics
    stub.real["guesstimate.audio_file_response"] = guesstimate_module.audio_file_response
    monkeypatch.setattr(guesstimate_module, "evaluate_guesstimate", _evaluate_guesstimate)
    monkeypatch.setattr(guesstimate_module, "get_session_laya_metrics", _laya)
    monkeypatch.setattr(guesstimate_module, "audio_file_response",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("AUTH-E audio")))

    async def _store_performance(*args, **kwargs):
        stub.calls.append("technical.store_performance")
        return None

    stub.real["technical.interview_graph"] = technical_module.interview_graph
    stub.real["technical.store_performance"] = technical_module.store_performance
    monkeypatch.setattr(technical_module, "interview_graph",
                        _GraphStub(stub, technical_module.interview_graph))
    monkeypatch.setattr(technical_module, "store_performance", _store_performance)

    _stub_analysis_processors(analysis_module, stub, monkeypatch)
    return stub


def _analysis_metrics() -> Dict[str, Any]:
    """The minimum shape `analyze_session` reads, with zeroed values and no invented measurements.

    These are stub returns inside a test, not reported scores: every field the handler indexes must
    exist or the handler fails for its own reasons and a 404 would prove nothing about ownership.
    """
    return {
        "speaking_pace": 0.0,
        "filler_words_count": 0,
        "filler_words_list": {"words": [], "hesitations": []},
        "clarity_score": 0.0,
        "jam_score": 0.0,
        "jam_verdict": "Fixture verdict",
        "hesitations_count": 0,
        "repetitions_count": 0,
        "repeated_words": {},
        "jam_infractions": [],
        "multimodal_timeline": [],
        "nonverbal_summary": {},
    }


def _stub_analysis_processors(module, stub: ProcessingStub, monkeypatch) -> None:
    """AUTH-D: patch what `analysis.py` imported, so no test can reach Whisper, MediaPipe,
    audEERING, Praat, Ollama or edge-tts. Patching the service modules instead would leave the
    route calling the real chain."""

    def _record(name: str, value):
        def _fake(*args, **kwargs):
            stub.calls.append(f"analysis.{name}")
            return value() if callable(value) else value

        return _fake

    for attribute, value in (
        ("analyze_transcription", _analysis_metrics),
        ("analyze_video", lambda: {"eye_contact_percentage": 0.0, "posture_quality": 0.0}),
        ("analyze_audio_prosody", lambda: {"confidence_score": 0.0, "vocal_energy_db": 0.0,
                                           "tone_verdict": "Fixture tone"}),
        ("extract_prosody_features", lambda: {"pitch_mean_hz": 0.0}),
        ("generate_feedback", lambda: {"content": "Fixture feedback.", "score": 0.0,
                                       "suggestions": [], "congruence": {},
                                       "avatar_reaction": {}, "rewrites": [],
                                       "competencies": {}, "mastery_points": [],
                                       "curated_drills": []}),
    ):
        if hasattr(module, attribute):
            stub.real[f"analysis.{attribute}"] = getattr(module, attribute)
            monkeypatch.setattr(module, attribute, _record(attribute, value))

    for attribute in ("transcribe_audio", "analyze_speech_emotion"):
        if hasattr(module, attribute):
            stub.real[f"analysis.{attribute}"] = getattr(module, attribute)
            factory = _transcribe_stub if attribute == "transcribe_audio" else _emotion_stub
            monkeypatch.setattr(module, attribute, factory(stub, "analysis"))

    async def _synthesize(session_id: int, text: str, *args, **kwargs) -> Path:
        stub.calls.append("analysis.synthesize_feedback_audio")
        return write_tts_fixture(session_id)

    stub.real["analysis.synthesize_feedback_audio"] = module.synthesize_feedback_audio
    monkeypatch.setattr(module, "synthesize_feedback_audio", _synthesize)

    # feedback.py reads only the database today; pin that no processor sneaks in behind AUTH-D.
    stub.real["feedback.module"] = feedback_module



# ---------------------------------------------------------------------------
# Apps
# ---------------------------------------------------------------------------
def _override_with(db_session):
    def _override():
        yield db_session

    return _override


@pytest.fixture
def session_app(db_session) -> TestClient:
    """The five routers under test, mounted exactly as main.py mounts them (minus aliases)."""
    application = FastAPI()
    application.include_router(sessions_module.router)
    application.include_router(progress_module.router)
    application.include_router(technical_module.router)
    application.include_router(guesstimate_module.router)
    application.include_router(hr_module.router)
    application.dependency_overrides[get_db] = _override_with(db_session)
    with TestClient(application) as client:
        yield client


@pytest.fixture
def alias_app(db_session) -> TestClient:
    """main.py:75 + main.py:81 — the sessions router mounted twice, so the /api/jam alias shares
    the very handlers AUTH-C secures."""
    application = FastAPI()
    application.include_router(sessions_module.router)
    application.include_router(sessions_module.router, prefix="/api/jam", tags=["JAM Round"])
    application.dependency_overrides[get_db] = _override_with(db_session)
    with TestClient(application) as client:
        yield client


@pytest.fixture
def analysis_app(db_session) -> TestClient:
    """AUTH-D: analysis + feedback mounted as main.py:76-77 mounts them, plus the sessions router
    the child rows hang off. Nothing here reaches main.py, so no startup DDL or seeding runs."""
    application = FastAPI()
    application.include_router(sessions_module.router)
    application.include_router(analysis_module.router)
    application.include_router(feedback_module.router)
    application.dependency_overrides[get_db] = _override_with(db_session)
    with TestClient(application) as client:
        yield client


@pytest.fixture
def analysis_alias_app(db_session) -> TestClient:
    """main.py:76 + main.py:82 — the analysis router mounted twice, so the /api/jam alias of
    /analyze shares the very handler AUTH-D secures."""
    application = FastAPI()
    application.include_router(analysis_module.router)
    application.include_router(analysis_module.router, prefix="/api/jam", tags=["JAM Round"])
    application.dependency_overrides[get_db] = _override_with(db_session)
    with TestClient(application) as client:
        yield client


@pytest.fixture
def make_account(db_session):
    counter = {"n": 0}

    def _make(email: Optional[str] = None, user_id: Optional[int] = None) -> Account:
        counter["n"] += 1
        name = f"authc-user-{counter['n']}"
        address = email or f"{name}@ownership.test"
        kwargs: Dict[str, Any] = {
            "email": address,
            "username": name,
            "hashed_password": "not-a-real-hash",
        }
        if user_id is not None:
            kwargs["id"] = user_id
        user = User(**kwargs)
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
        return Account(id=user.id, email=user.email, token=create_access_token(user.email))

    return _make


# ---------------------------------------------------------------------------
# Session builders
# ---------------------------------------------------------------------------
def _detail_for(db, session: SessionModel, round_type: str, *, with_report: bool,
                with_question: bool) -> None:
    if round_type == "hr":
        detail = HRInterview(
            session_id=session.id,
            role="Backend Engineer",
            target_company="Cadra",
            interview_mode="standard_hr",
            max_questions=8,
            question_count=1,
            questions=[dict(QUESTION)],
            current_question=dict(QUESTION) if with_question else None,
        )
    elif round_type == "technical":
        detail = TechnicalInterview(
            session_id=session.id,
            role="Backend Engineer",
            target_company="Cadra",
            resume_context="",
            max_questions=8,
            question_count=1,
            questions=[dict(QUESTION)],
            current_question=dict(QUESTION) if with_question else None,
        )
    elif round_type == "guesstimate":
        detail = GuesstimateCase(
            session_id=session.id,
            question="Estimate the number of coffee shops in a city.",
            category="Market Sizing",
            difficulty="Intermediate",
            approach_type="top_down",
            candidate_answer="",
            audio_url=None,
        )
    else:
        return
    db.add(detail)
    db.commit()
    if with_report:
        session.report = {"fixture": "AUTH-C report placeholder"}
        session.status = "completed"
        session.overall_score = 0.0
        db.commit()


def make_target(db, owner_id: Optional[int], ep: Endpoint, *,
                with_recording: bool = False) -> SessionModel:
    """Create exactly the row the endpoint needs, so a denial can never be a missing fixture.

    `with_report` is forced for the /report endpoints and `current_question` for the answer
    endpoints; without them the handler would 400/404 for its own reasons and a passing test
    would prove nothing about ownership.
    """
    session = SessionModel(
        user_id=owner_id,
        title=f"AUTH-C {ep.name} target",
        description="Fixture row created by the AUTH-C suite.",
        duration_seconds=42.0,
        round_type=ep.round_type or "jam",
        status="in_progress",
        overall_score=None,
        round_metadata={},
        report=None,
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    if ep.needs_report:
        _detail_for(db, session, ep.round_type or "jam", with_report=True,
                    with_question=ep.needs_current_question)
    elif ep.needs_detail or ep.needs_current_question:
        _detail_for(db, session, ep.round_type or "jam", with_report=False,
                    with_question=ep.needs_current_question)

    if with_recording or ep.name == "jam.audio":
        attach_recording(db, session)
    return session


def attach_recording(db, session: SessionModel) -> Path:
    """Give a JAM session a real, readable recording inside the temp upload dir.

    get_session_audio resolves audio_path first and then video_path, and only returns a response
    for a readable non-empty file, so the owner control needs a genuine file on disk.
    """
    root = Path(settings.upload_dir).resolve()
    if TEMP_ROOT not in root.parents:
        raise AssertionError(f"refusing to write a recording outside the temp envelope: {root}")
    dest = root / "jam_audio" / f"fixture_session_{session.id}.webm"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(CLIP_BODY)
    session.audio_path = str(dest)
    db.commit()
    db.refresh(session)
    return dest


# AUTH-D: `synthesize_feedback_audio` is replaced by a stub that writes marker bytes where the real
# cache lives, so a test can prove a refused request created no file and was served no cached one.
TTS_BYTES = b"ID3auth-d-fixture-not-a-real-mp3"


def tts_cache_root() -> Path:
    root = (Path(settings.upload_dir).resolve() / "tts")
    if root != TEMP_ROOT and TEMP_ROOT not in root.parents:
        raise AssertionError(f"AUTH-D isolation tripwire: TTS cache left the envelope: {root}")
    return root


def expected_tts_file(session_id: int) -> Path:
    return tts_cache_root() / f"session_{session_id}_coach.mp3"


def write_tts_fixture(session_id: int) -> Path:
    dest = expected_tts_file(session_id)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(TTS_BYTES)
    return dest


def clear_tts_fixture(session_id: int) -> None:
    expected_tts_file(session_id).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# AUTH-D rows: a JAM session plus exactly the child records each endpoint needs
# ---------------------------------------------------------------------------
def make_analysis_target(db, owner_id: Optional[int], *, with_analysis: bool = True,
                         with_transcription: bool = True, with_feedback: bool = True,
                         with_report: bool = True,
                         status: str = "pending") -> SessionModel:
    """A JAM session in the shape the analysis routes expect.

    Missing children are deliberate for the D-A4 tests; elsewhere they would let a 404 from the
    handler's own not-found branch pass as an ownership denial.
    """
    session = SessionModel(
        user_id=owner_id,
        title="AUTH-D analysis target",
        description="Fixture row created by the AUTH-D suite.",
        duration_seconds=42.0,
        round_type="jam",
        status=status,
        overall_score=None,
        round_metadata={},
        report={"feedback_content": "Fixture feedback.", "verdict": "Fixture verdict"}
        if with_report else None,
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    if with_analysis:
        db.add(SessionAnalysis(
            session_id=session.id,
            speaking_pace=0.0,
            filler_words_count=0,
            filler_words_list={"words": [], "hesitations": []},
            clarity_score=0.0,
            eye_contact_percentage=0.0,
            posture_quality=0.0,
        ))
    if with_transcription:
        db.add(Transcription(
            session_id=session.id,
            text="Fixture transcript text created by the AUTH-D test.",
            language="en",
            confidence=0.0,
        ))
    if with_feedback:
        db.add(AIFeedback(
            session_id=session.id,
            feedback_type="overall",
            content=f"Fixture feedback for session {session.id}.",
            score=0.0,
            suggestions=[],
        ))
    db.commit()
    db.refresh(session)
    return session


def read_children(db, session_id: int) -> Dict[str, Any]:
    """Every child row an AUTH-D endpoint can touch, after expiring the identity map."""
    db.expire_all()
    session = db.get(SessionModel, session_id)
    analysis = db.scalars(select(SessionAnalysis).where(
        SessionAnalysis.session_id == session_id)).first()
    transcription = db.scalars(select(Transcription).where(
        Transcription.session_id == session_id)).first()
    feedback = db.scalars(select(AIFeedback).where(
        AIFeedback.session_id == session_id).order_by(AIFeedback.id)).all()
    return {
        "status": session.status if session else None,
        "overall_score": session.overall_score if session else None,
        "report": session.report if session else None,
        "round_metadata": session.round_metadata if session else None,
        "analysis": None if analysis is None else {
            "speaking_pace": analysis.speaking_pace,
            "filler_words_count": analysis.filler_words_count,
            "clarity_score": analysis.clarity_score,
        },
        "transcription": None if transcription is None else {
            "text": transcription.text,
            "language": transcription.language,
            "confidence": transcription.confidence,
        },
        "feedback": [{"content": f.content, "score": f.score,
                      "suggestions": list(f.suggestions or [])} for f in feedback],
    }




# ---------------------------------------------------------------------------
# Calls
# ---------------------------------------------------------------------------
def build_request(client: TestClient, ep: Endpoint, headers: Optional[Dict[str, str]],
                  *, sid: Optional[int] = None, with_audio: bool = True,
                  json_body: Optional[Dict[str, Any]] = None):
    """Issue the endpoint's real HTTP request, including a genuine upload where it accepts one."""
    path = ep.path.format(sid=sid) if sid is not None else ep.path
    sender = getattr(client, ep.method)

    if ep.method == "post" and ep.form:
        data = {"session_id": sid, **ep.form} if ep.by_id else dict(ep.form)
        files = None
        if ep.writes_disk and with_audio:
            files = {"audio_file": ("fixture-clip.webm", CLIP_BODY, "audio/webm")}
        elif ep.name == "jam.create" and with_audio:
            files = {"audio": ("fixture-clip.webm", CLIP_BODY, "audio/webm")}
        return sender(path, data=data, files=files, headers=headers)

    if ep.json_body is not None:
        return sender(path, json=json_body if json_body is not None else ep.json_body,
                      headers=headers)

    if ep.method == "delete":
        return sender(path, headers=headers)
    return sender(path, headers=headers)


# ---------------------------------------------------------------------------
# State readers
# ---------------------------------------------------------------------------
def read_session(db, session_id: int) -> Optional[Dict[str, Any]]:
    """The session exactly as the database holds it, after expiring the identity map."""
    db.expire_all()
    session = db.get(SessionModel, session_id)
    if session is None:
        return None
    return {
        "id": session.id,
        "user_id": session.user_id,
        "title": session.title,
        "description": session.description,
        "status": session.status,
        "round_type": session.round_type,
        "duration_seconds": session.duration_seconds,
        "overall_score": session.overall_score,
        "round_metadata": session.round_metadata,
        "report": session.report,
        "audio_path": session.audio_path,
        "video_path": session.video_path,
    }


def read_detail(db, session_id: int, round_type: str) -> Optional[Dict[str, Any]]:
    db.expire_all()
    if round_type == "hr":
        row = db.scalars(_select_detail(HRInterview, session_id)).first()
        if row is None:
            return None
        return {"question_count": row.question_count,
                "questions": [dict(q) for q in (row.questions or [])],
                "current_question": row.current_question}
    if round_type == "technical":
        row = db.scalars(_select_detail(TechnicalInterview, session_id)).first()
        if row is None:
            return None
        return {"question_count": row.question_count,
                "questions": [dict(q) for q in (row.questions or [])],
                "current_question": row.current_question}
    if round_type == "guesstimate":
        row = db.scalars(_select_detail(GuesstimateCase, session_id)).first()
        if row is None:
            return None
        return {"candidate_answer": row.candidate_answer,
                "approach_type": row.approach_type,
                "audio_url": row.audio_url,
                "evaluation": row.evaluation}
    return None


def _select_detail(model, session_id: int):
    return select(model).where(model.session_id == session_id)


# ---------------------------------------------------------------------------
# Upload-directory evidence
# ---------------------------------------------------------------------------
def upload_snapshot() -> Dict[str, int]:
    """Every file under the temp upload dir as relative-path -> size."""
    root = Path(settings.upload_dir).resolve()
    if TEMP_ROOT not in root.parents and root != TEMP_ROOT:
        raise AssertionError(f"AUTH-C isolation tripwire: upload dir left the envelope: {root}")
    if not root.exists():
        return {}
    found: Dict[str, int] = {}
    for path in root.rglob("*"):
        if path.is_file():
            found[str(path.relative_to(root))] = path.stat().st_size
    return found


def upload_added(before: Dict[str, int]) -> List[str]:
    after = upload_snapshot()
    return sorted(name for name in after if name not in before)


# The round handlers name each clip from (session id, question number, the *caller's* id), so the
# path is predictable and ids repeat between tests. A name-set comparison alone could miss a
# denial that overwrote an earlier test's file, so the denial tests check the exact path.
CLIP_LAYOUT = {
    "hr.answer": ("hr_audio", "session_{sid}_hr_q_{q}_{uid}.webm"),
    "guesstimate.submit": ("guesstimate_audio", "session_{sid}_guesstimate_{uid}.webm"),
    "technical.answer": ("technical_audio", "session_{sid}_q_{q}_{uid}.webm"),
}


def expected_round_clip(ep_name: str, session_id: int, caller_id: int,
                        question_number: int = 2) -> Path:
    """Where the handler *would* write this caller's clip; fixtures use question_count = 1."""
    try:
        subdir, pattern = CLIP_LAYOUT[ep_name]
    except KeyError as exc:
        raise AssertionError(f"{ep_name} does not write a clip") from exc
    root = Path(settings.upload_dir).resolve()
    dest = (root / subdir / pattern.format(sid=session_id, q=question_number,
                                           uid=caller_id)).resolve()
    if root not in dest.parents:
        raise AssertionError(f"refusing to touch a path outside the upload dir: {dest}")
    return dest


def clear_round_clip(path: Path) -> None:
    """Remove a stale clip of the same name left behind by an earlier test."""
    root = Path(settings.upload_dir).resolve()
    if root not in path.parents:
        raise AssertionError(f"refusing to delete a path outside the upload dir: {path}")
    path.unlink(missing_ok=True)


@pytest.fixture
def commit_counter(monkeypatch):
    """Count commits made by request handlers, without changing what a commit does.

    Patched on the Session class rather than the one instance, and armed only for the request
    under test, so fixture setup keeps committing normally through `make_target`.
    """
    counter = {"n": 0}
    armed = {"on": False}
    real_commit = OrmSession.commit

    def _maybe_counting(self, *args, **kwargs):
        if armed["on"]:
            counter["n"] += 1
        return real_commit(self, *args, **kwargs)

    monkeypatch.setattr(OrmSession, "commit", _maybe_counting)

    class CommitCounter:
        def arm(self) -> "CommitCounter":
            armed["on"] = True
            counter["n"] = 0
            return self

        @property
        def count(self) -> int:
            return counter["n"]

    return CommitCounter()


@pytest.fixture
def commit_fault(monkeypatch):
    """Arm a genuine commit failure, so a handler that reaches commit surfaces as a fault.

    Two things follow: a denied request must still return the exact 404 (the refusal happens
    before any transaction work), and an owner's request must surface the failure rather than
    have AUTH-C wrap it into a success.
    """

    class _CommitFault(RuntimeError):
        pass

    armed = {"on": False}
    real_commit = OrmSession.commit

    def _faulty(self, *args, **kwargs):
        if armed["on"]:
            raise _CommitFault("AUTH-C forced commit failure")
        return real_commit(self, *args, **kwargs)

    monkeypatch.setattr(OrmSession, "commit", _faulty)

    class CommitFault:
        Error = _CommitFault

        def arm(self) -> "CommitFault":
            armed["on"] = True
            return self

    return CommitFault()


# ---------------------------------------------------------------------------
# Static / AST guards
# ---------------------------------------------------------------------------
def route_source(filename: str) -> str:
    return (ROUTES_DIR / filename).read_text(encoding="utf-8")


def route_tree(filename: str) -> ast.Module:
    return ast.parse(route_source(filename))


def depends_names(tree: ast.Module, handler: str) -> set[str]:
    """Names bound through Depends(...) in a top-level handler's default arguments."""
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or node.name != handler:
            continue
        found: set[str] = set()
        defaults = [*node.args.defaults, *(kw.value for kw in node.args.kw_defaults if kw)]
        for default in defaults:
            if (
                isinstance(default, ast.Call)
                and isinstance(default.func, ast.Name)
                and default.func.id == "Depends"
                and default.args
                and isinstance(default.args[0], ast.Name)
            ):
                found.add(default.args[0].id)
        return found
    raise AssertionError(f"handler {handler} no longer exists in the parsed source")


def imported_modules(source: str) -> List[str]:
    """Every module this file imports, from `import x.y` and `from x.y import z`."""
    tree = ast.parse(source)
    found: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                found.append(node.module)
    return found


def offset_of(source: str, needle: str) -> int:
    """Character offset of the first `needle`, raising if it is absent."""
    position = source.find(needle)
    if position < 0:
        raise AssertionError(f"expected {needle!r} to appear in the source")
    return position


def body_of(source: str, handler: str) -> str:
    """The source text of one top-level handler, from its `def` line to the next top-level def.

    Ordering assertions run against a handler body rather than the whole file, so an earlier
    unrelated occurrence of a token cannot make the guard pass or fail by accident.
    """
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    starts = [n.lineno - 1 for n in tree.body
              if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    for node in tree.body:
        if (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == handler):
            begin = node.lineno - 1
            later = [s for s in starts if s > begin]
            end = min(later) if later else len(lines)
            return "".join(lines[begin:end])
    raise AssertionError(f"handler {handler} no longer exists in the parsed source")


def envelope_isolated() -> None:
    """Every stateful target must resolve inside the temp dir; the live Postgres must be unused."""
    url = str(settings.database_url)
    if not url.startswith("sqlite"):
        raise AssertionError(f"AUTH-C tests must not bind a real server: {url.split('://')[0]}")
    temp_root = str(TEMP_ROOT.resolve())
    targets = {
        "DATABASE_URL": url,
        "UPLOAD_DIR": str(settings.upload_dir),
        "LOGS_DIR": str(settings.logs_dir),
    }
    for label, value in targets.items():
        resolved = value if value.startswith("sqlite") else str(Path(value).resolve())
        if temp_root not in resolved:
            raise AssertionError(f"AUTH-C isolation tripwire: {label} left the envelope: {value}")


@pytest.fixture(autouse=True)
def envelope_check():
    envelope_isolated()


# ---------------------------------------------------------------------------
# Denial evidence collector
# ---------------------------------------------------------------------------
@dataclass
class DenialShape:
    status: int
    body: str
    content_type: str
    www_authenticate: Optional[str]

    @property
    def key(self) -> Tuple[Any, ...]:
        return (self.status, self.body, self.content_type, self.www_authenticate)


def shape_of(response) -> DenialShape:
    return DenialShape(
        status=response.status_code,
        body=response.text,
        content_type=response.headers.get("content-type", ""),
        www_authenticate=response.headers.get("www-authenticate"),
    )
