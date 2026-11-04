"""AUTH-E (C-02/C-03/C-06/C-08/C-09/C-10): authenticated session ownership on audio playback.

A clip is served only when the requester's own user id is in the filename, the session that
filename names is owned by that user, the route's own detail row lists that exact URL, and the
confined file is a readable, non-empty regular file. Denials are uniform: an authorization miss
is byte-for-byte a "not found" — never 403, never 500, never a hint of existence.

The route-level tests never import the service module at collection time, so a pre-implementation
RED run reports the real defect (a foreign clip is served) instead of an import error.
"""
from __future__ import annotations

import ast
import os
import shutil
from pathlib import Path
from urllib.parse import quote

import pytest
from audio_fixtures import (  # noqa: F401  (audio_app/make_account/clean_clip_dirs are fixtures)
    GUESSTIMATE_BODY,
    HR_BODY,
    NOT_FOUND_DETAIL,
    audio_app,
    clean_clip_dirs,
    create_guesstimate_session,
    create_hr_session,
    guesstimate_filename,
    guesstimate_url,
    hr_filename,
    hr_url,
    make_account,
    write_clip,
)
from conftest import BACKEND_DIR, TEMP_ROOT

from config import settings

AUTO = object()


def service():
    """Late import so the behavioural tests stay runnable before the service exists."""
    from app.services import audio_ownership

    return audio_ownership


def upload_root() -> Path:
    return Path(settings.upload_dir).resolve()


@pytest.fixture()
def owner(audio_app, make_account):
    return make_account()


@pytest.fixture()
def intruder(audio_app, make_account):
    return make_account()


def hr_recording(db, user_id, *, q_num=1, max_questions=4, questions=AUTO, with_detail=True):
    """An HR session owned by `user_id` whose JSON blob lists its own clip. File not written."""
    session = create_hr_session(
        db, user_id, max_questions=max_questions, question_count=q_num, with_detail=with_detail
    )
    name = hr_filename(session.id, q_num, user_id)
    if with_detail:
        session.hr_detail.questions = (
            [{"question_key": f"q{q_num}", "audio_url": hr_url(name)}] if questions is AUTO else questions
        )
        db.commit()
    return session, name


def guesstimate_recording(db, user_id, *, stored=AUTO, with_detail=True):
    """A guesstimate session owned by `user_id`. Returns (session, canonical filename)."""
    session = create_guesstimate_session(db, user_id, with_detail=with_detail)
    name = guesstimate_filename(session.id, user_id)
    if with_detail:
        session.guesstimate_detail.audio_url = guesstimate_url(name) if stored is AUTO else stored
        db.commit()
    return session, name


# ---------------------------------------------------------------------------
# HR route: the happy path keeps working exactly as before
# ---------------------------------------------------------------------------

def test_owner_receives_their_own_hr_clip(audio_app, db_session, owner):
    _, name = hr_recording(db_session, owner.id)
    write_clip("hr_audio", name)

    response = audio_app.get(hr_url(name), headers=owner.auth)

    assert response.status_code == 200, response.text
    assert response.content == HR_BODY
    assert response.headers["content-type"].startswith("audio/webm")
    assert response.headers["cache-control"] == "private, no-store"
    # A disposition would push the browser to download the candidate recording.
    assert "content-disposition" not in response.headers


def test_range_request_still_works_for_the_owner(audio_app, db_session, owner):
    _, name = hr_recording(db_session, owner.id)
    payload = b"0123456789abcdef"
    write_clip("hr_audio", name, payload)

    response = audio_app.get(hr_url(name), headers={**owner.auth, "Range": "bytes=0-3"})

    assert response.status_code == 206
    assert response.content == b"0123"
    assert response.headers["content-range"] == f"bytes 0-3/{len(payload)}"


# ---------------------------------------------------------------------------
# HR route: authorization
# ---------------------------------------------------------------------------

def test_another_users_token_cannot_read_a_foreign_hr_clip(audio_app, db_session, owner, intruder):
    """C-02: the clip exists and this route serves it — but not to them."""
    _, name = hr_recording(db_session, owner.id)
    write_clip("hr_audio", name)

    response = audio_app.get(hr_url(name), headers=intruder.auth)

    assert response.status_code == 404
    assert response.content != HR_BODY
    assert response.json() == {"detail": NOT_FOUND_DETAIL}


