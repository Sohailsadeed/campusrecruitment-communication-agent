"""AUTH-D — analysis and feedback authorization, written before the fix.

Five handlers key on a caller-supplied session id and prove nothing about it:
`POST /analyze`, `GET /analysis`, `GET /transcription` and `GET /tts` in `analysis.py`, and
`GET /feedback` in `feedback.py`. None of them binds an identity dependency at all, so an anonymous
caller can run the whole billed pipeline on any session, read any transcript or analysis, stream any
candidate's executive-coach TTS feedback and list any session's feedback rows.

The discipline is the one AUTH-C was accepted with: owner control first, then the exact status, then
the exact body, then the persisted state — and for every refusal, proof that the refusal was the
*first* thing that happened, before Whisper, MediaPipe, prosody, the LLM, edge-tts or a commit.
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest
from conftest import BACKEND_DIR  # noqa: F401  (kept for path parity with the AUTH-C suite)
from session_fixtures import (  # noqa: F401  (analysis_app/analysis_alias_app/make_account/stubbed_processing/commit_counter/commit_fault/envelope_check are fixtures)
    AUTHD_ENDPOINTS,
    AUTHD_HANDLER_COUNTS,
    BAD_AUTH_HEADERS,
    CALLER_ID,
    CHILD_DETAIL,
    GUEST_ID,
    HANDLER_COUNTS,
    NOT_FOUND_DETAIL,
    ALL_ENDPOINTS,
    UNAUTHENTICATED,
    VICTIM_ID,
    WWW_AUTHENTICATE,
    Endpoint,
    analysis_alias_app,
    analysis_app,
    authd_endpoint,
    build_request,
    clear_tts_fixture,
    commit_counter,
    commit_fault,
    depends_names,
    envelope_check,
    envelope_isolated,
    expected_tts_file,
    imported_modules,
    make_account,
    make_analysis_target,
    offset_of,
    read_children,
    read_session,
    route_source,
    route_tree,
    stubbed_processing,
    upload_added,
    upload_snapshot,
    write_tts_fixture,
)

ABSENT_ID = 987_654

DENIED_BODY = {"detail": NOT_FOUND_DETAIL}
DENIED_BODY_JSON = json.dumps(DENIED_BODY, separators=(",", ":"))
UNAUTH_BODY_JSON = json.dumps({"detail": UNAUTHENTICATED}, separators=(",", ":"))

AUTHD_NAMES: List[str] = [e.name for e in AUTHD_ENDPOINTS]

# `analysis.py` imports these names, so patching the service modules instead would leave the route
# calling the real Whisper / MediaPipe / audEERING / Praat / Ollama / edge-tts chain.
ANALYSIS_PROCESSOR_ATTRS = (
    "transcribe_audio", "analyze_transcription", "analyze_video", "analyze_audio_prosody",
    "extract_prosody_features", "analyze_speech_emotion", "generate_feedback",
    "synthesize_feedback_audio",
)


def assert_exact_denial(response, *, label: str) -> None:
    """Status first, then the whole body: a 403, 422, 405, 500 or wrong-route 404 is not this."""
    assert response.status_code == 404, (
        f"{label}: expected 404, got {response.status_code} {response.text!r}")
    assert response.headers.get("content-type", "").startswith("application/json"), (
        f"{label}: denial is not JSON: {response.headers.get('content-type')!r}")
    assert response.text == DENIED_BODY_JSON, (
        f"{label}: denial body is {response.text!r}, want {DENIED_BODY_JSON!r}")
    assert response.json() == DENIED_BODY


def assert_exact_unauthenticated(response, *, label: str) -> None:
    assert response.status_code == 401, f"{label}: expected 401, got {response.status_code}"
    assert response.text == UNAUTH_BODY_JSON, f"{label}: body is {response.text!r}"
    assert response.headers.get("www-authenticate") == WWW_AUTHENTICATE, (
        f"{label}: no Bearer challenge on {label}")


@pytest.fixture
def principals(make_account) -> SimpleNamespace:
    return SimpleNamespace(
        guest=make_account(user_id=GUEST_ID),
        victim=make_account(user_id=VICTIM_ID),
        caller=make_account(user_id=CALLER_ID),
    )


# ---------------------------------------------------------------------------
# Category 1 — authentication: none of the five may answer anonymously
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("ep_name", AUTHD_NAMES, ids=AUTHD_NAMES)
@pytest.mark.parametrize("header", BAD_AUTH_HEADERS)
def test_bad_credentials_are_rejected_on_every_authd_endpoint(analysis_app, db_session,
                                                              principals, ep_name, header):
    ep = authd_endpoint(ep_name)
    target = make_analysis_target(db_session, principals.caller.id)
    headers = None if header is None else {"Authorization": header}
    response = build_request(analysis_app, ep, headers, sid=target.id)
    assert_exact_unauthenticated(response, label=f"{ep.name} / {header!r}")


@pytest.mark.parametrize("ep_name", AUTHD_NAMES, ids=AUTHD_NAMES)
def test_valid_token_for_a_deleted_subject_is_rejected(analysis_app, db_session,
                                                       ep_name, make_account):
    """The signature is real; the user behind it is gone. AUTH-A must still fail closed here."""
    ep = authd_endpoint(ep_name)
    gone = make_account()
    target = make_analysis_target(db_session, gone.id)
    from app.models.user import User

    # Control first: this proves the fixture produced a credential the route genuinely accepts, so
    # the refusal below is caused by the deletion and not by a broken token or a mismatched id.
    control = build_request(analysis_app, ep, gone.auth, sid=target.id)
    assert control.status_code == 200, (
        f"{ep.name}: the live-subject control returned {control.status_code} {control.text!r}")

    db_session.delete(db_session.get(User, gone.id))
    db_session.commit()

    response = build_request(analysis_app, ep, gone.auth, sid=target.id)
    assert_exact_unauthenticated(response, label=f"{ep.name} deleted-subject")


# ---------------------------------------------------------------------------
# Category 2 — ownership: foreign, NULL-owner and absent all refuse identically
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("ep_name", AUTHD_NAMES, ids=AUTHD_NAMES)
def test_foreign_session_denied_on_every_authd_endpoint(analysis_app, db_session, principals,
                                                        stubbed_processing, ep_name):
    ep = authd_endpoint(ep_name)
    control = make_analysis_target(db_session, principals.caller.id)
    victim = make_analysis_target(db_session, principals.victim.id)
    before = read_session(db_session, victim.id)
    before_children = read_children(db_session, victim.id)

    # The owner control runs the pipeline and writes its own rows, so the evidence that the denial
    # did neither is snapshotted only after it. (AUTH-C lesson: the control's footprint is not the
    # refusal's footprint.)
    control_response = build_request(analysis_app, ep, principals.caller.auth, sid=control.id)
    assert control_response.status_code == 200, (
        f"{ep.name}: owner control returned {control_response.status_code} "
        f"{control_response.text!r}")
    stubbed_processing.calls.clear()
    files_before = upload_snapshot()

    denial = build_request(analysis_app, ep, principals.caller.auth, sid=victim.id)
    assert_exact_denial(denial, label=f"{ep.name} foreign")

    assert read_session(db_session, victim.id) == before, (
        f"{ep.name}: the denial changed the victim's session row")
    assert read_children(db_session, victim.id) == before_children, (
        f"{ep.name}: the denial changed the victim's child rows")
    assert stubbed_processing.count() == 0, (
        f"{ep.name}: the denial reached {stubbed_processing.names}")
    assert upload_added(files_before) == [], (
        f"{ep.name}: the denial wrote {upload_added(files_before)}")


@pytest.mark.parametrize("ep_name", AUTHD_NAMES, ids=AUTHD_NAMES)
def test_null_owner_orphan_denied_on_every_authd_endpoint(analysis_app, db_session, principals,
                                                          ep_name):
    ep = authd_endpoint(ep_name)
    control = make_analysis_target(db_session, principals.caller.id)
    orphan = make_analysis_target(db_session, None)
    assert orphan.user_id is None
    before = read_children(db_session, orphan.id)

    assert build_request(analysis_app, ep, principals.caller.auth,
                         sid=control.id).status_code == 200

    denial = build_request(analysis_app, ep, principals.caller.auth, sid=orphan.id)
    assert_exact_denial(denial, label=f"{ep.name} null-owner")
    assert read_children(db_session, orphan.id) == before


@pytest.mark.parametrize("ep_name", AUTHD_NAMES, ids=AUTHD_NAMES)
def test_absent_session_denied_on_every_authd_endpoint(analysis_app, principals, ep_name):
    ep = authd_endpoint(ep_name)
    denial = build_request(analysis_app, ep, principals.caller.auth, sid=ABSENT_ID)
    assert_exact_denial(denial, label=f"{ep.name} absent")


DENIAL_EVIDENCE: Dict[str, Dict[str, Any]] = {}


@pytest.mark.parametrize("ep_name", AUTHD_NAMES, ids=AUTHD_NAMES)
def test_foreign_orphan_and_absent_are_byte_identical(analysis_app, db_session, principals,
                                                      ep_name):
    ep = authd_endpoint(ep_name)
    victim = make_analysis_target(db_session, principals.victim.id)
    orphan = make_analysis_target(db_session, None)

    shapes = {
        "foreign": build_request(analysis_app, ep, principals.caller.auth, sid=victim.id),
        "orphan": build_request(analysis_app, ep, principals.caller.auth, sid=orphan.id),
        "absent": build_request(analysis_app, ep, principals.caller.auth, sid=ABSENT_ID),
    }
    recorded = {}
    for kind, response in shapes.items():
        recorded[f"{kind}:{response.status_code}"] = response.text
        DENIAL_EVIDENCE[f"{ep.name}.{kind}"] = {
            "status": response.status_code,
            "body": response.text,
            "www_authenticate": response.headers.get("www-authenticate"),
        }
    assert len(set(recorded.values())) == 1, f"{ep.name}: the three legs differ: {recorded}"
    assert list(recorded.values())[0] == DENIED_BODY_JSON


def test_the_recorded_denial_headers_are_uniform():
    assert DENIAL_EVIDENCE, "the uniformity test recorded nothing"
    values = {entry["www_authenticate"] for entry in DENIAL_EVIDENCE.values()}
    # Recording this rather than asserting a signal: a 404 carrying no challenge is not evidence
    # that the header discriminates anything.
    assert values == {None}, DENIAL_EVIDENCE


@pytest.mark.parametrize("ep_name", AUTHD_NAMES, ids=AUTHD_NAMES)
def test_no_endpoint_still_answers_403(analysis_app, db_session, principals, ep_name):
    ep = authd_endpoint(ep_name)
    victim = make_analysis_target(db_session, principals.victim.id)
    denial = build_request(analysis_app, ep, principals.caller.auth, sid=victim.id)
    assert denial.status_code != 403, (
        f"{ep.name}: answers 403 {denial.text!r}; an existence oracle survives")


# ---------------------------------------------------------------------------
# Category 3 — no data, no processing, no file on a refused request
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("ep_name", AUTHD_NAMES, ids=AUTHD_NAMES)
def test_denied_request_returns_no_private_data(analysis_app, db_session, principals, ep_name):
    """The victim's own fixture strings must not appear anywhere in the refusal."""
    ep = authd_endpoint(ep_name)
    victim = make_analysis_target(db_session, principals.victim.id)
    denial = build_request(analysis_app, ep, principals.caller.auth, sid=victim.id)
    assert_exact_denial(denial, label=f"{ep.name} leak check")
    body = denial.text
    for marker in ("Fixture transcript text", "Fixture feedback for session", "Analysis not found",
                   "Transcription not found", "No feedback for session"):
        assert marker not in body, f"{ep.name}: refusal leaked {marker!r}"


