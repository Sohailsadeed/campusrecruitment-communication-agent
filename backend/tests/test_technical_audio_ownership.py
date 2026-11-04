"""Technical-round audio: the same AUTH-E gate, applied to the route that had none.

Before this contract `stream_technical_audio` opened `settings.upload_dir/technical_audio/<name>`
for any caller who could name the file — no token, no session, no ownership. These tests pin the
replacement: identity first, then the session the filename names, then the round's own stored URL
list, then a confined readable file. Every refusal is the same 404 the missing clip already
produced, so a probe learns nothing about what exists.

HR and Guesstimate behaviour is not re-litigated here; test_audio_ownership.py owns that. This file
covers the Technical route plus the two cross-round seams the new router shares with them.
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
    TECHNICAL_BODY,
    audio_app,
    clean_clip_dirs,
    create_guesstimate_session,
    create_hr_session,
    create_technical_session,
    guesstimate_filename,
    guesstimate_url,
    hr_filename,
    hr_url,
    make_account,
    technical_filename,
    technical_url,
    write_clip,
)
from conftest import BACKEND_DIR, TEMP_ROOT

from config import settings

AUTO = object()

SUBDIR = "technical_audio"


def service():
    """Late import so a RED run reports the real defect instead of an import error."""
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


def technical_recording(
    db, user_id, *, q_num=1, max_questions=5, questions=AUTO, with_detail=True
):
    """A technical session owned by `user_id` whose JSON blob lists its own clip. File not written."""
    session = create_technical_session(
        db, user_id, max_questions=max_questions, question_count=q_num, with_detail=with_detail
    )
    name = technical_filename(session.id, q_num, user_id) if user_id is not None else None
    if user_id is None:
        # An orphan row still has a filename the route would have written for its owner.
        name = technical_filename(session.id, q_num, 1)
    if with_detail:
        session.technical_detail.questions = (
            [{"question_key": f"q{q_num}", "audio_url": technical_url(name)}]
            if questions is AUTO
            else questions
        )
        db.commit()
    return session, name


# ---------------------------------------------------------------------------
# The owner's playback is unchanged: same bytes, same headers, same seeking
# ---------------------------------------------------------------------------

def test_owner_receives_their_own_technical_clip(audio_app, db_session, owner):
    _, name = technical_recording(db_session, owner.id)
    write_clip(SUBDIR, name, TECHNICAL_BODY)

    response = audio_app.get(technical_url(name), headers=owner.auth)

    assert response.status_code == 200, response.text
    assert response.content == TECHNICAL_BODY
    assert response.headers["content-type"].startswith("audio/webm")
    assert response.headers["cache-control"] == "private, no-store"
    # A disposition would push the browser to download the candidate recording.
    assert "content-disposition" not in response.headers


def test_range_request_still_works_for_the_owner(audio_app, db_session, owner):
    """The report's scrub bar sends Range; the fix must not turn seeking into a failure."""
    _, name = technical_recording(db_session, owner.id)
    payload = b"0123456789abcdef"
    write_clip(SUBDIR, name, payload)

    response = audio_app.get(
        technical_url(name), headers={**owner.auth, "Range": "bytes=4-7"}
    )

    assert response.status_code == 206
    assert response.content == b"4567"
    assert response.headers["content-range"] == f"bytes 4-7/{len(payload)}"


def test_question_number_above_the_planned_range_is_served_when_the_json_lists_it(
    audio_app, db_session, owner
):
    """A lost question_count update must not make a real clip unplayable (C-07, kept for Technical)."""
    _, name = technical_recording(db_session, owner.id, q_num=7, max_questions=5)
    write_clip(SUBDIR, name, TECHNICAL_BODY)

    response = audio_app.get(technical_url(name), headers=owner.auth)

    assert response.status_code == 200, response.text
    assert response.content == TECHNICAL_BODY


def test_the_highest_supported_question_number_is_served(audio_app, db_session, owner):
    """max_questions is capped at 10, so q_10 is a clip this app really makes."""
    _, name = technical_recording(db_session, owner.id, q_num=10, max_questions=10)
    write_clip(SUBDIR, name, TECHNICAL_BODY)

    response = audio_app.get(technical_url(name), headers=owner.auth)

    assert response.status_code == 200, response.text
    assert response.content == TECHNICAL_BODY