def test_foreign_session_id_in_an_otherwise_own_filename_is_denied(audio_app, db_session, owner, intruder):
    """C-02 IDOR shape: victim's session id, attacker's user id, attacker-shaped file on disk."""
    session, _ = hr_recording(db_session, owner.id)
    planted = hr_filename(session.id, 1, intruder.id)
    write_clip("hr_audio", planted)

    response = audio_app.get(hr_url(planted), headers=intruder.auth)

    assert response.status_code == 404
    assert response.json() == {"detail": NOT_FOUND_DETAIL}


def test_a_planted_victim_user_id_in_the_filename_is_denied(audio_app, db_session, owner, intruder):
    """C-03: the uid group must equal the requester's id, not merely be a parseable integer."""
    session, _ = hr_recording(db_session, intruder.id)
    planted = hr_filename(session.id, 1, owner.id)
    write_clip("hr_audio", planted)

    response = audio_app.get(hr_url(planted), headers=intruder.auth)

    assert response.status_code == 404
    assert response.json() == {"detail": NOT_FOUND_DETAIL}


def test_orphan_session_is_denied(audio_app, db_session, owner):
    """user_id IS NULL means nobody owns it: deny instead of falling back to a guest identity."""
    _, name = hr_recording(db_session, None)
    write_clip("hr_audio", name)

    response = audio_app.get(hr_url(name), headers=owner.auth)

    assert response.status_code == 404
    assert response.json() == {"detail": NOT_FOUND_DETAIL}


def test_session_without_a_detail_row_is_denied(audio_app, db_session, owner):
    _, name = hr_recording(db_session, owner.id, with_detail=False)
    write_clip("hr_audio", name)

    response = audio_app.get(hr_url(name), headers=owner.auth)

    assert response.status_code == 404
    assert response.json() == {"detail": NOT_FOUND_DETAIL}


def test_unauthenticated_request_is_rejected_before_any_lookup(audio_app, db_session, owner):
    _, name = hr_recording(db_session, owner.id)
    write_clip("hr_audio", name)

    response = audio_app.get(hr_url(name))

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert response.content != HR_BODY


def test_clip_not_listed_in_the_stored_questions_is_denied(audio_app, db_session, owner):
    """C-08: owning the session is not enough — the route's own URL list must name this clip."""
    session, name = hr_recording(db_session, owner.id, questions=[])
    session.hr_detail.questions = [
        {"question_key": "q2", "audio_url": hr_url(hr_filename(session.id, 2, owner.id))}
    ]
    db_session.commit()
    write_clip("hr_audio", name)

    response = audio_app.get(hr_url(name), headers=owner.auth)

    assert response.status_code == 404
    assert response.json() == {"detail": NOT_FOUND_DETAIL}


def test_question_number_above_the_planned_range_is_served_when_the_json_lists_it(
    audio_app, db_session, owner
):
    """C-07 deliberately kept: a lost question_count update must not make a real clip unplayable."""
    _, name = hr_recording(db_session, owner.id, q_num=5, max_questions=4)
    write_clip("hr_audio", name)

    response = audio_app.get(hr_url(name), headers=owner.auth)

    assert response.status_code == 200
    assert response.content == HR_BODY


@pytest.mark.parametrize("q_num", [0, 9, 10, 42])
def test_question_number_outside_the_supported_range_is_denied(audio_app, db_session, owner, q_num):
    session, _ = hr_recording(db_session, owner.id)
    name = hr_filename(session.id, q_num, owner.id)
    session.hr_detail.questions = [{"question_key": f"q{q_num}", "audio_url": hr_url(name)}]
    db_session.commit()
    write_clip("hr_audio", name)

    response = audio_app.get(hr_url(name), headers=owner.auth)

    assert response.status_code == 404
    assert response.content != HR_BODY


# ---------------------------------------------------------------------------
# HR route: the name and the blob are validated as raw strings, before any path work
# ---------------------------------------------------------------------------

