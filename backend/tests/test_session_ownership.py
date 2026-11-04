"""AUTH-C — session ownership enforcement, written before the fix.

One root cause, twelve test categories: a handler that takes a session id from the caller never
proves the session belongs to that caller, and the collection handlers answer an anonymous request
out of a guest pool keyed on the literal user id 1.

Every denial test runs in the same order: the owner's own control first (so a pass can never be a
wrong-route 404, a 422 or a missing fixture), then the exact status, then the exact body, and only
then the persisted state.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest
from session_fixtures import (  # noqa: F401  (session_app/alias_app/make_account/stubbed_processing/commit_counter/commit_fault/envelope_check are fixtures)
    ALL_ENDPOINTS,
    BACKEND_DIR,
    BAD_AUTH_HEADERS,
    BY_ID_ENDPOINTS,
    CALLER_ID,
    CLIP_BODY,
    COLLECTION_ENDPOINTS,
    GUEST_ID,
    HANDLER_COUNTS,
    NOT_FOUND_DETAIL,
    SERVICES_DIR,
    UNAUTHENTICATED,
    VICTIM_ID,
    WWW_AUTHENTICATE,
    Endpoint,
    alias_app,
    body_of,
    build_request,
    clear_round_clip,
    commit_counter,
    commit_fault,
    depends_names,
    endpoint,
    envelope_check,
    envelope_isolated,
    expected_round_clip,
    imported_modules,
    make_account,
    make_target,
    offset_of,
    read_detail,
    read_session,
    route_source,
    route_tree,
    session_app,
    shape_of,
    stubbed_processing,
    upload_added,
    upload_snapshot,
)

ABSENT_ID = 987_654

DENIED_BODY = {"detail": NOT_FOUND_DETAIL}
# Starlette renders JSONResponse with compact separators, so compare against the same form.
DENIED_BODY_JSON = json.dumps(DENIED_BODY, separators=(",", ":"))

ROUND_READ_SHAPES: Dict[str, List[str]] = {
    "hr.session": ["session_id", "role", "target_company", "interview_mode",
                   "current_question", "question_count", "max_questions", "is_complete",
                   "questions", "report", "overall_score", "created_at"],
    "hr.report": ["session_id", "role", "target_company", "interview_mode", "overall_score",
                  "report", "questions", "created_at"],
    "guesstimate.session": ["session_id", "question", "category", "difficulty", "approach_type",
                            "candidate_answer", "audio_url", "is_complete", "overall_score",
                            "evaluation", "created_at"],
    "guesstimate.report": ["session_id", "question", "category", "difficulty", "approach_type",
                           "candidate_answer", "audio_url", "overall_score", "evaluation",
                           "created_at"],
    "technical.session": ["session_id", "role", "target_company", "company_tier",
                          "current_question", "question_count", "max_questions", "is_complete",
                          "questions", "report", "overall_score"],
    "technical.report": ["session_id", "role", "target_company", "company_tier", "overall_score",
                         "report", "questions", "created_at"],
}

SESSION_OUT_KEYS = ["id", "user_id", "title", "description", "round_type", "overall_score",
                    "round_metadata", "report", "duration_seconds",
                    "status", "created_at"]
SESSION_DETAIL_KEYS = SESSION_OUT_KEYS + ["transcription", "analysis", "feedback", "audio_url"]

PROGRESS_NAMES = [e.name for e in COLLECTION_ENDPOINTS if e.name.startswith("progress")]
PROGRESS_SHAPES: Dict[str, Any] = {
    "progress.summary": dict,
    "progress.metrics": list,
    "progress.technical": dict,
    "progress.guesstimate": dict,
    "progress.hr": dict,
    "progress.readiness": dict,
}

ANSWER_ENDPOINTS = ["hr.answer", "guesstimate.submit", "technical.answer"]

# Recorded, not asserted as a discriminator: a 404 raised without headers carries no
# WWW-Authenticate at all, so its presence or absence cannot tell the three cases apart.
ORACLE_EVIDENCE: Dict[str, Optional[str]] = {}


@pytest.fixture
def principals(make_account) -> SimpleNamespace:
    return SimpleNamespace(
        guest=make_account(user_id=GUEST_ID),
        victim=make_account(user_id=VICTIM_ID),
        caller=make_account(user_id=CALLER_ID),
    )


def success_status(ep: Endpoint) -> int:
    return 204 if ep.method == "delete" else 200


def assert_exact_denial(response, *, label: str):
    """Status first, then the whole body: 403, 422, 405 or a wrong-route 404 cannot pass as this."""
    shape = shape_of(response)
    assert response.status_code == 404, (
        f"{label}: expected 404, got {response.status_code} {response.text!r}")
    content_type = response.headers.get("content-type", "")
    assert content_type.startswith("application/json"), (
        f"{label}: expected a JSON denial, got content-type {content_type!r}")
    assert response.text == DENIED_BODY_JSON, (
        f"{label}: expected body {DENIED_BODY_JSON!r}, got {response.text!r}")
    assert response.json() == DENIED_BODY
    return shape


# ---------------------------------------------------------------------------
# Category 1 — authentication: all 22 handlers × 4 bad-credential forms
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("header", BAD_AUTH_HEADERS)
@pytest.mark.parametrize("ep_name", [e.name for e in ALL_ENDPOINTS],
                         ids=[e.name for e in ALL_ENDPOINTS])
def test_bad_credentials_are_rejected_on_every_endpoint(session_app, db_session, principals,
                                                        ep_name, header):
    ep = endpoint(ep_name)
    # The target row exists and belongs to someone else, so a 401 here cannot be a 404 in disguise.
    target = make_target(db_session, principals.victim.id, ep)
    headers = {"Authorization": header} if header is not None else None

    response = build_request(session_app, ep, headers, sid=target.id)

    assert response.status_code == 401, (
        f"{ep.name}: a caller with {header or 'no Authorization header'} got "
        f"{response.status_code} {response.text!r} — the endpoint answers unverified requests")
    assert response.json() == {"detail": UNAUTHENTICATED}
    assert response.headers.get("www-authenticate") == WWW_AUTHENTICATE


def test_valid_token_for_a_deleted_subject_is_rejected(session_app, db_session, principals,
                                                       make_account):
    from sqlalchemy import delete

    from app.models.user import User

    ep = endpoint("jam.get")
    target = make_target(db_session, principals.victim.id, ep)
    gone = make_account(email="deleted-subject@ownership.test")
    db_session.execute(delete(User).where(User.email == gone.email))
    db_session.commit()

    response = build_request(session_app, ep, {"Authorization": f"Bearer {gone.token}"},
                             sid=target.id)
    assert response.status_code == 401
    assert response.json() == {"detail": UNAUTHENTICATED}


# ---------------------------------------------------------------------------
# Category 2 — ownership denial: a foreign owner, and a NULL-owner orphan
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("ep_name", [e.name for e in BY_ID_ENDPOINTS],
                         ids=[e.name for e in BY_ID_ENDPOINTS])
def test_foreign_session_denied_on_every_by_id_endpoint(session_app, db_session, principals,
                                                        stubbed_processing, ep_name):
    ep = endpoint(ep_name)
    control = make_target(db_session, principals.caller.id, ep)
    victim_target = make_target(db_session, principals.victim.id, ep)
    before = read_session(db_session, victim_target.id)
    before_detail = read_detail(db_session, victim_target.id, ep.round_type or "jam")

    # 1. Owner control: this endpoint and this fixture genuinely resolve, so the denial below is
    #    not a wrong route, a round-type mismatch or a missing detail row.
    control_response = build_request(session_app, ep, principals.caller.auth, sid=control.id)
    assert control_response.status_code == success_status(ep), (
        f"{ep.name}: owner control returned {control_response.status_code} "
        f"{control_response.text!r}")

    # The control is expected to run the pipeline and write its own recording, so the evidence that
    # the denial did neither is snapshotted only now — otherwise the caller's own work would be
    # attributed to the refused request.
    stubbed_processing.calls.clear()
    files_before = upload_snapshot()

    # 2. exact status, 3. exact body.
    denial = build_request(session_app, ep, principals.caller.auth, sid=victim_target.id)
    assert_exact_denial(denial, label=f"{ep.name} foreign")

    # 4. Only now the persisted state: the victim's row is exactly as it was.
    assert read_session(db_session, victim_target.id) == before, (
        f"{ep.name}: the denial changed the victim's stored row")
    assert read_detail(db_session, victim_target.id, ep.round_type or "jam") == before_detail
    assert stubbed_processing.count() == 0, (
        f"{ep.name}: the denial reached {stubbed_processing.names}")
    assert upload_added(files_before) == [], (
        f"{ep.name}: the denial wrote {upload_added(files_before)}")


@pytest.mark.parametrize("ep_name", [e.name for e in BY_ID_ENDPOINTS],
                         ids=[e.name for e in BY_ID_ENDPOINTS])
def test_null_owner_orphan_denied_on_every_by_id_endpoint(session_app, db_session, principals,
                                                          ep_name):
    ep = endpoint(ep_name)
    control = make_target(db_session, principals.caller.id, ep)
    orphan = make_target(db_session, None, ep)
    assert orphan.user_id is None
    before = read_session(db_session, orphan.id)

    assert build_request(session_app, ep, principals.caller.auth,
                         sid=control.id).status_code == success_status(ep)

    denial = build_request(session_app, ep, principals.caller.auth, sid=orphan.id)
    assert_exact_denial(denial, label=f"{ep.name} null-owner")
    assert read_session(db_session, orphan.id) == before


@pytest.mark.parametrize("ep_name", [e.name for e in BY_ID_ENDPOINTS],
                         ids=[e.name for e in BY_ID_ENDPOINTS])
def test_no_endpoint_still_answers_403_for_a_foreign_session(session_app, db_session,
                                                             principals, ep_name):
    """The old 403 proved a session existed; AUTH-C must retire that oracle."""
    ep = endpoint(ep_name)
    victim_target = make_target(db_session, principals.victim.id, ep)
    denial = build_request(session_app, ep, principals.caller.auth, sid=victim_target.id)
    assert denial.status_code != 403, (
        f"{ep.name}: still answers 403 {denial.text!r}; the existence oracle survives")
    assert "Access denied" not in denial.text


# ---------------------------------------------------------------------------
# Category 3 — foreign, orphan and absent are byte-for-byte indistinguishable
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("ep_name", [e.name for e in BY_ID_ENDPOINTS],
                         ids=[e.name for e in BY_ID_ENDPOINTS])
def test_foreign_orphan_and_absent_are_byte_identical(session_app, db_session, principals,
                                                      ep_name):
    ep = endpoint(ep_name)
    victim_target = make_target(db_session, principals.victim.id, ep)
    orphan = make_target(db_session, None, ep)

    foreign = shape_of(build_request(session_app, ep, principals.caller.auth, sid=victim_target.id))
    orphaned = shape_of(build_request(session_app, ep, principals.caller.auth, sid=orphan.id))
    absent = shape_of(build_request(session_app, ep, principals.caller.auth, sid=ABSENT_ID))

    assert (foreign.status, foreign.body) == (404, DENIED_BODY_JSON)
    assert orphaned.key == foreign.key, f"{ep.name}: orphan differs from foreign: {orphaned.key}"
    assert absent.key == foreign.key, f"{ep.name}: absent id differs from foreign: {absent.key}"
    ORACLE_EVIDENCE[ep.name] = foreign.www_authenticate


def test_the_recorded_denial_headers_are_uniform():
    assert ORACLE_EVIDENCE, "the oracle test recorded nothing"
    values = set(ORACLE_EVIDENCE.values())
    assert len(values) == 1, ORACLE_EVIDENCE


# ---------------------------------------------------------------------------
# Category 4 — a denied round operation must not reach expensive processing
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("ep_name", ANSWER_ENDPOINTS)
def test_denied_round_answer_triggers_no_processing(session_app, db_session, principals,
                                                    stubbed_processing, ep_name):
    ep = endpoint(ep_name)
    victim_target = make_target(db_session, principals.victim.id, ep)
    stubbed_processing.calls.clear()

    denial = build_request(session_app, ep, principals.caller.auth, sid=victim_target.id)

    assert_exact_denial(denial, label=ep_name)
    assert stubbed_processing.count() == 0, (
        f"{ep.name}: the refusal still ran {stubbed_processing.names} on a recording the caller "
        f"does not own")


@pytest.mark.parametrize("ep_name", ANSWER_ENDPOINTS)
def test_owner_round_answer_does_reach_the_pipeline(session_app, db_session, principals,
                                                    stubbed_processing, ep_name):
    """Positive control for the assertion above: the stubs are the attributes the route imports."""
    ep = endpoint(ep_name)
    target = make_target(db_session, principals.caller.id, ep)
    stubbed_processing.calls.clear()

    response = build_request(session_app, ep, principals.caller.auth, sid=target.id)

    assert response.status_code == 200, response.text
    label = ep_name.split(".")[0]
    assert stubbed_processing.count(f"{label}.transcribe_audio") == 1
    assert stubbed_processing.count(f"{label}.analyze_speech_emotion") == 1


# ---------------------------------------------------------------------------
# Category 5 — a denied round answer must not touch the disk
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("ep_name", ANSWER_ENDPOINTS)
def test_denied_round_answer_writes_no_recording(session_app, db_session, principals, ep_name):
    ep = endpoint(ep_name)
    victim_target = make_target(db_session, principals.victim.id, ep)
    clip = expected_round_clip(ep_name, victim_target.id, principals.caller.id)
    clear_round_clip(clip)
    before = upload_snapshot()

    denial = build_request(session_app, ep, principals.caller.auth, sid=victim_target.id)

    assert_exact_denial(denial, label=ep_name)
    assert not clip.exists(), (
        f"{ep.name}: the refusal still stored the caller's recording at {clip.name} in a session "
        f"they do not own")
    assert upload_added(before) == [], (
        f"{ep.name}: the denial wrote {upload_added(before)}")


@pytest.mark.parametrize("ep_name", ANSWER_ENDPOINTS)
def test_owner_round_answer_writes_the_recording_it_owns(session_app, db_session, principals,
                                                         ep_name):
    ep = endpoint(ep_name)
    target = make_target(db_session, principals.caller.id, ep)
    clip = expected_round_clip(ep_name, target.id, principals.caller.id)
    clear_round_clip(clip)

    response = build_request(session_app, ep, principals.caller.auth, sid=target.id)

    assert response.status_code == 200, response.text
    assert clip.exists(), f"{ep.name}: the owner's own clip never reached {clip}"
    assert clip.read_bytes() == CLIP_BODY


# ---------------------------------------------------------------------------
# Category 6 — owner happy paths keep their response shapes
# ---------------------------------------------------------------------------
def test_owner_get_session_keeps_the_detail_shape(session_app, db_session, principals):
    ep = endpoint("jam.get")
    target = make_target(db_session, principals.caller.id, ep, with_recording=True)

    response = build_request(session_app, ep, principals.caller.auth, sid=target.id)

    assert response.status_code == 200, response.text
    body = response.json()
    assert sorted(body) == sorted(SESSION_DETAIL_KEYS)
    assert body["id"] == target.id
    assert body["user_id"] == principals.caller.id
    assert body["audio_url"] == f"http://testserver/api/sessions/{target.id}/audio"
    assert body["transcription"] is None and body["analysis"] is None
    assert body["feedback"] == []


def test_owner_audio_streams_the_original_recording(session_app, db_session, principals):
    ep = endpoint("jam.audio")
    target = make_target(db_session, principals.caller.id, ep)

    response = build_request(session_app, ep, principals.caller.auth, sid=target.id)

    assert response.status_code == 200, response.text
    assert response.content == CLIP_BODY
    assert response.headers.get("content-type", "").startswith("audio/webm")
    assert "inline" in response.headers.get("content-disposition", "")
    assert response.headers.get("cache-control") == "private, max-age=3600"


def test_owner_audio_of_a_session_without_a_recording_still_reports_absent(session_app, db_session,
                                                                          principals):
    """AUTH-C changes who may ask, not what a missing file means for its owner."""
    session = make_target(db_session, principals.caller.id, endpoint("jam.get"))
    session.audio_path = None
    session.video_path = None
    db_session.commit()

    response = build_request(session_app, endpoint("jam.audio"), principals.caller.auth,
                             sid=session.id)
    assert response.status_code == 404
    assert response.json() == {"detail": "Original recording unavailable"}


def test_owner_list_sessions_returns_only_its_own_rows(session_app, db_session, principals):
    mine = make_target(db_session, principals.caller.id, endpoint("jam.get"))
    theirs = make_target(db_session, principals.victim.id, endpoint("jam.get"))
    orphan = make_target(db_session, None, endpoint("jam.get"))

    response = build_request(session_app, endpoint("jam.list"), principals.caller.auth)

    assert response.status_code == 200, response.text
    rows = response.json()
    assert isinstance(rows, list)
    assert {row["id"] for row in rows} == {mine.id}
    assert sorted(rows[0]) == sorted(SESSION_OUT_KEYS)
    assert {theirs.id, orphan.id}.isdisjoint({row["id"] for row in rows})


def test_owner_update_returns_the_patched_row(session_app, db_session, principals):
    ep = endpoint("jam.update")
    target = make_target(db_session, principals.caller.id, ep)

    response = build_request(session_app, ep, principals.caller.auth, sid=target.id,
                             json_body={"status": "completed", "title": "Renamed by the owner"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert sorted(body) == sorted(SESSION_OUT_KEYS)
    assert body["title"] == "Renamed by the owner"
    assert body["status"] == "completed"
    stored = read_session(db_session, target.id)
    assert stored["title"] == "Renamed by the owner"
    assert stored["user_id"] == principals.caller.id


def test_owner_delete_removes_only_that_row(session_app, db_session, principals):
    doomed = make_target(db_session, principals.caller.id, endpoint("jam.delete"))
    keeper = make_target(db_session, principals.caller.id, endpoint("jam.get"))

    response = build_request(session_app, endpoint("jam.delete"), principals.caller.auth,
                             sid=doomed.id)

    assert response.status_code == 204, response.text
    assert response.text == ""
    assert read_session(db_session, doomed.id) is None
    assert read_session(db_session, keeper.id) is not None


@pytest.mark.parametrize("ep_name", sorted(ROUND_READ_SHAPES))
def test_owner_round_reads_keep_their_shapes(session_app, db_session, principals, ep_name):
    ep = endpoint(ep_name)
    target = make_target(db_session, principals.caller.id, ep)

    response = build_request(session_app, ep, principals.caller.auth, sid=target.id)

    assert response.status_code == 200, response.text
    assert sorted(response.json()) == sorted(ROUND_READ_SHAPES[ep_name])
    assert response.json()["session_id"] == target.id


@pytest.mark.parametrize("ep_name", ANSWER_ENDPOINTS)
def test_owner_round_answer_response_shape(session_app, db_session, principals, stubbed_processing,
                                           ep_name):
    ep = endpoint(ep_name)
    target = make_target(db_session, principals.caller.id, ep)

    response = build_request(session_app, ep, principals.caller.auth, sid=target.id)

    assert response.status_code == 200, response.text
    body = response.json()
    if ep_name == "guesstimate.submit":
        expected = ["audio_url", "evaluation", "overall_score", "session_id", "vocal_delivery"]
    else:
        expected = ["audio_url", "evaluation", "is_complete", "max_questions", "next_question",
                    "question_count", "report", "session_id", "vocal_delivery"]
    assert sorted(body) == sorted(expected)
    assert body["session_id"] == target.id
    assert body["audio_url"], "the uploaded clip was not published back to its owner"


# ---------------------------------------------------------------------------
# Category 7 — creation always persists the authenticated caller
# ---------------------------------------------------------------------------
def test_multipart_create_persists_the_authenticated_caller(session_app, db_session, principals):
    ep = endpoint("jam.create")

    response = build_request(session_app, ep, principals.caller.auth)

    assert response.status_code == 201, response.text
    created = response.json()
    assert sorted(created) == sorted(SESSION_OUT_KEYS)
    assert created["user_id"] == principals.caller.id
    stored = read_session(db_session, created["id"])
    assert stored["user_id"] == principals.caller.id
    assert stored["audio_path"], "the uploaded recording was not persisted"


def test_json_create_persists_the_authenticated_caller(session_app, db_session, principals):
    ep = endpoint("jam.create_json")

    response = build_request(session_app, ep, principals.caller.auth)

    assert response.status_code == 201, response.text
    created = response.json()
    assert created["user_id"] == principals.caller.id
    assert read_session(db_session, created["id"])["user_id"] == principals.caller.id


def test_created_sessions_are_invisible_to_other_accounts(session_app, db_session, principals):
    created = build_request(session_app, endpoint("jam.create_json"),
                            principals.caller.auth).json()

    assert_exact_denial(build_request(session_app, endpoint("jam.get"), principals.victim.auth,
                                      sid=created["id"]), label="jam.get after create")
    listed = build_request(session_app, endpoint("jam.list"), principals.victim.auth).json()
    assert created["id"] not in {row["id"] for row in listed}


# ---------------------------------------------------------------------------
# Category 8 — the six progress handlers plus the list: scoped, and no guest pool
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("ep_name", PROGRESS_NAMES + ["jam.list"])
def test_collection_endpoints_do_not_answer_the_guest_pool(session_app, db_session, principals,
                                                           ep_name):
    """The defect: an anonymous request was served from user 1's rows plus every orphan row."""
    ep = endpoint(ep_name)
    pool_member = make_target(db_session, GUEST_ID, endpoint("jam.get"))
    orphan = make_target(db_session, None, endpoint("jam.get"))
    assert pool_member.user_id == GUEST_ID and orphan.user_id is None

    response = build_request(session_app, ep, None)

    assert response.status_code == 401, (
        f"{ep_name}: answered {response.status_code} with {response.text[:120]!r} for an "
        f"anonymous caller; the guest pool still serves user 1 and orphan telemetry")