def test_denied_analyze_leaves_the_session_status_untouched(analysis_app, db_session, principals,
                                                            stubbed_processing):
    """`/analyze` writes status=processing and commits before it does any work; a refusal may not."""
    ep = authd_endpoint("analysis.analyze")
    victim = make_analysis_target(db_session, principals.victim.id, status="pending")

    control = make_analysis_target(db_session, principals.caller.id, status="pending")
    assert build_request(analysis_app, ep, principals.caller.auth,
                         sid=control.id).status_code == 200
    stubbed_processing.calls.clear()

    denial = build_request(analysis_app, ep, principals.caller.auth, sid=victim.id)
    assert_exact_denial(denial, label="analyze foreign")
    assert read_session(db_session, victim.id)["status"] == "pending", (
        "the denial moved the victim's session out of pending")
    children = read_children(db_session, victim.id)
    assert children["report"] == {"feedback_content": "Fixture feedback.",
                                  "verdict": "Fixture verdict"}, "the denial rewrote the report"
    assert children["feedback"] == [{"content": f"Fixture feedback for session {victim.id}.",
                                     "score": 0.0, "suggestions": []}]


@pytest.mark.parametrize("ep_name", AUTHD_NAMES, ids=AUTHD_NAMES)
def test_denied_request_reaches_no_commit(analysis_app, db_session, principals, commit_counter,
                                          ep_name):
    ep = authd_endpoint(ep_name)
    victim = make_analysis_target(db_session, principals.victim.id)
    armed = commit_counter.arm()
    denial = build_request(analysis_app, ep, principals.caller.auth, sid=victim.id)
    assert_exact_denial(denial, label=f"{ep.name} commit")
    assert armed.count == 0, f"{ep.name}: committed {armed.count}× against a stranger's session"