HOSTILE_HR_NAMES = [
    "not-a-clip.webm",
    "session_1_hr_q_1_0.webm",
    "session_0_hr_q_1_1.webm",
    "session_1_hr_q_0_1.webm",
    "session_01_hr_q_1_1.webm",
    "session_1_hr_q_1_01.webm",
    "session_1_hr_q_1_12345678901234.webm",
    "session_1_hrq_1_1.webm",
    "session_1_hr_q_1_1.webm.png",
    "session_1_hr_q_1_1.WEBM",
    "Session_1_hr_q_1_1.webm",
    "session_1_hr_q_1_1x.webm",
    "xsession_1_hr_q_1_1.webm",
    "session_1_hr_q_1_1.webm\x00.png",
    "..session_1_hr_q_1_1.webm",
    "session_1\\..\\hr_q_1_1.webm",
    "session_1_hr_q_1_1 webm",
    "session_1_hr_q_1.webm",
    "session_1_hr_q_webm",
    # ١٢ is a valid Python decimal digit run but not ASCII: int() would rewrite it.
    "session_١_hr_q_1_1.webm",
]


@pytest.mark.parametrize("name", HOSTILE_HR_NAMES)
def test_non_canonical_file_names_never_reach_the_filesystem(audio_app, db_session, owner, name):
    """Grammar first, on the raw string after decoding: nothing is normalised or opened.

    The name is percent-encoded so the transport cannot reject it and Starlette hands the
    handler the exact hostile string, NUL and backslash included, as a single path segment.
    An empty segment is not in this list: the router never matches it, so it never reaches
    the handler — test_traversal_shapes_never_yield_bytes covers that shape.
    """
    upload_root().joinpath("hr_audio").mkdir(parents=True, exist_ok=True)
    (upload_root() / "hr_audio" / "other-clip.webm").write_bytes(HR_BODY)

    response = audio_app.get(f"/api/hr/audio/{quote(name, safe='')}", headers=owner.auth)

    assert response.status_code == 404, response.text
    assert response.content != HR_BODY
    assert response.json() == {"detail": NOT_FOUND_DETAIL}


@pytest.mark.parametrize(
    "raw_path",
    [
        pytest.param("/api/hr/audio/..%2F..%2Fsecret.webm", id="encoded-slash"),
        pytest.param("/api/hr/audio/%2E%2E%2Fsecret.webm", id="encoded-dot-dot"),
        pytest.param("/api/hr/audio/..%5Csecret.webm", id="encoded-backslash"),
        pytest.param("/api/hr/audio/", id="empty-filename"),
        pytest.param("/api/hr/audio", id="no-filename-segment"),
    ],
)
def test_traversal_shapes_never_yield_bytes(audio_app, db_session, owner, raw_path):
    upload_root().parent.joinpath("secret.webm").write_bytes(HR_BODY)

    response = audio_app.get(raw_path, headers=owner.auth)

    assert response.status_code == 404
    assert response.content != HR_BODY


HOSTILE_STORED_URLS = [
    pytest.param("http://evil.example/api/hr/audio/session_1_hr_q_1_1.webm", id="absolute-foreign-host"),
    pytest.param("//evil.example/api/hr/audio/session_1_hr_q_1_1.webm", id="protocol-relative"),
    pytest.param("http:///api/hr/audio/session_1_hr_q_1_1.webm", id="scheme-without-authority"),
    pytest.param("file:///api/hr/audio/session_1_hr_q_1_1.webm", id="file-scheme"),
    pytest.param("https:/api/hr/audio/session_1_hr_q_1_1.webm", id="one-slash-https"),
    pytest.param("/api/hr/audio/session_1_hr_q_1_1.webm?download=1", id="query-suffix"),
    pytest.param("/api/hr/audio/session_1_hr_q_1_1.webm#fragment", id="fragment-suffix"),
    pytest.param("/api/hr/audio/session_1_hr_q_1_1.webm;sessionid=1", id="semicolon-params"),
    pytest.param("/api/hr/audio//session_1_hr_q_1_1.webm", id="doubled-slash"),
    pytest.param("/api/hr/audio/./session_1_hr_q_1_1.webm", id="dot-segment"),
    pytest.param("\\api\\hr\\audio\\session_1_hr_q_1_1.webm", id="backslash-path"),
    pytest.param("/api/hr/audio/session_1_hr_q_1_1.webm\x00", id="nul-in-url"),
    pytest.param("", id="empty-string"),
    pytest.param(None, id="none"),
    pytest.param(1234, id="non-string"),
    pytest.param(["/api/hr/audio/session_1_hr_q_1_1.webm"], id="list-instead-of-string"),
]