# ---------------------------------------------------------------------------
# Authorization
# ---------------------------------------------------------------------------

def test_unauthenticated_request_is_rejected(audio_app, db_session, owner):
    """The defect this contract closes: naming the file used to be the whole credential."""
    _, name = technical_recording(db_session, owner.id)
    write_clip(SUBDIR, name, TECHNICAL_BODY)

    response = audio_app.get(technical_url(name))

    assert response.status_code == 401, response.text
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert response.content != TECHNICAL_BODY


def test_a_stale_token_is_rejected(audio_app, db_session, owner):
    _, name = technical_recording(db_session, owner.id)
    write_clip(SUBDIR, name, TECHNICAL_BODY)

    response = audio_app.get(
        technical_url(name), headers={"Authorization": "Bearer not-a-real-token"}
    )

    assert response.status_code == 401
    assert response.content != TECHNICAL_BODY


def test_another_users_token_cannot_read_a_foreign_technical_clip(
    audio_app, db_session, owner, intruder
):
    """The clip exists and the route can serve it — but not to them."""
    _, name = technical_recording(db_session, owner.id)
    write_clip(SUBDIR, name, TECHNICAL_BODY)

    response = audio_app.get(technical_url(name), headers=intruder.auth)

    assert response.status_code == 404
    assert response.content != TECHNICAL_BODY
    assert response.json() == {"detail": NOT_FOUND_DETAIL}


def test_foreign_session_id_in_an_otherwise_own_filename_is_denied(
    audio_app, db_session, owner, intruder
):
    """IDOR shape: victim's session id, attacker's user id, attacker-shaped file on disk."""
    session, _ = technical_recording(db_session, owner.id)
    planted = technical_filename(session.id, 1, intruder.id)
    write_clip(SUBDIR, planted, TECHNICAL_BODY)

    response = audio_app.get(technical_url(planted), headers=intruder.auth)

    assert response.status_code == 404
    assert response.json() == {"detail": NOT_FOUND_DETAIL}


def test_a_planted_victim_user_id_in_the_filename_is_denied(
    audio_app, db_session, owner, intruder
):
    """The uid group must equal the requester's id, not merely be a parseable integer."""
    session, _ = technical_recording(db_session, intruder.id)
    planted = technical_filename(session.id, 1, owner.id)
    write_clip(SUBDIR, planted, TECHNICAL_BODY)

    response = audio_app.get(technical_url(planted), headers=intruder.auth)

    assert response.status_code == 404
    assert response.json() == {"detail": NOT_FOUND_DETAIL}


def test_orphan_session_is_denied(audio_app, db_session, owner):
    """user_id IS NULL owns nothing: no fallback to a guest identity."""
    _, name = technical_recording(db_session, None)
    write_clip(SUBDIR, name, TECHNICAL_BODY)

    response = audio_app.get(technical_url(name), headers=owner.auth)

    assert response.status_code == 404
    assert response.json() == {"detail": NOT_FOUND_DETAIL}


def test_unknown_session_id_is_denied(audio_app, db_session, owner):
    """A made-up session id with the requester's own uid in it never reaches the filesystem."""
    name = technical_filename(987654, 1, owner.id)
    write_clip(SUBDIR, name, TECHNICAL_BODY)

    response = audio_app.get(technical_url(name), headers=owner.auth)

    assert response.status_code == 404
    assert response.content != TECHNICAL_BODY
    assert response.json() == {"detail": NOT_FOUND_DETAIL}


def test_session_without_a_technical_detail_row_is_denied(audio_app, db_session, owner):
    _, name = technical_recording(db_session, owner.id, with_detail=False)
    write_clip(SUBDIR, name, TECHNICAL_BODY)

    response = audio_app.get(technical_url(name), headers=owner.auth)

    assert response.status_code == 404
    assert response.json() == {"detail": NOT_FOUND_DETAIL}


def test_an_hr_session_has_no_technical_clips(audio_app, db_session, owner):
    """A session of another round is not this round's, even when its id is the requester's own."""
    session = create_hr_session(db_session, owner.id)
    name = technical_filename(session.id, 1, owner.id)
    write_clip(SUBDIR, name, TECHNICAL_BODY)

    response = audio_app.get(technical_url(name), headers=owner.auth)

    assert response.status_code == 404
    assert response.content != TECHNICAL_BODY