@pytest.mark.parametrize("ep_name", PROGRESS_NAMES + ["jam.list"])
def test_authenticated_scope_is_unchanged_by_removing_foreign_rows(session_app, db_session,
                                                                   principals, ep_name):
    """Shape-independent preservation: the caller's payload cannot depend on rows they can't own.

    Answers with a foreign row and an orphan row present must be byte-equal to the same answers
    after those rows are gone. Anything else means the payload is reading them.
    """
    from sqlalchemy import delete

    from app.models.session import Session as SessionModel

    ep = endpoint(ep_name)
    round_type = {"progress.technical": "technical", "progress.guesstimate": "guesstimate",
                  "progress.hr": "hr"}.get(ep_name, "jam")
    mine = make_target(db_session, principals.caller.id, endpoint("jam.get"))
    mine.round_type = round_type
    theirs = make_target(db_session, principals.victim.id, endpoint("jam.get"))
    theirs.round_type = round_type
    orphan = make_target(db_session, None, endpoint("jam.get"))
    orphan.round_type = round_type
    db_session.commit()

    with_strangers = build_request(session_app, ep, principals.caller.auth).json()
    assert isinstance(with_strangers, PROGRESS_SHAPES.get(ep_name, list))

    db_session.execute(
        delete(SessionModel).where(SessionModel.id.in_([theirs.id, orphan.id])))
    db_session.commit()

    without_strangers = build_request(session_app, ep, principals.caller.auth).json()
    assert without_strangers == with_strangers, (
        f"{ep_name}: the response for the owner changed once rows they cannot own were deleted, "
        f"so the endpoint was reading them")