@pytest.mark.parametrize("stored", [param.values[0] for param in HOSTILE_STORED_URLS])
def test_a_tampered_stored_url_does_not_authorize_anything(audio_app, db_session, owner, stored):
    _, name = hr_recording(db_session, owner.id, questions=[{"question_key": "q1", "audio_url": stored}])
    write_clip("hr_audio", name)

    response = audio_app.get(hr_url(name), headers=owner.auth)

    assert response.status_code == 404
    assert response.content != HR_BODY


MALFORMED_QUESTIONS = [
    pytest.param({"q1": "/api/hr/audio/session_1_hr_q_1_1.webm"}, id="questions-is-dict"),
    pytest.param("[]", id="questions-is-string"),
    pytest.param([None, "x", 7, []], id="entries-not-dicts"),
    pytest.param([{}], id="entry-without-audio-url"),
    pytest.param([{"audio_url": 123}], id="audio-url-not-a-string"),
    pytest.param([{"audio_url": ""}], id="audio-url-empty"),
    pytest.param([{"audio_url": None}], id="audio-url-none"),
    pytest.param([], id="questions-empty"),
]


@pytest.mark.parametrize("questions", [param.values[0] for param in MALFORMED_QUESTIONS])
def test_malformed_hr_json_denies_instead_of_crashing(audio_app, db_session, owner, questions):
    """A corrupted blob is a 404, not a 500 — and never a way to reach the file."""
    _, name = hr_recording(db_session, owner.id, questions=questions)
    write_clip("hr_audio", name)

    response = audio_app.get(hr_url(name), headers=owner.auth)

    assert response.status_code == 404, response.text
    assert response.content != HR_BODY


# ---------------------------------------------------------------------------
# HR route: the filesystem is only reached after every logical check
# ---------------------------------------------------------------------------

def test_missing_file_is_denied(audio_app, db_session, owner):
    _, name = hr_recording(db_session, owner.id)

    response = audio_app.get(hr_url(name), headers=owner.auth)

    assert response.status_code == 404
    assert response.json() == {"detail": NOT_FOUND_DETAIL}


def test_empty_file_is_denied(audio_app, db_session, owner):
    """A zero-byte clip is a failed upload, not a successful playback."""
    _, name = hr_recording(db_session, owner.id)
    write_clip("hr_audio", name, b"")

    response = audio_app.get(hr_url(name), headers=owner.auth)

    assert response.status_code == 404
    assert response.json() == {"detail": NOT_FOUND_DETAIL}


def test_directory_in_place_of_a_clip_is_denied(audio_app, db_session, owner):
    _, name = hr_recording(db_session, owner.id)
    (upload_root() / "hr_audio" / name).mkdir(parents=True, exist_ok=True)

    response = audio_app.get(hr_url(name), headers=owner.auth)

    assert response.status_code == 404
    assert response.json() == {"detail": NOT_FOUND_DETAIL}


def _link_directory(target: Path, link: Path) -> str:
    """Point `link` at `target` as a directory; returns the mechanism actually used."""
    try:
        os.symlink(target, link, target_is_directory=True)
        return "symlink"
    except OSError:
        pass
    import _winapi  # Windows only, and a junction needs no elevated privilege

    _winapi.CreateJunction(str(target), str(link))
    return "junction"


def test_a_clip_directory_repointed_outside_the_upload_root_is_denied(audio_app, db_session, owner):
    """Defence in depth: a legitimately named, legitimately listed clip is still refused when the
    directory holding it resolves outside settings.upload_dir."""
    _, name = hr_recording(db_session, owner.id)
    outside = TEMP_ROOT / "outside-upload-dir"
    outside.mkdir(parents=True, exist_ok=True)
    (outside / name).write_bytes(HR_BODY)

    link = upload_root() / "hr_audio"
    if link.is_dir():
        # Only ever remove a directory we have just proved is genuinely ours, never a link.
        assert link.resolve().is_relative_to(upload_root())
        shutil.rmtree(link)
    try:
        _link_directory(outside, link)
    except OSError as exc:
        pytest.skip(f"platform cannot link directories: {exc}")

    # Prove the escape is real before claiming the denial was earned.
    escaped = (link / name).resolve()
    assert (link / name).read_bytes() == HR_BODY
    assert not escaped.is_relative_to(upload_root())

    response = audio_app.get(hr_url(name), headers=owner.auth)

    assert response.status_code == 404
    assert response.content != HR_BODY