# ---------------------------------------------------------------------------
# Owning the session is not enough: the round's own blob must name this clip
# ---------------------------------------------------------------------------

def test_clip_not_listed_in_the_stored_questions_is_denied(audio_app, db_session, owner):
    session, name = technical_recording(db_session, owner.id)
    session.technical_detail.questions = [
        {"question_key": "q2", "audio_url": technical_url(technical_filename(session.id, 2, owner.id))}
    ]
    db_session.commit()
    write_clip(SUBDIR, name, TECHNICAL_BODY)

    response = audio_app.get(technical_url(name), headers=owner.auth)

    assert response.status_code == 404
    assert response.json() == {"detail": NOT_FOUND_DETAIL}


def test_empty_questions_blob_has_nothing_to_play(audio_app, db_session, owner):
    _, name = technical_recording(db_session, owner.id, questions=[])
    write_clip(SUBDIR, name, TECHNICAL_BODY)

    response = audio_app.get(technical_url(name), headers=owner.auth)

    assert response.status_code == 404
    assert response.json() == {"detail": NOT_FOUND_DETAIL}


@pytest.mark.parametrize(
    "questions",
    [
        pytest.param("not-a-list", id="string-blob"),
        pytest.param({"audio_url": "/api/technical/audio/x.webm"}, id="dict-not-list"),
        pytest.param([None], id="null-entry"),
        pytest.param(["plain-string"], id="entry-not-dict"),
        pytest.param([{"audio_url": None}], id="null-url"),
        pytest.param([{"audio_url": 7}], id="numeric-url"),
        pytest.param([{"audio_url": ["a", "b"]}], id="list-url"),
    ],
)
def test_malformed_technical_json_denies_instead_of_crashing(audio_app, db_session, owner, questions):
    _, name = technical_recording(db_session, owner.id, questions=questions)
    write_clip(SUBDIR, name, TECHNICAL_BODY)

    response = audio_app.get(technical_url(name), headers=owner.auth)

    assert response.status_code == 404
    assert response.content != TECHNICAL_BODY
    assert response.json() == {"detail": NOT_FOUND_DETAIL}


HOSTILE_STORED_URLS = [
    pytest.param(
        "http://evil.example/api/technical/audio/session_1_q_1_1.webm", id="absolute-foreign-host"),
    pytest.param("//evil.example/api/technical/audio/session_1_q_1_1.webm", id="protocol-relative"),
    pytest.param("file:///api/technical/audio/session_1_q_1_1.webm", id="file-scheme"),
    pytest.param("/api/technical/audio/session_1_q_1_1.webm?download=1", id="query-suffix"),
    pytest.param("/api/technical/audio/session_1_q_1_1.webm#fragment", id="fragment-suffix"),
    pytest.param("/api/technical/audio/session_1_q_1_1.webm;sessionid=1", id="semicolon-params"),
    pytest.param("/api/technical/audio//session_1_q_1_1.webm", id="doubled-slash"),
    pytest.param("/api/technical/audio/./session_1_q_1_1.webm", id="dot-segment"),
    pytest.param("\\api\\technical\\audio\\session_1_q_1_1.webm", id="backslash-path"),
    pytest.param("", id="empty-url"),
]


@pytest.mark.parametrize("stored", [param.values[0] for param in HOSTILE_STORED_URLS])
def test_a_tampered_stored_url_does_not_authorize_anything(audio_app, db_session, owner, stored):
    session, name = technical_recording(db_session, owner.id, questions=[{"audio_url": stored}])
    write_clip(SUBDIR, name, TECHNICAL_BODY)

    response = audio_app.get(technical_url(name), headers=owner.auth)

    assert response.status_code == 404, f"{stored!r} was accepted: {response.text}"
    assert response.content != TECHNICAL_BODY


@pytest.mark.parametrize("q_num", [0, 11, 12, 42])
def test_question_number_outside_the_supported_range_is_denied(
    audio_app, db_session, owner, q_num
):
    """max_questions is capped at 10, so no clip this app makes can carry a larger number."""
    session, _ = technical_recording(db_session, owner.id)
    name = technical_filename(session.id, q_num, owner.id)
    session.technical_detail.questions = [{"question_key": f"q{q_num}", "audio_url": technical_url(name)}]
    db_session.commit()
    write_clip(SUBDIR, name, TECHNICAL_BODY)

    response = audio_app.get(technical_url(name), headers=owner.auth)

    assert response.status_code == 404
    assert response.content != TECHNICAL_BODY