# ---------------------------------------------------------------------------
# Category 9 — the /api/jam alias is covered by securing the shared handlers
# ---------------------------------------------------------------------------
def test_alias_mount_shares_the_protected_handler(alias_app, db_session, principals):
    victim_target = make_target(db_session, principals.victim.id, endpoint("jam.get"))
    mine = make_target(db_session, principals.caller.id, endpoint("jam.get"))

    control = alias_app.get(f"/api/jam/api/sessions/{mine.id}", headers=principals.caller.auth)
    assert control.status_code == 200, control.text

    denial = alias_app.get(f"/api/jam/api/sessions/{victim_target.id}",
                           headers=principals.caller.auth)
    assert_exact_denial(denial, label="alias jam.get")

    anonymous = alias_app.get(f"/api/jam/api/sessions/{victim_target.id}")
    assert anonymous.status_code == 401


# ---------------------------------------------------------------------------
# Category 10 — static / AST guards
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("ep_name", [e.name for e in ALL_ENDPOINTS],
                         ids=[e.name for e in ALL_ENDPOINTS])
def test_every_auth_c_handler_binds_the_fail_closed_resolver(ep_name):
    ep = endpoint(ep_name)
    bound = depends_names(route_tree(ep.router_file), ep.handler)
    assert "get_current_user" in bound, (
        f"{ep.router_file}::{ep.handler} binds {sorted(bound)}; it still accepts an anonymous "
        f"caller")
    assert not bound & {"_get_optional_user", "get_optional_current_user"}, (
        f"{ep.router_file}::{ep.handler} still binds an optional resolver: {sorted(bound)}")