def test_symlink_that_escapes_the_upload_dir_is_denied(audio_app, db_session, owner):
    _, name = hr_recording(db_session, owner.id)
    outside = TEMP_ROOT / "outside-upload-clip.webm"
    outside.write_bytes(HR_BODY)
    link = upload_root() / "hr_audio" / name
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.symlink(outside, link, target_is_directory=False)
    except OSError as exc:  # Windows without developer mode cannot create file symlinks
        pytest.skip(f"platform cannot create file symlinks: {exc}")

    response = audio_app.get(hr_url(name), headers=owner.auth)

    assert response.status_code == 404
    assert response.content != HR_BODY


def test_an_accepted_clip_name_can_carry_no_path_separator():
    """The confinement is by construction first: the name handed to the filesystem is rebuilt
    from validated integers, so it cannot contain a separator, a dot-dot or a NUL."""
    for name in ("session_1_hr_q_1_1.webm", "session_999999999999_hr_q_8_1.webm"):
        clip = service().parse_hr_filename(name)
        assert clip is not None
        for forbidden in ("/", "\\", "\x00", "..", os.sep, os.altsep or "\x01"):
            assert forbidden not in clip.filename
        assert clip.stored_url == hr_url(clip.filename)


def test_every_denial_is_byte_identical(audio_app, db_session, owner, intruder):
    """No oracle: 'not yours', 'not recorded', 'not there' and 'not a clip' are one response."""
    _, theirs = hr_recording(db_session, owner.id)
    write_clip("hr_audio", theirs)
    _, ghost = hr_recording(db_session, owner.id, q_num=2)  # listed in the blob, never written

    foreign = audio_app.get(hr_url(theirs), headers=intruder.auth)
    missing_file = audio_app.get(hr_url(ghost), headers=owner.auth)
    bad_name = audio_app.get(hr_url("session_999999_hr_q_1_999999.webm"), headers=owner.auth)

    assert foreign.status_code == 404
    for response in (missing_file, bad_name):
        assert response.status_code == 404
        assert response.headers["content-type"] == foreign.headers["content-type"]
        assert response.json() == foreign.json() == {"detail": NOT_FOUND_DETAIL}


# ---------------------------------------------------------------------------
# Guesstimate route
# ---------------------------------------------------------------------------

def test_owner_receives_their_own_guesstimate_clip(audio_app, db_session, owner):
    _, name = guesstimate_recording(db_session, owner.id)
    write_clip("guesstimate_audio", name, GUESSTIMATE_BODY)

    response = audio_app.get(guesstimate_url(name), headers=owner.auth)

    assert response.status_code == 200, response.text
    assert response.content == GUESSTIMATE_BODY
    assert response.headers["cache-control"] == "private, no-store"
    assert "content-disposition" not in response.headers


def test_another_users_token_cannot_read_a_foreign_guesstimate_clip(audio_app, db_session, owner, intruder):
    _, name = guesstimate_recording(db_session, owner.id)
    write_clip("guesstimate_audio", name, GUESSTIMATE_BODY)

    response = audio_app.get(guesstimate_url(name), headers=intruder.auth)

    assert response.status_code == 404
    assert response.content != GUESSTIMATE_BODY
    assert response.json() == {"detail": NOT_FOUND_DETAIL}


def test_guesstimate_case_without_a_stored_url_has_nothing_to_play(audio_app, db_session, owner):
    _, name = guesstimate_recording(db_session, owner.id, stored=None)
    write_clip("guesstimate_audio", name, GUESSTIMATE_BODY)

    response = audio_app.get(guesstimate_url(name), headers=owner.auth)

    assert response.status_code == 404
    assert response.json() == {"detail": NOT_FOUND_DETAIL}


def test_guesstimate_stored_url_naming_a_different_clip_is_denied(audio_app, db_session, owner):
    _, name = guesstimate_recording(
        db_session, owner.id, stored=guesstimate_url("session_424242_guesstimate_424242.webm")
    )
    write_clip("guesstimate_audio", name, GUESSTIMATE_BODY)

    response = audio_app.get(guesstimate_url(name), headers=owner.auth)

    assert response.status_code == 404
    assert response.content != GUESSTIMATE_BODY


def test_guesstimate_planted_victim_user_id_is_denied(audio_app, db_session, owner, intruder):
    session, _ = guesstimate_recording(db_session, intruder.id)
    planted = guesstimate_filename(session.id, owner.id)
    write_clip("guesstimate_audio", planted, GUESSTIMATE_BODY)

    response = audio_app.get(guesstimate_url(planted), headers=intruder.auth)

    assert response.status_code == 404
    assert response.content != GUESSTIMATE_BODY