@pytest.mark.parametrize(
    "template",
    [
        pytest.param("candidate-answer.webm", id="name-the-grammar-refuses"),
        pytest.param("session_{sid}_q_01_{uid}.webm", id="padded-question-number"),
        pytest.param("session_{sid}_q_1_{uid}.WEBM", id="uppercase-extension"),
        pytest.param("session_{sid}_q_1_{uid}.webm.png", id="double-extension"),
    ],
)
def test_a_blob_that_lists_a_non_canonical_name_still_serves_nothing(
    audio_app, db_session, owner, template
):
    """The grammar is its own gate, not a convenience layered on top of the blob check.

    A row naming an arbitrary file is what a tampered or migrated blob looks like, so the request
    must be refused for being an unusable name even though the caller's own session lists it, the
    bytes are on disk under that exact name, and the canonical clip they would normalise to is on
    disk too.
    """
    session, canonical = technical_recording(db_session, owner.id)
    listed = template.format(sid=session.id, uid=owner.id)
    session.technical_detail.questions = [{"audio_url": f"/api/technical/audio/{listed}"}]
    db_session.commit()
    write_clip(SUBDIR, listed, TECHNICAL_BODY)
    write_clip(SUBDIR, canonical, TECHNICAL_BODY)

    response = audio_app.get(f"/api/technical/audio/{listed}", headers=owner.auth)

    assert response.status_code == 404, response.text
    assert response.content != TECHNICAL_BODY
    assert response.json() == {"detail": NOT_FOUND_DETAIL}


@pytest.mark.parametrize(
    "template",
    [
        pytest.param("session_0{sid}_q_1_{uid}.webm", id="zero-padded-session-id"),
        pytest.param("session_{sid}_q_01_{uid}.webm", id="zero-padded-question-number"),
        pytest.param("session_{sid}_q_1_0{uid}.webm", id="zero-padded-owner-id"),
    ],
)
def test_a_zero_padded_spelling_of_a_real_clip_serves_nothing(audio_app, db_session, owner, template):
    """A name that differs from a real clip only by leading zeroes asks the parser to normalise it.

    The session lists the canonical URL and the canonical bytes are on disk, so a parser that ran
    int() over the digits and rebuilt the name afterwards would hand this caller the owner's real
    recording; the grammar refuses the spelling before any digit is read.
    """
    session, canonical = technical_recording(db_session, owner.id)
    padded = template.format(sid=session.id, uid=owner.id)
    write_clip(SUBDIR, canonical, TECHNICAL_BODY)

    response = audio_app.get(technical_url(padded), headers=owner.auth)

    assert response.status_code == 404, response.text
    assert response.content != TECHNICAL_BODY
    assert response.json() == {"detail": NOT_FOUND_DETAIL}


# ---------------------------------------------------------------------------
# Missing files fail the same way a missing permission does
# ---------------------------------------------------------------------------

def test_missing_file_is_denied(audio_app, db_session, owner):
    _, name = technical_recording(db_session, owner.id)

    response = audio_app.get(technical_url(name), headers=owner.auth)

    assert response.status_code == 404
    assert response.json() == {"detail": NOT_FOUND_DETAIL}


def test_empty_file_is_denied(audio_app, db_session, owner):
    """A zero-byte clip is a failed upload, not a successful playback."""
    _, name = technical_recording(db_session, owner.id)
    write_clip(SUBDIR, name, b"")

    response = audio_app.get(technical_url(name), headers=owner.auth)

    assert response.status_code == 404
    assert response.json() == {"detail": NOT_FOUND_DETAIL}


def test_directory_in_place_of_a_clip_is_denied(audio_app, db_session, owner):
    _, name = technical_recording(db_session, owner.id)
    (upload_root() / SUBDIR / name).mkdir(parents=True, exist_ok=True)

    response = audio_app.get(technical_url(name), headers=owner.auth)

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