@pytest.mark.parametrize("filename", ["sessions.py", "progress.py"])
def test_the_optional_resolver_is_gone_from_the_session_keyed_routers(filename):
    source = route_source(filename)
    assert "_get_optional_user" not in source, f"{filename} still defines or uses the resolver"
    assert "get_optional_current_user" not in source


def test_progress_does_not_import_the_sessions_router():
    """The dependency direction is routes -> services -> models, never route -> route."""
    imports = imported_modules(route_source("progress.py"))
    offending = [module for module in imports if module.startswith("app.routes.sessions")]
    assert not offending, offending


@pytest.mark.parametrize("filename", ["sessions.py", "progress.py"])
def test_guest_pool_predicates_are_removed(filename):
    source = route_source(filename)
    for forbidden in ["user_id == 1", "user_id.is_(None)", "user_id != 1", "user_id > 1"]:
        assert forbidden not in source, f"{filename} still contains the pool predicate {forbidden!r}"


@pytest.mark.parametrize("handler", ["create_session", "create_session_json"])
def test_create_handlers_persist_the_authenticated_identity(handler):
    body = body_of(route_source("sessions.py"), handler)
    assert "current_user.id" in body
    assert "if current_user else None" not in body, f"{handler} can still write a NULL owner"


def test_sessions_router_no_longer_distinguishes_foreign_access_with_403():
    source = route_source("sessions.py")
    assert "Access denied" not in source
    assert "403" not in source
    assert "_get_session_for_user" not in source, "the permissive resolver still exists"