def test_guesstimate_orphan_session_is_denied(audio_app, db_session, owner):
    _, name = guesstimate_recording(db_session, None)
    write_clip("guesstimate_audio", name, GUESSTIMATE_BODY)

    response = audio_app.get(guesstimate_url(name), headers=owner.auth)

    assert response.status_code == 404
    assert response.json() == {"detail": NOT_FOUND_DETAIL}


def test_guesstimate_session_without_a_case_row_is_denied(audio_app, db_session, owner):
    _, name = guesstimate_recording(db_session, owner.id, with_detail=False)
    write_clip("guesstimate_audio", name, GUESSTIMATE_BODY)

    response = audio_app.get(guesstimate_url(name), headers=owner.auth)

    assert response.status_code == 404
    assert response.json() == {"detail": NOT_FOUND_DETAIL}


def test_guesstimate_empty_file_is_denied(audio_app, db_session, owner):
    _, name = guesstimate_recording(db_session, owner.id)
    write_clip("guesstimate_audio", name, b"")

    response = audio_app.get(guesstimate_url(name), headers=owner.auth)

    assert response.status_code == 404
    assert response.json() == {"detail": NOT_FOUND_DETAIL}


def test_guesstimate_unauthenticated_request_is_rejected(audio_app, db_session, owner):
    _, name = guesstimate_recording(db_session, owner.id)
    write_clip("guesstimate_audio", name, GUESSTIMATE_BODY)

    response = audio_app.get(guesstimate_url(name))

    assert response.status_code == 401
    assert response.content != GUESSTIMATE_BODY


def test_the_two_rounds_cannot_read_through_each_other(audio_app, db_session, owner):
    """Each route's grammar is disjoint, so the other round's real clip name is denied on both."""
    _, hr_name = hr_recording(db_session, owner.id)
    _, guesstimate_name = guesstimate_recording(db_session, owner.id)
    write_clip("hr_audio", hr_name)
    write_clip("guesstimate_audio", guesstimate_name, GUESSTIMATE_BODY)

    # Both files exist and are confined; only the route that lists them may serve them.
    assert audio_app.get(hr_url(hr_name), headers=owner.auth).status_code == 200
    assert audio_app.get(guesstimate_url(guesstimate_name), headers=owner.auth).status_code == 200

    on_hr = audio_app.get(hr_url(guesstimate_name), headers=owner.auth)
    on_guesstimate = audio_app.get(guesstimate_url(hr_name), headers=owner.auth)

    assert on_hr.status_code == 404
    assert on_guesstimate.status_code == 404
    assert on_hr.content != HR_BODY
    assert on_guesstimate.content != GUESSTIMATE_BODY


# ---------------------------------------------------------------------------
# Pure helper truth tables
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "stored,expected",
    [
        pytest.param("/api/hr/audio/session_1_hr_q_1_1.webm", True, id="exact-route"),
        pytest.param("/api/hr/audio/session_1_hr_q_2_9.webm", False, id="different-clip"),
        pytest.param("/api/guesstimate/audio/session_1_hr_q_1_1.webm", False, id="other-route-prefix"),
        pytest.param("/api/hr/audio/session_1_hr_q_1_1.webm/", False, id="trailing-slash"),
        pytest.param("api/hr/audio/session_1_hr_q_1_1.webm", False, id="missing-leading-slash"),
        pytest.param("HTTP://api/hr/audio/session_1_hr_q_1_1.webm", False, id="uppercase-scheme"),
    ],
)
def test_stored_audio_path_matches_accepts_only_the_exact_route(stored, expected):
    matches = service().stored_audio_path_matches
    assert matches(stored, "/api/hr/audio/session_1_hr_q_1_1.webm") is expected


@pytest.mark.parametrize("stored", [param.values[0] for param in HOSTILE_STORED_URLS])
def test_stored_audio_path_matches_rejects_every_lookalike(stored):
    matches = service().stored_audio_path_matches
    assert matches(stored, "/api/hr/audio/session_1_hr_q_1_1.webm") is False


def test_stored_audio_path_matches_survives_a_malformed_expected_route():
    assert service().stored_audio_path_matches("/api/hr/audio/x.webm", "") is False