def test_a_clip_directory_repointed_outside_the_upload_root_is_denied(
    audio_app, db_session, owner
):
    """Defence in depth: a named, listed clip is still refused when its directory escapes the root."""
    _, name = technical_recording(db_session, owner.id)
    outside = TEMP_ROOT / "technical-outside-upload-dir"
    outside.mkdir(parents=True, exist_ok=True)
    (outside / name).write_bytes(TECHNICAL_BODY)

    link = upload_root() / SUBDIR
    if link.is_dir():
        # Only ever remove a directory we have just proved is genuinely ours, never a link.
        assert link.resolve().is_relative_to(upload_root())
        shutil.rmtree(link)
    try:
        _link_directory(outside, link)
    except OSError as exc:
        pytest.skip(f"platform cannot link directories: {exc}")

    assert (link / name).read_bytes() == TECHNICAL_BODY
    assert not (link / name).resolve().is_relative_to(upload_root())

    response = audio_app.get(technical_url(name), headers=owner.auth)

    assert response.status_code == 404
    assert response.content != TECHNICAL_BODY


def test_symlink_that_escapes_the_upload_dir_is_denied(audio_app, db_session, owner):
    _, name = technical_recording(db_session, owner.id)
    outside = TEMP_ROOT / "technical-outside-clip.webm"
    outside.write_bytes(TECHNICAL_BODY)
    link = upload_root() / SUBDIR / name
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.symlink(outside, link, target_is_directory=False)
    except OSError as exc:  # Windows without developer mode cannot create file symlinks
        pytest.skip(f"platform cannot create file symlinks: {exc}")

    response = audio_app.get(technical_url(name), headers=owner.auth)

    assert response.status_code == 404
    assert response.content != TECHNICAL_BODY


# ---------------------------------------------------------------------------
# The filename is validated as a raw string, before any path work
# ---------------------------------------------------------------------------

HOSTILE_TECHNICAL_NAMES = [
    "not-a-clip.webm",
    "session_1_q_1_0.webm",
    "session_0_q_1_1.webm",
    "session_1_q_0_1.webm",
    "session_1_q_11_1.webm",
    "session_1_q_12_1.webm",
    "session_1_q_42_1.webm",
    "session_01_q_1_1.webm",
    "session_1_q_01_1.webm",
    "session_1_q_1_01.webm",
    "session_1_q_1_12345678901234.webm",
    "session_1_qq_1_1.webm",
    "session_1_q1_1.webm",
    "session_1_hr_q_1_1.webm",
    "session_1_guesstimate_1.webm",
    "session_1_q_1_1.webm.png",
    "session_1_q_1_1.WEBM",
    "Session_1_q_1_1.webm",
    "session_1_q_1_1x.webm",
    "xsession_1_q_1_1.webm",
    "session_1_q_1_1.webm\x00.png",
    "..session_1_q_1_1.webm",
    "session_1\\..\\q_1_1.webm",
    "session_1_q_1_1 webm",
    "session_1_q_1.webm",
    "session_1_q_webm",
    # ١ is a valid Python decimal digit run but not ASCII: int() would rewrite it.
    "session_١_q_1_1.webm",
]


@pytest.mark.parametrize("name", HOSTILE_TECHNICAL_NAMES)
def test_non_canonical_file_names_never_reach_the_filesystem(audio_app, db_session, owner, name):
    """Grammar first, on the decoded raw string: nothing is normalised, opened or listed.

    The name is percent-encoded so the transport cannot reject it and Starlette hands the handler
    the exact hostile string, NUL and backslash included, as one path segment.
    """
    (upload_root() / SUBDIR).mkdir(parents=True, exist_ok=True)
    (upload_root() / SUBDIR / "other-clip.webm").write_bytes(TECHNICAL_BODY)

    response = audio_app.get(f"/api/technical/audio/{quote(name, safe='')}", headers=owner.auth)

    assert response.status_code == 404, response.text
    assert response.content != TECHNICAL_BODY
    assert response.json() == {"detail": NOT_FOUND_DETAIL}