@pytest.mark.parametrize("ep_name", [e.name for e in ALL_ENDPOINTS],
                         ids=[e.name for e in ALL_ENDPOINTS])
def test_the_shared_helper_is_used_by_every_handler(ep_name):
    ep = endpoint(ep_name)
    body = body_of(route_source(ep.router_file), ep.handler)
    helpers = ["owned_session(", "owned_round_session(", "owned_session_scope("]
    used = [token for token in helpers if token in body]
    if ep.name in {"jam.create", "jam.create_json"}:
        assert "current_user.id" in body, body
    else:
        assert used, f"{ep.router_file}::{ep.handler} uses none of the shared helpers"


def test_ownership_service_exists_and_depends_only_downwards():
    import app.services.session_ownership as service  # noqa: F401

    source = (SERVICES_DIR / "session_ownership.py").read_text(encoding="utf-8")
    imports = imported_modules(source)
    offending = [module for module in imports if module.startswith("app.routes")]
    assert not offending, f"a service must not import a route module: {offending}"
    assert any(module.startswith("app.models") for module in imports), imports
    assert "Session not found" in source


def test_ownership_service_import_does_not_pull_in_the_routers():
    """A fresh interpreter inside the same temp envelope proves the import graph is acyclic."""
    if not str(os.environ.get("DATABASE_URL", "")).startswith("sqlite"):
        raise AssertionError("refusing to spawn a child that could reach the live database")
    code = (
        "import sys, app.services.session_ownership\n"
        "routes = sorted(n for n in sys.modules if n.startswith('app.routes'))\n"
        "print('ROUTES:' + ','.join(routes))\n"
        "assert not routes, routes\n"
        "print('ACYCLIC-OK')\n"
    )
    result = subprocess.run([sys.executable, "-c", code], cwd=str(BACKEND_DIR),
                            env=dict(os.environ), capture_output=True, text=True, timeout=180)
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    assert "ACYCLIC-OK" in result.stdout