@pytest.mark.parametrize("ep_name", AUTHD_NAMES, ids=AUTHD_NAMES)
def test_a_forced_commit_fault_does_not_change_a_denial(analysis_app, db_session, principals,
                                                       commit_fault, ep_name):
    ep = authd_endpoint(ep_name)
    victim = make_analysis_target(db_session, principals.victim.id)
    commit_fault.arm()
    denial = build_request(analysis_app, ep, principals.caller.auth, sid=victim.id)
    assert_exact_denial(denial, label=f"{ep.name} commit-fault")


def test_an_owner_analyze_fault_surfaces_instead_of_becoming_a_success(
        analysis_app, db_session, principals, commit_fault):
    """AUTH-D must not wrap a real failure into a 200 or hide it behind a denial body."""
    ep = authd_endpoint("analysis.analyze")
    target = make_analysis_target(db_session, principals.caller.id, status="pending")
    commit_fault.arm()
    with pytest.raises(commit_fault.Error):
        build_request(analysis_app, ep, principals.caller.auth, sid=target.id)


# ---------------------------------------------------------------------------
# Category 4 — /tts: no synthesis, no file, no cached bytes for a stranger
# ---------------------------------------------------------------------------
def test_denied_tts_synthesizes_nothing_and_creates_no_file(analysis_app, db_session, principals,
                                                            stubbed_processing):
    ep = authd_endpoint("analysis.tts")
    victim = make_analysis_target(db_session, principals.victim.id)
    clear_tts_fixture(victim.id)
    control = make_analysis_target(db_session, principals.caller.id)
    assert build_request(analysis_app, ep, principals.caller.auth,
                         sid=control.id).status_code == 200
    stubbed_processing.calls.clear()

    denial = build_request(analysis_app, ep, principals.caller.auth, sid=victim.id)
    assert_exact_denial(denial, label="tts foreign")
    assert stubbed_processing.count("analysis.synthesize_feedback_audio") == 0, (
        f"the denial synthesized: {stubbed_processing.names}")
    assert not expected_tts_file(victim.id).exists(), (
        f"the denial created {expected_tts_file(victim.id)}")