@pytest.mark.parametrize(
    "raw_path",
    [
        pytest.param("/api/technical/audio/..%2F..%2Fsecret.webm", id="encoded-slash"),
        pytest.param("/api/technical/audio/%2E%2E%2Fsecret.webm", id="encoded-dot-dot"),
        pytest.param("/api/technical/audio/..%5Csecret.webm", id="encoded-backslash"),
        pytest.param("/api/technical/audio/..%2F..%2F..%2Fwindows%5Csecret.webm", id="deep-traversal"),
        pytest.param("/api/technical/audio/%2Fetc%2Fpasswd", id="absolute-posix-path"),
        pytest.param("/api/technical/audio/C%3A%5Csecrets%5Ccandidate.webm", id="absolute-windows-path"),
        pytest.param("/api/technical/audio/", id="empty-filename"),
        pytest.param("/api/technical/audio", id="no-filename-segment"),
    ],
)
def test_traversal_shapes_never_yield_bytes(audio_app, db_session, owner, raw_path):
    """Neither the client-supplied name nor a client-supplied path authorizes anything."""
    upload_root().parent.joinpath("secret.webm").write_bytes(TECHNICAL_BODY)

    response = audio_app.get(raw_path, headers=owner.auth)

    assert response.status_code == 404
    assert response.content != TECHNICAL_BODY


@pytest.mark.parametrize(
    "name,session_id,question_number,user_id",
    [
        pytest.param("session_1_q_1_1.webm", 1, 1, 1, id="simple"),
        pytest.param("session_42_q_10_7.webm", 42, 10, 7, id="question-ten"),
        pytest.param(
            "session_999999999999_q_9_888888888888.webm", 999999999999, 9, 888888888888,
            id="twelve-digits",
        ),
    ],
)
def test_parse_technical_filename_accepts_canonical_names(name, session_id, question_number, user_id):
    clip = service().parse_technical_filename(name)
    assert clip is not None
    assert (clip.session_id, clip.question_number, clip.recording_owner_id) == (
        session_id, question_number, user_id)
    assert clip.filename == name
    assert clip.stored_url == technical_url(name)


@pytest.mark.parametrize("name", HOSTILE_TECHNICAL_NAMES)
def test_parse_technical_filename_refuses_to_guess(name):
    assert service().parse_technical_filename(name) is None


def test_an_accepted_clip_name_can_carry_no_path_separator():
    """Confinement is by construction first: the name handed to the filesystem is rebuilt from
    validated integers, so it cannot contain a separator, a dot-dot or a NUL."""
    for name in ("session_1_q_1_1.webm", "session_999999999999_q_10_1.webm"):
        clip = service().parse_technical_filename(name)
        assert clip is not None
        for forbidden in ("/", "\\", "\x00", "..", os.sep, os.altsep or "\x01"):
            assert forbidden not in clip.filename
        assert clip.stored_url == technical_url(clip.filename)
        assert service().TECHNICAL_SUBDIR == SUBDIR


# ---------------------------------------------------------------------------
# No oracle: every refusal is one response
# ---------------------------------------------------------------------------

def test_every_denial_is_byte_identical(audio_app, db_session, owner, intruder):
    """'Not yours', 'not recorded', 'not there' and 'not a clip' must be indistinguishable."""
    _, theirs = technical_recording(db_session, owner.id)
    write_clip(SUBDIR, theirs, TECHNICAL_BODY)
    _, ghost = technical_recording(db_session, owner.id, q_num=2)  # listed, never written

    foreign = audio_app.get(technical_url(theirs), headers=intruder.auth)
    anonymous = audio_app.get(technical_url(theirs))
    missing_file = audio_app.get(technical_url(ghost), headers=owner.auth)
    bad_name = audio_app.get(technical_url("session_999999_q_1_999999.webm"), headers=owner.auth)

    assert anonymous.status_code == 401  # identity is checked before anything else
    for response in (foreign, missing_file, bad_name):
        assert response.status_code == 404
        assert response.headers["content-type"] == foreign.headers["content-type"]
        assert response.json() == foreign.json() == {"detail": NOT_FOUND_DETAIL}


def test_a_denial_discloses_nothing_about_the_recording(audio_app, db_session, owner, intruder):
    """The body, headers and length of a cross-user denial carry no session, user or path clue."""
    session, name = technical_recording(db_session, owner.id)
    write_clip(SUBDIR, name, TECHNICAL_BODY)

    response = audio_app.get(technical_url(name), headers=intruder.auth)
    text = response.text

    assert response.status_code == 404
    for secret in (str(session.id), str(owner.id), str(owner.email), SUBDIR,
                   str(upload_root()), name):
        assert secret not in text, f"{secret!r} leaked into the denial"
    assert not any(name in value for value in response.headers.values())