def test_ownership_check_precedes_every_side_effect():
    """Ordering inside the handler bodies: no expensive or irreversible step may run first.

    Every effect is named in the shape the handler actually writes it in, and a missing effect is a
    failure rather than a skip — an absent string here would otherwise disable the check silently.
    """
    pairs = [
        ("hr.py", "submit_hr_answer", "owned_round_session(",
         ["tx.stage(", "asyncio.gather", "db.commit()", "evaluate_hr_answer("]),
        ("guesstimate.py", "submit_guesstimate_answer", "owned_round_session(",
         ["tx.stage(", "asyncio.gather", "db.commit()", "evaluate_guesstimate("]),
        ("technical.py", "submit_technical_answer", "owned_round_session(",
         ["tx.stage(", "asyncio.gather", "db.commit()", "interview_graph.ainvoke"]),
        ("sessions.py", "delete_session", "owned_session(", ["db.delete("]),
        ("sessions.py", "update_session", "owned_session(", ["db.commit()"]),
        ("sessions.py", "get_session_audio", "owned_session(", ["FileResponse("]),
        ("sessions.py", "get_session", "owned_session(", ["return detail"]),
    ]
    for filename, handler, guard, effects in pairs:
        body = body_of(route_source(filename), handler)
        position = offset_of(body, guard)
        for effect in effects:
            assert effect in body, (
                f"{filename}::{handler} no longer contains {effect!r}; this ordering check has "
                f"gone stale and must be re-targeted, not left to pass vacuously")
            assert offset_of(body, effect) > position, (
                f"{filename}::{handler} reaches {effect!r} before the ownership check")