def test_denied_tts_does_not_serve_an_existing_cached_file(analysis_app, db_session, principals):
    """The cache hit path is the leak: a foreign caller must not get the bytes already on disk."""
    ep = authd_endpoint("analysis.tts")
    victim = make_analysis_target(db_session, principals.victim.id)
    cached = write_tts_fixture(victim.id)
    assert cached.exists()

    denial = build_request(analysis_app, ep, principals.caller.auth, sid=victim.id)
    assert_exact_denial(denial, label="tts cached-file")
    assert denial.content != cached.read_bytes(), "the denial streamed the victim's cached audio"


def test_owner_tts_returns_the_synthesized_audio(analysis_app, db_session, principals):
    ep = authd_endpoint("analysis.tts")
    target = make_analysis_target(db_session, principals.caller.id)
    clear_tts_fixture(target.id)

    response = build_request(analysis_app, ep, principals.caller.auth, sid=target.id)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("audio/mpeg"), response.headers
    assert response.content == write_tts_fixture(target.id).read_bytes()


def test_owner_tts_synthesis_failure_still_answers_503(analysis_app, db_session, principals,
                                                       monkeypatch):
    """D-A7: the existing synthesis-failure behaviour is preserved, not repurposed as a denial."""
    from app.routes import analysis as analysis_module

    ep = authd_endpoint("analysis.tts")
    target = make_analysis_target(db_session, principals.caller.id)

    async def _unavailable(session_id, text, *args, **kwargs):
        return None

    monkeypatch.setattr(analysis_module, "synthesize_feedback_audio", _unavailable)
    response = build_request(analysis_app, ep, principals.caller.auth, sid=target.id)
    assert response.status_code == 503, response.text
    assert response.json() == {"detail": "TTS synthesis currently unavailable"}