def test_authorized_question_urls_keeps_only_non_empty_strings():
    class _Detail:
        questions = [
            {"audio_url": "/api/hr/audio/a.webm"},
            {"audio_url": ""},
            {"audio_url": None},
            {"audio_url": 7},
            {"other": "x"},
            "not-a-dict",
            None,
        ]

    assert service().authorized_question_urls(_Detail()) == ["/api/hr/audio/a.webm"]


def test_authorized_question_urls_survives_a_missing_or_non_list_blob():
    class _Dict:
        questions = {"a": 1}

    class _Empty:
        pass

    assert service().authorized_question_urls(_Dict()) == []
    assert service().authorized_question_urls(_Empty()) == []
    assert service().authorized_question_urls(None) == []


@pytest.mark.parametrize(
    "name,session_id,question_number,user_id",
    [
        pytest.param("session_1_hr_q_1_1.webm", 1, 1, 1, id="simple"),
        pytest.param(
            "session_999999999999_hr_q_8_888888888888.webm", 999999999999, 8, 888888888888, id="twelve-digits"
        ),
        # The single-digit question group makes the tail unambiguously the user id, not q=12.
        pytest.param("session_1_hr_q_1_12.webm", 1, 1, 12, id="two-digit-user-id"),
    ],
)
def test_parse_hr_filename_accepts_canonical_names(name, session_id, question_number, user_id):
    parsed = service().parse_hr_filename(name)
    assert parsed is not None
    assert (parsed.session_id, parsed.question_number, parsed.recording_owner_id) == (
        session_id,
        question_number,
        user_id,
    )
    # The canonical reconstruction is what reaches the filesystem, never the raw string.
    assert parsed.filename == name
    assert parsed.stored_url == hr_url(name)


@pytest.mark.parametrize("name", HOSTILE_HR_NAMES)
def test_parse_hr_filename_refuses_to_guess(name):
    assert service().parse_hr_filename(name) is None


@pytest.mark.parametrize(
    "name,session_id,user_id",
    [
        pytest.param("session_1_guesstimate_1.webm", 1, 1, id="simple"),
        pytest.param("session_12_guesstimate_3456789.webm", 12, 3456789, id="long-ids"),
    ],
)
def test_parse_guesstimate_filename_accepts_canonical_names(name, session_id, user_id):
    parsed = service().parse_guesstimate_filename(name)
    assert parsed is not None
    assert (parsed.session_id, parsed.recording_owner_id) == (session_id, user_id)
    assert parsed.filename == name
    assert parsed.stored_url == guesstimate_url(name)


@pytest.mark.parametrize(
    "name",
    [
        "session_1_hr_q_1_1.webm",
        "session_1_guesstimate_1.webm.webm",
        "session_0_guesstimate_1.webm",
        "session_1_guesstimate_0.webm",
        "session_1_guesstimate_123456789012345.webm",
        "session_1_guesstimate_1.mp3",
        "session_1_guesstimate_1_1.webm",
        "session_1_guesstimate_01.webm",
        "",
    ],
)
def test_parse_guesstimate_filename_refuses_anything_else(name):
    assert service().parse_guesstimate_filename(name) is None


# ---------------------------------------------------------------------------
# Static guards on the wiring
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "filename,handler",
    [
        pytest.param("hr.py", "serve_hr_audio", id="hr"),
        pytest.param("guesstimate.py", "serve_guesstimate_audio", id="guesstimate"),
    ],
)
def test_both_audio_routes_keep_the_identity_dependency_and_gain_the_session(filename, handler):
    tree = ast.parse((BACKEND_DIR / "app" / "routes" / filename).read_text(encoding="utf-8"))
    body = next(
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == handler
    )
    resolvers = {
        node.args[0].id
        for node in ast.walk(body)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "Depends"
        and node.args
        and isinstance(node.args[0], ast.Name)
    }
    assert {"get_current_user", "get_db"} <= resolvers, f"{handler} lost a dependency: {sorted(resolvers)}"


def test_the_ownership_service_is_read_only():
    """The leaf service may not write, migrate or open its own transaction."""
    module = service()
    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    attributes = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    for forbidden in ("add", "commit", "flush", "delete", "execute", "scalars", "rollback", "begin"):
        assert forbidden not in attributes, f"audio_ownership must never call .{forbidden}()"