# ---------------------------------------------------------------------------
# Category 11 — transaction discipline
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("ep_name", [e.name for e in BY_ID_ENDPOINTS],
                         ids=[e.name for e in BY_ID_ENDPOINTS])
def test_denied_request_reaches_no_commit(session_app, db_session, principals, commit_counter,
                                          ep_name):
    ep = endpoint(ep_name)
    victim_target = make_target(db_session, principals.victim.id, ep)
    counter = commit_counter.arm()

    denial = build_request(session_app, ep, principals.caller.auth, sid=victim_target.id)

    assert_exact_denial(denial, label=ep_name)
    assert counter.count == 0, (
        f"{ep.name}: committed {counter.count} time(s) against a session the caller does not own")


@pytest.mark.parametrize("ep_name", [e.name for e in BY_ID_ENDPOINTS],
                         ids=[e.name for e in BY_ID_ENDPOINTS])
def test_a_forced_commit_fault_does_not_change_a_denial(session_app, db_session, principals,
                                                        commit_fault, ep_name):
    """The refusal must not depend on the transaction: with commit broken it is still the 404."""
    ep = endpoint(ep_name)
    victim_target = make_target(db_session, principals.victim.id, ep)
    fault = commit_fault.arm()

    denial = build_request(session_app, ep, principals.caller.auth, sid=victim_target.id)

    assert_exact_denial(denial, label=f"{ep.name} under a commit fault")
    assert read_session(db_session, victim_target.id) is not None
    assert fault is not None


@pytest.mark.parametrize("ep_name", ["jam.update", "jam.delete", "hr.answer"])
def test_an_owner_fault_surfaces_instead_of_becoming_a_success(session_app, db_session,
                                                               principals, commit_fault, ep_name):
    """No new boundary may swallow a failed write into a successful response."""
    ep = endpoint(ep_name)
    target = make_target(db_session, principals.caller.id, ep)
    fault = commit_fault.arm()

    with pytest.raises(fault.Error):
        build_request(session_app, ep, principals.caller.auth, sid=target.id)