def test_owner_tts_declares_the_container_the_provider_actually_wrote(
        analysis_app, db_session, principals, tmp_path, monkeypatch):
    """Phase 07: a local engine answers in WAV, so the type and download name follow the file.

    The denial path above is untouched by this; only the shape of a successful owner response is
    checked, and an MP3 keeps the type it has always had (see the test before this one).
    """
    import wave
    from app.routes import analysis as analysis_module

    ep = authd_endpoint("analysis.tts")
    target = make_analysis_target(db_session, principals.caller.id)
    clip = tmp_path / f"session_{target.id}_coach_reply_1_0_deadbeefcafe.wav"
    with wave.open(str(clip), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(24000)
        out.writeframes(b"\x00\x00" * 2400)

    async def _local_engine(session_id, text, *args, **kwargs):
        return clip

    monkeypatch.setattr(analysis_module, "synthesize_feedback_audio", _local_engine)
    response = build_request(analysis_app, ep, principals.caller.auth, sid=target.id)

    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("audio/wav"), response.headers
    assert f"session_{target.id}_coach.wav" in response.headers.get("content-disposition", "")
    assert response.content == clip.read_bytes()


# ---------------------------------------------------------------------------
# Category 5 — owner happy paths assert response shapes, not merely a status
# ---------------------------------------------------------------------------
ANALYSIS_OUT_KEYS = {"id", "session_id", "speaking_pace", "filler_words_count",
                     "filler_words_list", "clarity_score", "eye_contact_percentage",
                     "posture_quality", "created_at"}
TRANSCRIPTION_OUT_KEYS = {"id", "session_id", "text", "language", "confidence", "created_at"}
FEEDBACK_OUT_KEYS = {"id", "session_id", "feedback_type", "content", "score", "suggestions",
                    "created_at"}


def test_owner_get_analysis_returns_the_own_analysis_row(analysis_app, db_session, principals):
    ep = authd_endpoint("analysis.get")
    target = make_analysis_target(db_session, principals.caller.id)
    response = build_request(analysis_app, ep, principals.caller.auth, sid=target.id)
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == ANALYSIS_OUT_KEYS, sorted(body)
    assert body["session_id"] == target.id
    assert target.title not in json.dumps(body), "the analysis payload grew beyond the row"


def test_owner_get_transcription_returns_the_own_transcript(analysis_app, db_session, principals):
    ep = authd_endpoint("analysis.transcription")
    target = make_analysis_target(db_session, principals.caller.id)
    response = build_request(analysis_app, ep, principals.caller.auth, sid=target.id)
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == TRANSCRIPTION_OUT_KEYS, sorted(body)
    assert body["text"].startswith("Fixture transcript text")


def test_owner_get_feedback_returns_only_its_own_rows(analysis_app, db_session, principals):
    ep = authd_endpoint("feedback.list")
    mine = make_analysis_target(db_session, principals.caller.id)
    theirs = make_analysis_target(db_session, principals.victim.id)
    response = build_request(analysis_app, ep, principals.caller.auth, sid=mine.id)
    assert response.status_code == 200, response.text
    rows = response.json()
    assert isinstance(rows, list) and len(rows) == 1, rows
    assert set(rows[0]) == FEEDBACK_OUT_KEYS, sorted(rows[0])
    assert rows[0]["session_id"] == mine.id
    assert rows[0]["content"] == f"Fixture feedback for session {mine.id}."
    # Structural, not a substring scan: ids appear inside timestamps ("2" is in "2026-11-01"), so
    # matching raw text here would fail for a reason that has nothing to do with authorization.
    assert {r["session_id"] for r in rows} == {mine.id}, rows
    assert theirs.id not in {r["session_id"] for r in rows} | {r["id"] for r in rows}, rows
    assert all(str(mine.id) in r["content"] for r in rows), rows


def test_owner_analyze_runs_the_pipeline_and_completes(analysis_app, db_session, principals,
                                                       stubbed_processing):
    """Positive control for every zero-call assertion above: these stubs are the ones the route uses."""
    ep = authd_endpoint("analysis.analyze")
    target = make_analysis_target(db_session, principals.caller.id, status="pending")
    stubbed_processing.calls.clear()

    response = build_request(analysis_app, ep, principals.caller.auth, sid=target.id)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "completed", body["status"]
    assert body["report"] and body["analysis"], body.keys()

    for name in ("transcribe_audio", "analyze_transcription", "analyze_video",
                 "analyze_audio_prosody", "generate_feedback"):
        assert stubbed_processing.count(f"analysis.{name}") >= 1, (
            f"analysis.{name} was never reached — the zero-call denials would be vacuous")


def test_denied_analyze_triggers_no_processing_at_all(analysis_app, db_session, principals,
                                                      stubbed_processing):
    ep = authd_endpoint("analysis.analyze")
    victim = make_analysis_target(db_session, principals.victim.id, status="pending")
    control = make_analysis_target(db_session, principals.caller.id, status="pending")
    assert build_request(analysis_app, ep, principals.caller.auth,
                         sid=control.id).status_code == 200
    stubbed_processing.calls.clear()

    denial = build_request(analysis_app, ep, principals.caller.auth, sid=victim.id)
    assert_exact_denial(denial, label="analyze processing")
    assert stubbed_processing.count() == 0, (
        f"the refusal still ran {stubbed_processing.names} on a session the caller does not own")


# ---------------------------------------------------------------------------
# Category 6 — D-A4: child-resource 404s survive, but only for an owner
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("ep_name", ["analysis.get", "analysis.transcription", "feedback.list"],
                         ids=["analysis.get", "analysis.transcription", "feedback.list"])
def test_owned_session_missing_the_child_keeps_its_own_detail(analysis_app, db_session,
                                                              principals, ep_name):
    expected_detail, missing = CHILD_DETAIL[ep_name][0], CHILD_DETAIL[ep_name][1]
    kwargs = {"with_analysis": missing != "analysis",
              "with_transcription": missing != "transcription",
              "with_feedback": missing != "feedback"}
    target = make_analysis_target(db_session, principals.caller.id, **kwargs)
    ep = authd_endpoint(ep_name)
    response = build_request(analysis_app, ep, principals.caller.auth, sid=target.id)
    assert response.status_code == 404, response.text
    assert response.json() == {"detail": expected_detail}, (
        f"{ep_name}: the child 404 copy changed to {response.text!r}")
    assert response.text != DENIED_BODY_JSON, (
        f"{ep_name}: the child 404 is indistinguishable from an ownership denial")


def test_the_child_404_is_only_reachable_once_ownership_is_proven(analysis_app, db_session,
                                                                  principals):
    """A victim row with no children must refuse with the uniform body, not 'Analysis not found'."""
    ep = authd_endpoint("analysis.get")
    empty = make_analysis_target(db_session, principals.victim.id, with_analysis=False)
    denial = build_request(analysis_app, ep, principals.caller.auth, sid=empty.id)
    assert_exact_denial(denial, label="child-less foreign session")


# ---------------------------------------------------------------------------
# Category 7 — /analyze failure behaviour is preserved, not swallowed
# ---------------------------------------------------------------------------
def test_owner_analyze_processing_failure_still_answers_500_and_marks_failed(
        analysis_app, db_session, principals, monkeypatch):
    from app.routes import analysis as analysis_module

    ep = authd_endpoint("analysis.analyze")
    target = make_analysis_target(db_session, principals.caller.id, status="pending")

    def _boom(path, *args, **kwargs):
        raise RuntimeError("fixture pipeline failure")

    monkeypatch.setattr(analysis_module, "transcribe_audio", _boom)
    response = build_request(analysis_app, ep, principals.caller.auth, sid=target.id)
    assert response.status_code == 500, response.text
    assert response.json() == {"detail": "Analysis failed. Please try again."}
    assert read_session(db_session, target.id)["status"] == "failed"


def test_the_ownership_gate_is_outside_the_processing_try(analysis_app, db_session, principals,
                                                          stubbed_processing):
    """If the gate sat inside the catch-all, a 404 would surface as 500 and mark the row failed."""
    ep = authd_endpoint("analysis.analyze")
    victim = make_analysis_target(db_session, principals.victim.id, status="pending")
    denial = build_request(analysis_app, ep, principals.caller.auth, sid=victim.id)
    assert_exact_denial(denial, label="gate placement")
    assert read_session(db_session, victim.id)["status"] == "pending"


# ---------------------------------------------------------------------------
# Category 8 — the /api/jam alias shares the secured handler (D-A10)
# ---------------------------------------------------------------------------
def test_alias_analyze_shares_the_protected_handler(analysis_alias_app, db_session, principals,
                                                    stubbed_processing):
    ep = authd_endpoint("analysis.analyze")
    victim = make_analysis_target(db_session, principals.victim.id, status="pending")
    control = make_analysis_target(db_session, principals.caller.id, status="pending")

    alias_path = "/api/jam/api/sessions/{sid}/analyze"
    ok = analysis_alias_app.post(alias_path.format(sid=control.id),
                                 headers=principals.caller.auth)
    assert ok.status_code == 200, ok.text
    stubbed_processing.calls.clear()

    denial = analysis_alias_app.post(alias_path.format(sid=victim.id),
                                     headers=principals.caller.auth)
    assert_exact_denial(denial, label="alias analyze")
    assert stubbed_processing.count() == 0, stubbed_processing.names

    anonymous = analysis_alias_app.post(alias_path.format(sid=victim.id))
    assert anonymous.status_code == 401, anonymous.text


# ---------------------------------------------------------------------------
# Category 9 — static guards over all five handlers
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("ep_name", AUTHD_NAMES, ids=AUTHD_NAMES)
def test_every_authd_handler_binds_the_fail_closed_resolver(ep_name):
    ep = authd_endpoint(ep_name)
    bound = depends_names(route_tree(ep.router_file), ep.handler)
    assert "get_current_user" in bound, f"{ep.name} binds {sorted(bound)}"
    assert not bound & {"_get_optional_user", "get_optional_current_user"}, (
        f"{ep.name} accepts optional authentication: {sorted(bound)}")


@pytest.mark.parametrize("ep_name", AUTHD_NAMES, ids=AUTHD_NAMES)
def test_every_authd_handler_uses_the_shared_ownership_helper(ep_name):
    ep = authd_endpoint(ep_name)
    body = route_source(ep.router_file)
    start = offset_of(body, ep.handler)
    handler_body = body[start:]
    assert "owned_session(" in handler_body, f"{ep.name} does not call owned_session"


@pytest.mark.parametrize("ep_name", AUTHD_NAMES, ids=AUTHD_NAMES)
def test_no_authd_handler_fetches_the_session_as_its_authorization(ep_name):
    """`db.get(SessionModel, …)` is a lookup, not a permission check (contract §4A)."""
    ep = authd_endpoint(ep_name)
    body = route_source(ep.router_file)
    handler_body = body[offset_of(body, ep.handler):]
    # Stop at the next top-level def so a helper below cannot be blamed for this handler.
    following = handler_body.find("\ndef ", 1)
    handler_body = handler_body[:following] if following != -1 else handler_body
    assert "db.get(SessionModel" not in handler_body, (
        f"{ep.name} still authorizes with a bare db.get")


def test_analyze_ownership_gate_precedes_its_first_write_and_the_try():
    source = route_source("analysis.py")
    handler = source[offset_of(source, "analyze_session"):]
    gate = handler.find("owned_session(")
    assert gate != -1, "analyze_session never calls owned_session"
    assert handler.find("session.status =") > gate, "status is written before ownership"
    assert handler.find("db.commit()") > gate, "a commit precedes ownership verification"
    assert handler.find("try:") > gate, "the gate is inside the catch-all try block"


@pytest.mark.parametrize("filename", sorted(AUTHD_HANDLER_COUNTS))
def test_authd_router_imports_the_shared_helper(filename):
    imports = imported_modules(route_source(filename))
    assert any("session_ownership" in module for module in imports), imports


# ---------------------------------------------------------------------------
# Category 10 — the additive registry does not disturb AUTH-C's accepted evidence
# ---------------------------------------------------------------------------
def test_the_authd_registry_is_additive_and_covers_five_handlers():
    assert len(AUTHD_ENDPOINTS) == 5
    assert sum(AUTHD_HANDLER_COUNTS.values()) == 5
    for filename, count in AUTHD_HANDLER_COUNTS.items():
        names = {e.name for e in AUTHD_ENDPOINTS if e.router_file == filename}
        assert len(names) == count, (filename, sorted(names))


def test_auth_c_instrumentation_is_untouched_by_auth_d():
    assert len(ALL_ENDPOINTS) == 22
    assert sum(HANDLER_COUNTS.values()) == 22
    assert not ({e.name for e in AUTHD_ENDPOINTS} & {e.name for e in ALL_ENDPOINTS})


def test_the_stubbed_analysis_processors_replace_the_ones_the_route_imports(stubbed_processing):
    """Without this, every zero-call assertion above could be satisfied by a dead patch."""
    from app.routes import analysis as analysis_module

    for name in ANALYSIS_PROCESSOR_ATTRS:
        key = f"analysis.{name}"
        assert key in stubbed_processing.real, key
        current = getattr(analysis_module, name)
        assert current is not stubbed_processing.real[key], (
            f"{name} was never patched — the route would call the real processor")


def test_the_authd_envelope_is_isolated():
    envelope_isolated()
