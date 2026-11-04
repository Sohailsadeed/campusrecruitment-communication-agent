"""M-18 — session responses must not carry server-side filesystem paths.

`Session.audio_path` / `Session.video_path` hold absolute paths on the recording disk, and until now
`SessionOut` serialised both, so every session response handed any authenticated caller (and, before
AUTH-C, any caller at all) the owner's server-side layout. The fix is response-layer only: the ORM
columns stay, because `session_media.get_session_audio_path`, `analysis.py` and the audio route all
read them, and playback goes through the canonical authenticated route
`GET /api/sessions/{id}/audio`, published as `SessionDetailOut.audio_url`.

Each test therefore has two halves: the row really does hold the path (otherwise a pass would only
prove a missing fixture), and the response really does not.
"""
from __future__ import annotations

import ntpath
import posixpath
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest
from session_fixtures import (  # noqa: F401  (session_app/alias_app/analysis_app/make_account/stubbed_processing are fixtures)
    CALLER_ID,
    CLIP_BODY,
    NOT_FOUND_DETAIL,
    VICTIM_ID,
    analysis_app,
    alias_app,
    attach_recording,
    authd_endpoint,
    build_request,
    endpoint,
    make_account,
    make_analysis_target,
    make_target,
    read_session,
    session_app,
    stubbed_processing,
)

LEAKED_KEYS = ("audio_path", "video_path")

# Absolute-path shapes the responses must never contain. `(?!/)` keeps URL schemes such as
# http:// out of the drive-letter match. `/api/...` values are the canonical authenticated routes
# this fix keeps, so they are the one absolute-looking form that is legal.
WINDOWS_DRIVE_PATH = re.compile(r"[A-Za-z]:(?:\\|/(?!/))")
POSIX_ABSOLUTE_ROOT = re.compile(
    r"^(?:/home/|/Users/|/root/|/var/|/opt/|/tmp/|/mnt/|/srv/|/data/|/app/|[A-Za-z]:(?:\\|/(?!/)))"
)
CANONICAL_ROUTE_PREFIXES = ("/api/", "http://", "https://")