# ---------------------------------------------------------------------------
# Category 12 — exclusions stay excluded
# ---------------------------------------------------------------------------
def test_technical_audio_route_no_longer_declares_a_missing_identity():
    """C-04 is closed: the route now binds the requester and delegates to the AUTH-E resolver.

    This test used to pin the gap so AUTH-C could not claim it. The gap is fixed, so the pin now
    holds the fix in place instead — dropping either dependency reopens it.
    """
    bound = depends_names(route_tree("technical.py"), "serve_technical_audio")
    assert bound == {"get_current_user", "get_db"}, bound
    body = body_of(route_source("technical.py"), "serve_technical_audio")
    assert "resolve_technical_audio_path" in body, body


def test_resume_status_still_uses_the_optional_resolver():
    bound = depends_names(route_tree("technical.py"), "get_resume_status")
    assert bound == {"get_optional_current_user"}, bound


@pytest.mark.parametrize("handler", ["start_hr_interview", "start_guesstimate_session",
                                     "start_technical_interview"])
def test_start_handlers_are_not_rewired(handler):
    filename = {"start_hr_interview": "hr.py",
                "start_guesstimate_session": "guesstimate.py",
                "start_technical_interview": "technical.py"}[handler]
    body = body_of(route_source(filename), handler)
    assert "owned_" not in body, f"{handler} was pulled into AUTH-C scope"


@pytest.mark.parametrize("filename,handler,resolver", [
    ("hr.py", "serve_hr_audio", "get_current_user"),
    ("guesstimate.py", "serve_guesstimate_audio", "get_current_user"),
    ("technical.py", "serve_technical_audio", "get_current_user"),
])
def test_auth_e_audio_handlers_are_untouched(filename, handler, resolver):
    bound = depends_names(route_tree(filename), handler)
    assert resolver in bound, bound
    body = body_of(route_source(filename), handler)
    assert f"resolve_{filename[:-3]}_audio_path(" in body, body
    assert "audio_file_response(" in body, body


def test_the_auth_e_service_module_is_unchanged():
    source = (SERVICES_DIR / "audio_ownership.py").read_text(encoding="utf-8")
    assert "Audio recording file not found." in source
    assert "def owned_round_session" not in source


# AUTH-D moved `analysis.py` and `feedback.py` out of this list: securing those five handlers is
# that task's scope, and they now import the helper on purpose. The remaining two are still
# deliberately untouched, and the 22-handler inventory below is unchanged.
@pytest.mark.parametrize("filename", ["coach.py", "emotion_stream.py"])
def test_out_of_scope_route_modules_do_not_import_the_new_helper(filename):
    imports = imported_modules(route_source(filename))
    assert not any("session_ownership" in module for module in imports), imports


def test_the_route_inventory_is_exactly_twenty_two():
    assert len(ALL_ENDPOINTS) == 22
    assert len(BY_ID_ENDPOINTS) == 13
    assert len(COLLECTION_ENDPOINTS) == 9
    assert sum(HANDLER_COUNTS.values()) == 22
    for filename, count in HANDLER_COUNTS.items():
        names = {e.name for e in ALL_ENDPOINTS if e.router_file == filename}
        assert len(names) == count, (filename, sorted(names))


# ---------------------------------------------------------------------------
# Category 13 — environment and wiring invariants
# ---------------------------------------------------------------------------
def test_envelope_is_isolated_and_no_live_database_is_bound():
    envelope_isolated()


def test_the_stubbed_processors_replace_the_ones_the_routes_import(stubbed_processing):
    """Without this, every 'zero stub calls' assertion above could be satisfied by a dead patch."""
    from app.routes import guesstimate as guesstimate_module
    from app.routes import hr as hr_module
    from app.routes import technical as technical_module

    for key in ("hr.evaluate_hr_answer", "hr.generate_hr_report", "hr.pick_next_hr_question",
                "hr.transcribe_audio", "hr.analyze_speech_emotion",
                "guesstimate.evaluate_guesstimate", "guesstimate.get_session_laya_metrics",
                "technical.interview_graph", "technical.store_performance"):
        assert key in stubbed_processing.real, key

    assert hr_module.evaluate_hr_answer is not stubbed_processing.real["hr.evaluate_hr_answer"]
    assert guesstimate_module.evaluate_guesstimate is not (
        stubbed_processing.real["guesstimate.evaluate_guesstimate"])
    assert technical_module.interview_graph is not stubbed_processing.real[
        "technical.interview_graph"]


def test_the_defect_is_documented_by_the_controlled_owner_reads(session_app, db_session,
                                                                principals):
    """A readable summary of what the fix must not break: the owner keeps every private surface."""
    ep = endpoint("jam.get")
    target = make_target(db_session, principals.caller.id, ep)
    body = build_request(session_app, ep, principals.caller.auth, sid=target.id).json()
    assert body["user_id"] == principals.caller.id == CALLER_ID