# ---------------------------------------------------------------------------
# The other rounds are untouched by this change
# ---------------------------------------------------------------------------

def test_hr_and_guesstimate_clips_still_play_for_their_owner(audio_app, db_session, owner):
    """The regression this task forbids: HR/Guesstimate playback stays exactly as AUTH-E left it."""
    hr_session = create_hr_session(db_session, owner.id, question_count=1)
    hr_name = hr_filename(hr_session.id, 1, owner.id)
    hr_session.hr_detail.questions = [{"audio_url": hr_url(hr_name)}]
    db_session.commit()
    write_clip("hr_audio", hr_name, HR_BODY)

    gs_session = create_guesstimate_session(db_session, owner.id)
    gs_name = guesstimate_filename(gs_session.id, owner.id)
    gs_session.guesstimate_detail.audio_url = guesstimate_url(gs_name)
    db_session.commit()
    write_clip("guesstimate_audio", gs_name, GUESSTIMATE_BODY)

    hr_response = audio_app.get(hr_url(hr_name), headers=owner.auth)
    gs_response = audio_app.get(guesstimate_url(gs_name), headers=owner.auth)

    for response, body in ((hr_response, HR_BODY), (gs_response, GUESSTIMATE_BODY)):
        assert response.status_code == 200, response.text
        assert response.content == body
        assert response.headers["cache-control"] == "private, no-store"


@pytest.mark.parametrize(
    "clip_subdir,clip_name,body,target_prefix",
    [
        pytest.param(SUBDIR, "session_1_q_1_1.webm", TECHNICAL_BODY, "/api/hr/audio/", id="technical-clip-at-hr-route"),
        pytest.param(SUBDIR, "session_1_q_1_1.webm", TECHNICAL_BODY, "/api/guesstimate/audio/", id="technical-clip-at-guesstimate-route"),
        pytest.param("hr_audio", "session_1_hr_q_1_1.webm", HR_BODY, "/api/technical/audio/", id="hr-clip-at-technical-route"),
    ],
)
def test_the_rounds_cannot_read_through_each_others_audio_routes(
    audio_app, db_session, owner, clip_subdir, clip_name, body, target_prefix
):
    """Each grammar belongs to exactly one route, and no route reaches outside its own directory."""
    (upload_root() / clip_subdir).mkdir(parents=True, exist_ok=True)
    (upload_root() / clip_subdir / clip_name).write_bytes(body)

    response = audio_app.get(f"{target_prefix}{clip_name}", headers=owner.auth)

    assert response.status_code == 404
    assert response.content != body
    assert response.json() == {"detail": NOT_FOUND_DETAIL}


# ---------------------------------------------------------------------------
# Static guards on the wiring
# ---------------------------------------------------------------------------

def test_technical_audio_route_binds_identity_and_session_and_uses_the_resolver():
    tree = ast.parse((BACKEND_DIR / "app" / "routes" / "technical.py").read_text(encoding="utf-8"))
    body = next(
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "serve_technical_audio"
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
    assert {"get_current_user", "get_db"} <= resolvers, f"lost a dependency: {sorted(resolvers)}"
    source = ast.get_source_segment(
        (BACKEND_DIR / "app" / "routes" / "technical.py").read_text(encoding="utf-8"), body
    )
    assert "resolve_technical_audio_path" in source
    # The old handler built a path from the client's filename itself.
    assert "Path(filename)" not in source


def test_the_ownership_resolver_is_a_module_level_import():
    """Fail closed: the router cannot load at all if the ownership resolver is missing.

    A lazy import inside the handler would let the route keep working with no authorization when
    the service moved or broke, which is precisely the shape of the original defect.
    """
    source = (BACKEND_DIR / "app" / "routes" / "technical.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = [
        node
        for node in tree.body
        if isinstance(node, ast.ImportFrom)
        and node.module == "app.services.audio_ownership"
    ]
    assert imports, "the ownership resolver must be imported at module level, not inside the handler"
    assert {alias.name for node in imports for alias in node.names} == {
        "audio_file_response",
        "resolve_technical_audio_path",
    }