def absolute_path_findings(node: Any, *, path_in_body: str = "$") -> List[str]:
    """Every key or value under `path_in_body` that looks like a server-side filesystem path."""
    findings: List[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key in LEAKED_KEYS:
                findings.append(f"{path_in_body}.{key} is a leaked response key")
            findings.extend(absolute_path_findings(value, path_in_body=f"{path_in_body}.{key}"))
    elif isinstance(node, list):
        for index, item in enumerate(node):
            findings.extend(absolute_path_findings(item, path_in_body=f"{path_in_body}[{index}]"))
    elif isinstance(node, str):
        if node.startswith(CANONICAL_ROUTE_PREFIXES):
            return findings
        if WINDOWS_DRIVE_PATH.search(node) or POSIX_ABSOLUTE_ROOT.match(node):
            findings.append(f"{path_in_body} value {node!r} is an absolute filesystem path")
    return findings


def assert_no_absolute_paths(response, *, label: str) -> Dict[str, Any]:
    """Check the parsed body *and* the raw text, so a path cannot hide in an unparsed form."""
    body = response.json() if response.text else {}
    findings = absolute_path_findings(body)
    assert not findings, f"{label}: {findings}\nbody={body!r}"
    for key in LEAKED_KEYS:
        assert f'"{key}"' not in response.text, f"{label}: raw body still names {key!r}"
    return body


@pytest.fixture
def principals(make_account) -> SimpleNamespace:
    return SimpleNamespace(
        victim=make_account(user_id=VICTIM_ID),
        caller=make_account(user_id=CALLER_ID),
    )


def seed_paths(db, session, *, token: str) -> Dict[str, str]:
    """Store a Windows-style path in `audio_path` and a POSIX-style one in `video_path`.

    Both styles are seeded in the same row because the recording disk is Windows while the
    deployment image is POSIX; either alone would leave half the contract untested.
    """
    windows = f"C:\\Users\\candidate\\recordings\\{token}.webm"
    posix = f"/home/candidate/recordings/{token}.webm"
    session.audio_path = windows
    session.video_path = posix
    db.commit()
    db.refresh(session)
    return {"audio_path": windows, "video_path": posix}


# ---------------------------------------------------------------------------
# Positive control — the checker actually fires on a path, so the passes below are not vacuous
# ---------------------------------------------------------------------------
def test_the_checker_flags_every_absolute_shape_it_is_asked_to_find():
    leaked = {
        "audio_path": "C:\\Users\\candidate\\recordings\\s_1.webm",
        "nested": {"video_path": "/home/candidate/recordings/s_1.webm"},
        "rows": [{"report": {"source": "/var/lib/speakflow/uploads/audio/s_1.webm"}}],
        "unkeyed": "D:/tmp/s_1.webm",
    }
    findings = absolute_path_findings(leaked)
    key_findings = [f for f in findings if "leaked response key" in f]
    value_findings = [f for f in findings if "absolute filesystem path" in f]
    assert sorted(key_findings) == ["$.audio_path is a leaked response key",
                                    "$.nested.video_path is a leaked response key"]
    assert len(value_findings) == 4, findings
    assert any("C:" in f for f in value_findings), value_findings
    assert any("/home/" in f for f in value_findings), value_findings
    assert any("/var/lib" in f for f in value_findings), value_findings
    assert any("D:/tmp" in f for f in value_findings), value_findings


def test_the_checker_keeps_the_canonical_authenticated_route():
    """`/api/sessions/{id}/audio` is the replacement, not a leak."""
    allowed = {"audio_url": "/api/guesstimate/audio/session_2_guesstimate_1.webm",
               "detail_url": "http://testserver/api/sessions/2/audio",
               "tone_verdict": "Measured & Structured"}
    assert absolute_path_findings(allowed) == []


# ---------------------------------------------------------------------------
# List, detail and patch answers
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("ep_name", ["jam.list", "jam.get", "jam.update"])
def test_seeded_absolute_paths_never_reach_a_session_response(session_app, db_session, principals,
                                                             ep_name):
    ep = endpoint(ep_name)
    target = make_target(db_session, principals.caller.id, ep)
    seeded = seed_paths(db_session, target, token=f"leakcheck-{ep_name}")

    response = build_request(session_app, ep, principals.caller.auth, sid=target.id)

    assert response.status_code == 200, response.text
    assert_no_absolute_paths(response, label=ep_name)
    stored = read_session(db_session, target.id)
    assert stored["audio_path"] == seeded["audio_path"], "the seed did not persist"
    assert stored["video_path"] == seeded["video_path"], "the seed did not persist"
    # Each style is absolute on the platform it models, so each is proved with that platform's
    # matcher; `pathlib` on this host would call the POSIX seed relative.
    assert ntpath.isabs(stored["audio_path"]) and posixpath.isabs(stored["video_path"])


def test_detail_publishes_the_canonical_audio_route_instead_of_the_path(session_app, db_session,
                                                                       principals):
    target = make_target(db_session, principals.caller.id, endpoint("jam.get"),
                         with_recording=True)
    real_path = read_session(db_session, target.id)["audio_path"]
    assert real_path and Path(real_path).is_absolute(), "the fixture recording path is unusable"

    body = assert_no_absolute_paths(
        build_request(session_app, endpoint("jam.get"), principals.caller.auth, sid=target.id),
        label="jam.get")

    assert body["audio_url"] == f"http://testserver/api/sessions/{target.id}/audio"
    assert real_path not in str(body)


# ---------------------------------------------------------------------------
# Creation — the endpoint mints the absolute path itself, so this is the real thing
# ---------------------------------------------------------------------------
def test_multipart_create_does_not_echo_the_path_it_just_wrote(session_app, db_session,
                                                               principals):
    response = build_request(session_app, endpoint("jam.create"), principals.caller.auth)

    assert response.status_code == 201, response.text
    created = assert_no_absolute_paths(response, label="jam.create")
    stored = read_session(db_session, created["id"])
    assert stored["audio_path"], "the uploaded recording was not persisted"
    assert Path(stored["audio_path"]).is_absolute()
    assert str(Path(stored["audio_path"]).parent) not in response.text


def test_json_create_and_the_following_detail_stay_path_free(session_app, db_session, principals):
    created = build_request(session_app, endpoint("jam.create_json"), principals.caller.auth)
    assert created.status_code == 201, created.text
    created_id = assert_no_absolute_paths(created, label="jam.create_json")["id"]

    detail = build_request(session_app, endpoint("jam.get"), principals.caller.auth,
                           sid=created_id)
    assert detail.status_code == 200, detail.text
    body = assert_no_absolute_paths(detail, label="jam.get of a created session")
    assert body["audio_url"] is None, "a session with no recording advertised a playback route"


# ---------------------------------------------------------------------------
# Other response variants that reuse the same schema
# ---------------------------------------------------------------------------
def test_the_jam_alias_mounts_share_the_same_answer(alias_app, db_session, principals):
    target = make_target(db_session, principals.caller.id, endpoint("jam.get"),
                         with_recording=True)
    seeded = seed_paths(db_session, target, token="leakcheck-alias")

    listed = alias_app.get("/api/jam/api/sessions", headers=principals.caller.auth)
    assert listed.status_code == 200, listed.text
    assert_no_absolute_paths(listed, label="alias jam.list")

    detail = alias_app.get(f"/api/jam/api/sessions/{target.id}", headers=principals.caller.auth)
    assert detail.status_code == 200, detail.text
    assert_no_absolute_paths(detail, label="alias jam.get")
    assert read_session(db_session, target.id)["audio_path"] == seeded["audio_path"]


def test_analyze_does_not_echo_the_paths_it_reads(analysis_app, db_session, principals,
                                                  stubbed_processing):
    target = make_analysis_target(db_session, principals.caller.id)
    real_path = attach_recording(db_session, target)
    posix_marker = "/home/candidate/recordings/leakcheck-analyze.webm"
    target.video_path = posix_marker
    db_session.commit()

    response = build_request(analysis_app, authd_endpoint("analysis.analyze"),
                             principals.caller.auth, sid=target.id)

    assert response.status_code == 200, response.text
    body = assert_no_absolute_paths(response, label="analysis.analyze")
    assert body["audio_url"] == f"http://testserver/api/sessions/{target.id}/audio"
    assert "analysis.transcribe_audio" in stubbed_processing.calls, (
        "/analyze never reached the code that reads the path, so this proves nothing")
    stored = read_session(db_session, target.id)
    assert stored["audio_path"] == str(real_path) and stored["video_path"] == posix_marker
    assert str(real_path) not in response.text and posix_marker not in response.text


# ---------------------------------------------------------------------------
# Playback and ownership are unchanged
# ---------------------------------------------------------------------------
def test_the_owner_still_replays_through_the_authenticated_endpoint(session_app, db_session,
                                                                    principals):
    target = make_target(db_session, principals.caller.id, endpoint("jam.audio"))

    detail = build_request(session_app, endpoint("jam.get"), principals.caller.auth,
                           sid=target.id)
    audio = build_request(session_app, endpoint("jam.audio"), principals.caller.auth,
                          sid=target.id)

    assert detail.status_code == 200, detail.text
    assert audio.status_code == 200, audio.text
    assert audio.content == CLIP_BODY
    assert audio.headers.get("content-type", "").startswith("audio/webm")
    assert "private" in audio.headers.get("cache-control", "")
    assert_no_absolute_paths(detail, label="jam.get before replay")


def test_another_user_still_cannot_replay_or_read_the_recording(session_app, db_session,
                                                                principals):
    target = make_target(db_session, principals.caller.id, endpoint("jam.audio"))

    audio = build_request(session_app, endpoint("jam.audio"), principals.victim.auth,
                          sid=target.id)
    detail = build_request(session_app, endpoint("jam.get"), principals.victim.auth,
                           sid=target.id)
    listed = build_request(session_app, endpoint("jam.list"), principals.victim.auth)

    for response, label in ((audio, "victim jam.audio"), (detail, "victim jam.get")):
        assert response.status_code == 404, f"{label}: got {response.status_code} {response.text!r}"
        assert response.json() == {"detail": NOT_FOUND_DETAIL}, label
    assert listed.status_code == 200, listed.text
    assert target.id not in {row["id"] for row in listed.json()}
    assert_no_absolute_paths(listed, label="victim jam.list")


def test_a_denied_response_does_not_describe_the_recording_it_withheld(session_app, db_session,
                                                                       principals):
    """A 404 is the whole answer: no path, no filename, no clue about the disk layout."""
    target = make_target(db_session, principals.caller.id, endpoint("jam.get"),
                         with_recording=True)
    real = Path(read_session(db_session, target.id)["audio_path"])

    denial = build_request(session_app, endpoint("jam.get"), principals.victim.auth,
                           sid=target.id)

    assert denial.status_code == 404, denial.text
    assert denial.text == '{"detail":"Session not found"}'
    assert real.name not in denial.text and str(real.parent) not in denial.text


@pytest.mark.parametrize("ep_name", ["jam.list", "jam.get", "jam.create", "jam.update"])
def test_anonymous_callers_are_still_turned_away_first(session_app, db_session, ep_name):
    ep = endpoint(ep_name)
    target = make_target(db_session, CALLER_ID, ep) if ep.by_id else None
    sid = target.id if target is not None else None

    response = build_request(session_app, ep, None, sid=sid)

    assert response.status_code == 401, f"{ep_name}: {response.status_code} {response.text[:120]!r}"
