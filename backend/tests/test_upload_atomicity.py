"""N3 — upload failure atomicity, written against the five upload handlers.

One root cause: every upload route used to write straight into its final, deterministic path and
commit the row that describes it afterwards. A failure anywhere between the first byte and the
commit left the disk and the database telling different stories — and a retry truncated the previous
complete recording before a single new byte had been written.

Each fault below is armed deterministically (this chunk ordinal, this move, commit broken) rather
than through a timing window, and every test reads the disk back afterwards: the exact bytes at the
destination, the names either side of it, and the row the request was going to write. A status code
alone proves nothing about a filesystem.
"""
from __future__ import annotations

import io
import json
import logging
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session as OrmSession
from conftest import TEMP_ROOT
from session_fixtures import (  # noqa: F401  (session_app/make_account/stubbed_processing/envelope_check are fixtures)
    CALLER_ID,
    FIXTURE_ANSWER,
    VICTIM_ID,
    Endpoint,
    clear_round_clip,
    endpoint,
    envelope_check,
    expected_round_clip,
    make_account,
    make_target,
    read_detail,
    read_session,
    route_source,
    session_app,
    stubbed_processing,
    upload_added,
    upload_snapshot,
)

from app.models.user import User
from app.routes import technical as technical_module
from app.services import upload_store
from app.services.audio_ownership import NOT_FOUND_DETAIL as AUDIO_NOT_FOUND
from app.services.audio_ownership import resolve_guesstimate_audio_path
from app.services.audio_ownership import resolve_hr_audio_path
from config import settings

# Marker bytes for a recording that already existed before the request under test ran. The point of
# the occupied-slot cases is that these exact bytes must still be there afterwards, so they must be
# distinguishable from anything a request could write.
PRIOR_CLIP = b"prior-complete-recording-do-not-truncate"
NEW_CLIP = b"\x1a\x45\xdf\xa3n3-new-recording-body"
RETRY_CLIP = b"\x1a\x45\xdf\xa3n3-retry-succeeded"

PDF_A = b"%PDF-1.4\nN3 fixture resume body A\n%%EOF\n"
PDF_B = b"%PDF-1.4\nN3 fixture resume body B\n%%EOF\n"

UPLOAD_ROUTES = ("sessions.py", "hr.py", "guesstimate.py", "technical.py")
ROUND_ENDPOINTS = ["hr.answer", "guesstimate.submit", "technical.answer"]
EVALUATOR_FOR_ROUND = {
    "hr.answer": "hr.evaluate_hr_answer",
    "guesstimate.submit": "guesstimate.evaluate_guesstimate",
    "technical.answer": "technical.interview_graph.ainvoke",
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def principals(make_account) -> SimpleNamespace:
    return SimpleNamespace(
        victim=make_account(user_id=VICTIM_ID),
        caller=make_account(user_id=CALLER_ID),
    )


@pytest.fixture
def faults(monkeypatch):
    """Deterministic storage and database faults, plus a record of what actually happened.

    The two seams patched here (`_write_chunk`, `_atomic_replace`) exist in `upload_store` for
    exactly this purpose, so an injected fault lands on a real chunk boundary or a real move rather
    than on a wrapper the production path never calls. Chunk sizes are recorded so the bounded-memory
    claim is measured instead of asserted from the source.
    """
    real_write = upload_store._write_chunk
    real_replace = upload_store._atomic_replace
    real_commit = OrmSession.commit

    state: Dict[str, Any] = {
        "fail_chunk": None,
        "chunk_sizes": [],
        "fail_move": None,
        "moves": [],
        "commit_broken": False,
    }

    class _CommitFault(RuntimeError):
        pass

    def _write(fd: int, chunk: bytes) -> int:
        state["chunk_sizes"].append(len(chunk))
        if state["fail_chunk"] == len(state["chunk_sizes"]):
            raise OSError(5, "injected disk write failure")
        return real_write(fd, chunk)

    def _replace(src: Path, dst: Path) -> None:
        state["moves"].append((Path(src).name, Path(dst).name))
        if state["fail_move"] is not None and state["fail_move"](Path(src), Path(dst)):
            raise OSError(22, "injected finalisation failure")
        return real_replace(src, dst)

    def _commit(self, *args, **kwargs):
        if state["commit_broken"]:
            raise _CommitFault("N3 forced commit failure")
        return real_commit(self, *args, **kwargs)

    monkeypatch.setattr(upload_store, "_write_chunk", _write)
    monkeypatch.setattr(upload_store, "_atomic_replace", _replace)
    monkeypatch.setattr(OrmSession, "commit", _commit)

    class Faults:
        Error = _CommitFault

        # -- arming ------------------------------------------------------
        def fail_chunk(self, ordinal: int) -> None:
            state["fail_chunk"] = ordinal

        def fail_publish_move(self) -> None:
            """Only the move that brings the new content in. Displacing the occupant still works,
            so a failed publication must still be able to put the old file back."""
            state["fail_move"] = lambda src, dst: upload_store._TEMP_MARK in src.name

        def break_commit(self) -> None:
            state["commit_broken"] = True

        def heal_commit(self) -> None:
            state["commit_broken"] = False

        def reset(self) -> None:
            state["fail_chunk"] = None
            state["fail_move"] = None
            state["commit_broken"] = False

        # -- evidence ----------------------------------------------------
        @property
        def chunk_sizes(self) -> List[int]:
            return list(state["chunk_sizes"])

        @property
        def moves(self) -> List[tuple]:
            return list(state["moves"])

    return Faults()


@pytest.fixture
def small_chunks(monkeypatch):
    """Force the streaming granularity down so a small body still spans several chunks."""
    monkeypatch.setattr(upload_store, "CHUNK_BYTES", 8)
    return 8


@pytest.fixture
def resume_indexer(monkeypatch):
    """Capture the path the ChromaDB indexing consumer is handed, without running embeddings."""
    calls: List[str] = []

    async def _fake_process(user_id, resume_path):
        calls.append(str(resume_path))

    monkeypatch.setattr(technical_module, "process_resume", _fake_process)
    return calls


# ---------------------------------------------------------------------------
# Disk evidence helpers
# ---------------------------------------------------------------------------
def _inside_envelope(path: Path) -> Path:
    resolved = path.resolve()
    if TEMP_ROOT not in resolved.parents and resolved != TEMP_ROOT:
        raise AssertionError(f"N3 isolation tripwire: {resolved} is outside {TEMP_ROOT}")
    return resolved


def upload_root() -> Path:
    return _inside_envelope(Path(settings.upload_dir))


def resume_root() -> Path:
    return _inside_envelope(Path(settings.resume_upload_dir))


def marker_leftovers(root: Optional[Path] = None) -> List[str]:
    """Any temporary, backup or trash file this module made and failed to reclaim."""
    root = root or upload_root()
    marks = (upload_store._TEMP_MARK, upload_store._BACKUP_MARK, upload_store._TRASH_MARK)
    if not root.exists():
        return []
    return sorted(str(p.relative_to(root)) for p in root.rglob("*")
                  if p.is_file() and any(m in p.name for m in marks))


def read_bytes(path: Path) -> Optional[bytes]:
    return path.read_bytes() if path.is_file() else None


def tree_snapshot(root: Path) -> Dict[str, int]:
    root = _inside_envelope(root)
    if not root.exists():
        return {}
    return {str(p.relative_to(root)): p.stat().st_size for p in root.rglob("*") if p.is_file()}


def added_names(before: Dict[str, int], after: Dict[str, int]) -> List[str]:
    return sorted(name for name in after if name not in before)


def seed_clip(path: Path, body: bytes) -> None:
    _inside_envelope(path.parent)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)


def clear_resume_slot(user_id: int) -> None:
    (resume_root() / f"user_{user_id}.pdf").unlink(missing_ok=True)


def submit_round(client, ep: Endpoint, auth, sid: int, body: Optional[bytes],
                 *, filename: str = "answer.webm"):
    """Issue a round answer exactly as the endpoint registry describes it, with the body asked for."""
    data: Dict[str, Any] = {"session_id": sid, "answer": FIXTURE_ANSWER}
    if ep.name == "guesstimate.submit":
        data["approach_type"] = "top_down"
    files = None if body is None else {"audio_file": (filename, body, "audio/webm")}
    return client.post(ep.path, data=data, files=files, headers=auth)


def create_jam(client, auth, files: Optional[Dict[str, tuple]], *, title: str = "N3 session"):
    return client.post("/api/sessions",
                       data={"title": title, "duration_seconds": "12.5", "round_type": "jam"},
                       files=files, headers=auth)


def persisted_clip_url(ep: Endpoint, db, sid: int) -> Optional[str]:
    """The audio URL the committed row actually advertises, read back from the database."""
    if ep.name == "hr.answer":
        return read_detail(db, sid, "hr")["questions"][-1].get("audio_url")
    if ep.name == "guesstimate.submit":
        return read_detail(db, sid, "guesstimate")["audio_url"]
    if ep.name == "technical.answer":
        return read_detail(db, sid, "technical")["questions"][-1].get("audio_url")
    raise AssertionError(f"{ep.name} does not persist a clip url")


def assert_row_untouched(ep: Endpoint, db, sid: int) -> None:
    """The database is exactly what it was before the request that failed."""
    if ep.name == "guesstimate.submit":
        detail = read_detail(db, sid, "guesstimate")
        assert detail["candidate_answer"] == "", detail
        assert detail["audio_url"] is None, detail
    else:
        round_type = ep.round_type or "jam"
        detail = read_detail(db, sid, round_type)
        assert detail["question_count"] == 1, detail
        assert detail["questions"][-1].get("audio_url") is None, detail


def assert_typed_answer_recorded_without_audio(ep: Endpoint, db, sid: int) -> None:
    """Approved decision 2, checked on the committed row rather than only on the response.

    A round's recording is optional, so a storage failure inside the optional-audio section may not
    roll the answer back: the question advances, the typed text is what was evaluated, and the slot
    in `audio_url` stays empty. Asserting the advance is not a weaker expectation than
    `assert_row_untouched` — it is the *only* expectation the contract allows here, and the file
    assertions in the caller are what prove the displaced recording survived.
    """
    if ep.name == "guesstimate.submit":
        detail = read_detail(db, sid, "guesstimate")
        assert detail["candidate_answer"] == FIXTURE_ANSWER.strip(), detail
        assert detail["audio_url"] is None, detail
    else:
        round_type = ep.round_type or "jam"
        detail = read_detail(db, sid, round_type)
        assert detail["question_count"] == 2, detail
        last = detail["questions"][-1]
        assert last.get("answer") == FIXTURE_ANSWER.strip(), last
        assert last.get("audio_url") is None, last


def round_slot(ep: Endpoint, sid: int, uid: int) -> Path:
    return expected_round_clip(ep.name, sid, uid)


# ---------------------------------------------------------------------------
# 1 — Successful upload: the happy path still writes exactly what it used to
# ---------------------------------------------------------------------------
def test_successful_jam_upload_stores_exact_bytes_and_plays_them_back(session_app, db_session,
                                                                      principals):
    before = upload_snapshot()
    response = create_jam(session_app, principals.caller.auth,
                          {"audio": ("clip.webm", NEW_CLIP, "audio/webm")})
    assert response.status_code == 201, response.text
    sid = response.json()["id"]

    stored = read_session(db_session, sid)
    path = Path(stored["audio_path"])
    assert path.is_file(), f"the row names a file that is not there: {path}"
    assert read_bytes(path) == NEW_CLIP, "the destination does not hold the bytes that were sent"
    assert upload_added(before) == [str(path.relative_to(upload_root()))]
    assert marker_leftovers() == [], f"helper files were left behind: {marker_leftovers()}"

    playback = session_app.get(f"/api/sessions/{sid}/audio", headers=principals.caller.auth)
    assert playback.status_code == 200, playback.text
    assert playback.content == NEW_CLIP


@pytest.mark.parametrize("ep_name", ROUND_ENDPOINTS, ids=ROUND_ENDPOINTS)
def test_successful_round_upload_publishes_into_the_canonical_slot(session_app, db_session,
                                                                   principals, ep_name):
    ep = endpoint(ep_name)
    target = make_target(db_session, principals.caller.id, ep)
    slot = round_slot(ep, target.id, principals.caller.id)
    clear_round_clip(slot)
    before = upload_snapshot()

    response = submit_round(session_app, ep, principals.caller.auth, target.id, NEW_CLIP)
    assert response.status_code == 200, response.text

    assert read_bytes(slot) == NEW_CLIP
    assert upload_added(before) == [str(slot.relative_to(upload_root()))], (
        "a round upload must create its own slot and nothing else")
    assert marker_leftovers() == []
    # the response and the stored row advertise the canonical authenticated route, byte for byte
    expected = f"/api/{'hr' if ep.name == 'hr.answer' else ('guesstimate' if ep.name == 'guesstimate.submit' else 'technical')}/audio/{slot.name}"
    assert response.json()["audio_url"] == expected, response.json()["audio_url"]
    assert persisted_clip_url(ep, db_session, target.id) == expected


# ---------------------------------------------------------------------------
# 1b — Binary fidelity: what is sent is what is stored, byte for byte
# ---------------------------------------------------------------------------
#: Every byte value the transport can carry, including `0x0A` and the `0x0D 0x0A` pair.
ALL_BYTES = bytes(range(256)) * 5


def test_helper_stores_every_byte_value_unmodified():
    """A recording is arbitrary bytes, and the CRT will rewrite them if the descriptor is text.

    `os.open` without `O_BINARY` on Windows inherits the runtime's translation mode, and `os.write`
    then turns each lone `0x0A` into `0x0D 0x0A` (and `0x0D 0x0A` into `0x0D 0x0D 0x0A`). That is not
    a cosmetic difference: it silently corrupts the uploaded WebM and changes its length, while every
    test whose fixture happens to contain no newline byte still passes.
    """
    root = upload_root() / "n3_binary"
    root.mkdir(parents=True, exist_ok=True)
    tx = upload_store.transaction()
    staged = tx.stage(root, "allbytes.webm")
    written = staged.write_from(io.BytesIO(ALL_BYTES), chunk_bytes=7)
    staged.publish()
    tx.finalize()

    stored = (root / "allbytes.webm").read_bytes()
    assert written == len(ALL_BYTES)
    assert stored == ALL_BYTES, (
        f"the write path translated bytes: first divergence at "
        f"{next(i for i, (a, b) in enumerate(zip(stored, ALL_BYTES)) if a != b)}")
    assert (root / "allbytes.webm").stat().st_size == len(ALL_BYTES)
    (root / "allbytes.webm").unlink(missing_ok=True)
    root.rmdir()


@pytest.mark.parametrize("ep_name", ROUND_ENDPOINTS, ids=ROUND_ENDPOINTS)
def test_a_recording_full_of_newline_bytes_survives_the_route(session_app, db_session, principals,
                                                              ep_name):
    """The same property through a real upload route, not only through the helper."""
    ep = endpoint(ep_name)
    target = make_target(db_session, principals.caller.id, ep)
    slot = round_slot(ep, target.id, principals.caller.id)
    clear_round_clip(slot)

    response = submit_round(session_app, ep, principals.caller.auth, target.id, ALL_BYTES)
    assert response.status_code == 200, response.text
    audio_url = response.json()["audio_url"]
    assert audio_url is not None, "the route degraded a recording that succeeded"
    assert read_bytes(slot) == ALL_BYTES, (
        "the stored recording is not the bytes the candidate sent")

    # What the authorisation layer resolves for playback must be the same bytes, not a translated
    # copy. The harness replaces the HR/Guesstimate *serving* call (AUTH-E is out of scope) so the
    # resolver itself is exercised; technical's serving is reachable over HTTP.
    if ep.name == "hr.answer":
        db_session.expire_all()
        served = read_bytes(resolve_hr_audio_path(db_session, db_session.get(User, principals.caller.id), slot.name))
    elif ep.name == "guesstimate.submit":
        db_session.expire_all()
        served = read_bytes(resolve_guesstimate_audio_path(
            db_session, db_session.get(User, principals.caller.id), slot.name))
    else:
        playback = session_app.get(audio_url, headers=principals.caller.auth)
        assert playback.status_code == 200, playback.text
        served = playback.content
    assert served == ALL_BYTES, "playback served translated bytes"
    clear_round_clip(slot)


# ---------------------------------------------------------------------------
# 2 — Failure during the first chunk
# ---------------------------------------------------------------------------
def test_first_chunk_failure_on_jam_propagates_and_leaves_no_file(session_app, db_session,
                                                                  principals, faults):
    before = upload_snapshot()
    faults.fail_chunk(1)
    with pytest.raises(OSError):
        create_jam(session_app, principals.caller.auth,
                   {"audio": ("clip.webm", NEW_CLIP, "audio/webm")})
    assert upload_added(before) == [], f"partial file survived: {upload_added(before)}"
    assert marker_leftovers() == []


@pytest.mark.parametrize("ep_name", ROUND_ENDPOINTS, ids=ROUND_ENDPOINTS)
def test_first_chunk_failure_keeps_the_previous_complete_recording(session_app, db_session,
                                                                   principals, faults, ep_name):
    """The defect N3 exists for: a retry used to truncate the slot before writing any new byte."""
    ep = endpoint(ep_name)
    target = make_target(db_session, principals.caller.id, ep)
    slot = round_slot(ep, target.id, principals.caller.id)
    seed_clip(slot, PRIOR_CLIP)

    faults.fail_chunk(1)
    response = submit_round(session_app, ep, principals.caller.auth, target.id, NEW_CLIP)

    assert response.status_code == 200, response.text
    assert read_bytes(slot) == PRIOR_CLIP, "the failed write destroyed the earlier recording"
    assert response.json()["audio_url"] is None
    assert persisted_clip_url(ep, db_session, target.id) is None
    assert marker_leftovers() == []


# ---------------------------------------------------------------------------
# 3 — Failure during a later chunk (a partial body is already on disk)
# ---------------------------------------------------------------------------
def test_later_chunk_failure_on_jam_removes_the_partial_file(session_app, db_session, principals,
                                                             faults, small_chunks):
    before = upload_snapshot()
    faults.fail_chunk(2)
    with pytest.raises(OSError):
        create_jam(session_app, principals.caller.auth,
                   {"audio": ("clip.webm", bytes(range(20)), "audio/webm")})
    assert upload_added(before) == []
    assert marker_leftovers() == []
    assert faults.chunk_sizes == [small_chunks, small_chunks], (
        f"the body was not streamed one chunk at a time: {faults.chunk_sizes}")


@pytest.mark.parametrize("ep_name", ROUND_ENDPOINTS, ids=ROUND_ENDPOINTS)
def test_later_chunk_failure_never_publishes_a_partial_recording(session_app, db_session,
                                                                 principals, faults, small_chunks,
                                                                 ep_name):
    ep = endpoint(ep_name)
    target = make_target(db_session, principals.caller.id, ep)
    slot = round_slot(ep, target.id, principals.caller.id)
    seed_clip(slot, PRIOR_CLIP)

    faults.fail_chunk(3)
    response = submit_round(session_app, ep, principals.caller.auth, target.id, bytes(range(24)))

    assert response.status_code == 200, response.text
    assert read_bytes(slot) == PRIOR_CLIP
    assert bytes(range(8)) not in read_bytes(slot), "partial new content reached the destination"
    assert response.json()["audio_url"] is None
    assert marker_leftovers() == []


# ---------------------------------------------------------------------------
# 4 — Finalisation / rename failure
# ---------------------------------------------------------------------------
def test_publish_move_failure_on_jam_leaves_no_file_and_no_row(session_app, db_session,
                                                               principals, faults):
    before = upload_snapshot()
    rows_before = session_app.get("/api/sessions", headers=principals.caller.auth).json()
    faults.fail_publish_move()
    with pytest.raises(OSError):
        create_jam(session_app, principals.caller.auth,
                   {"audio": ("clip.webm", NEW_CLIP, "audio/webm")})

    assert upload_added(before) == []
    assert marker_leftovers() == []
    assert session_app.get("/api/sessions", headers=principals.caller.auth).json() == rows_before


@pytest.mark.parametrize("ep_name", ROUND_ENDPOINTS, ids=ROUND_ENDPOINTS)
def test_publish_move_failure_restores_the_displaced_recording(session_app, db_session,
                                                               principals, faults, ep_name):
    """Publication is the only step that can lose an existing file: the occupant moves aside first,
    so the restore has to run when the incoming move is the one that fails."""
    ep = endpoint(ep_name)
    target = make_target(db_session, principals.caller.id, ep)
    slot = round_slot(ep, target.id, principals.caller.id)
    seed_clip(slot, PRIOR_CLIP)
    size_before = slot.stat().st_size
    before = upload_snapshot()

    faults.fail_publish_move()
    response = submit_round(session_app, ep, principals.caller.auth, target.id, NEW_CLIP)

    assert response.status_code == 200, response.text
    assert read_bytes(slot) == PRIOR_CLIP, "the displaced recording was not put back byte for byte"
    assert slot.stat().st_size == size_before, "the restored recording is a different file"
    assert response.json()["audio_url"] is None
    assert upload_added(before) == [], (
        f"the displaced occupant or its backup survived: {upload_added(before)}")
    assert marker_leftovers() == []
    # The recording failed; the typed answer may not. See the helper's docstring for why this is the
    # contract and not a relaxed version of the row-untouched assertion used for a failed commit.
    assert_typed_answer_recorded_without_audio(ep, db_session, target.id)


# ---------------------------------------------------------------------------
# 5 — Database commit failure after publication
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("ep_name", ROUND_ENDPOINTS, ids=ROUND_ENDPOINTS)
def test_commit_failure_after_publication_removes_the_published_clip(session_app, db_session,
                                                                     principals, faults, ep_name):
    ep = endpoint(ep_name)
    target = make_target(db_session, principals.caller.id, ep)
    slot = round_slot(ep, target.id, principals.caller.id)
    clear_round_clip(slot)
    before = upload_snapshot()

    faults.break_commit()
    with pytest.raises(faults.Error):
        submit_round(session_app, ep, principals.caller.auth, target.id, NEW_CLIP)

    assert not slot.exists(), "a clip that no row describes is clutter reachable by name"
    assert upload_added(before) == []
    assert marker_leftovers() == []
    assert_row_untouched(ep, db_session, target.id)


# ---------------------------------------------------------------------------
# 6 — Successful replacement of an occupied destination
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("ep_name", ROUND_ENDPOINTS, ids=ROUND_ENDPOINTS)
def test_successful_replacement_keeps_only_the_new_recording(session_app, db_session, principals,
                                                             ep_name):
    ep = endpoint(ep_name)
    target = make_target(db_session, principals.caller.id, ep)
    slot = round_slot(ep, target.id, principals.caller.id)
    seed_clip(slot, PRIOR_CLIP)
    before = upload_snapshot()

    response = submit_round(session_app, ep, principals.caller.auth, target.id, NEW_CLIP)
    assert response.status_code == 200, response.text

    assert read_bytes(slot) == NEW_CLIP, "a successful upload must land in the slot"
    assert upload_added(before) == [], "the preserved copy must not survive the commit"
    assert marker_leftovers() == [], f"backup left behind: {marker_leftovers()}"
    assert persisted_clip_url(ep, db_session, target.id) == response.json()["audio_url"]


# ---------------------------------------------------------------------------
# 7 — Failed replacement restores the exact previous bytes
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("ep_name", ROUND_ENDPOINTS, ids=ROUND_ENDPOINTS)
def test_failed_replacement_restores_exact_previous_bytes(session_app, db_session, principals,
                                                          faults, ep_name):
    ep = endpoint(ep_name)
    target = make_target(db_session, principals.caller.id, ep)
    slot = round_slot(ep, target.id, principals.caller.id)
    seed_clip(slot, PRIOR_CLIP)
    size_before = slot.stat().st_size
    before = upload_snapshot()

    faults.break_commit()
    with pytest.raises(faults.Error):
        submit_round(session_app, ep, principals.caller.auth, target.id, NEW_CLIP)

    assert read_bytes(slot) == PRIOR_CLIP, "restoration did not return the original bytes"
    assert slot.stat().st_size == size_before
    assert upload_added(before) == []
    assert marker_leftovers() == []


def test_failed_replacement_of_a_resume_restores_the_previous_pdf(session_app, db_session,
                                                                  principals, faults,
                                                                  resume_indexer):
    caller = principals.caller
    slot = resume_root() / f"user_{caller.id}.pdf"
    slot.parent.mkdir(parents=True, exist_ok=True)
    slot.write_bytes(PDF_A)

    user = db_session.get(User, caller.id)
    user.resume_path = str(slot)
    user.resume_name = "previous-candidate.pdf"
    db_session.commit()

    faults.break_commit()
    with pytest.raises(faults.Error):
        session_app.post("/api/technical/resume/upload",
                         files={"file": ("new-candidate.pdf", PDF_B, "application/pdf")},
                         headers=caller.auth)

    assert read_bytes(slot) == PDF_A, "a failed upload destroyed the stored resume"
    db_session.expire_all()
    refreshed = db_session.get(User, caller.id)
    assert refreshed.resume_name == "previous-candidate.pdf"
    assert Path(refreshed.resume_path) == slot
    assert resume_indexer == [], "indexing ran for a resume the database refused"
    assert marker_leftovers(resume_root()) == []


# ---------------------------------------------------------------------------
# 8 — Concurrent requests against the same deterministic slot
# ---------------------------------------------------------------------------
def test_same_slot_publication_is_serialised_and_never_mixes_bodies():
    """Two requests for one slot, staged to completion and released to publish at the same instant.

    Two different claims, and the evidence for each is different. (a) The overlap detector can only
    fire if two preserve-then-replace sections genuinely interleaved, so a clean run is direct
    evidence about this run; it cannot prove the absence of a race in general, which is why
    `test_slot_locks_are_per_destination_not_global` pins the mechanism itself. (b) The outcome — one
    complete body in the slot, the rolled-back request leaving the committed request's file in place —
    is order-independent, and `test_the_committed_request_owns_the_slot_after_both_requests_settle`
    proves that for both publication orders without any threads at all.
    """
    root = upload_root() / "n3_concurrent"
    root.mkdir(parents=True, exist_ok=True)
    name = "session_900001_hr_q_1_900001.webm"
    slot = root / name
    body_a, body_b = b"first-request-complete-body", b"second-request-complete-body"

    real_replace = upload_store._atomic_replace
    guard = threading.Lock()
    inside: Dict[str, str] = {}
    overlaps: List[tuple] = []

    def _probing_replace(src: Path, dst: Path) -> None:
        key = Path(dst).name
        me = threading.current_thread().name
        with guard:
            other = inside.get(key)
            if other is not None and other != me:
                overlaps.append((key, other, me))
            inside[key] = me
        try:
            real_replace(src, dst)
        finally:
            with guard:
                inside.pop(key, None)

    upload_store._atomic_replace = _probing_replace
    try:
        barrier = threading.Barrier(2)
        outcomes: Dict[str, Any] = {}

        def _run(label: str, body: bytes) -> None:
            tx = upload_store.transaction()
            try:
                staged = tx.stage(root, name)
                staged.write_from(io.BytesIO(body))
                barrier.wait(timeout=30)
                staged.publish()
                outcomes[label] = tx
            except BaseException as exc:  # keep the transaction so the main thread can unwind it
                outcomes.setdefault(label, exc)

        threads = [threading.Thread(target=_run, args=("a", body_a), name="a"),
                   threading.Thread(target=_run, args=("b", body_b), name="b")]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        tx_a, tx_b = outcomes["a"], outcomes["b"]
        assert isinstance(tx_a, upload_store.UploadTransaction), tx_a
        assert isinstance(tx_b, upload_store.UploadTransaction), tx_b

        # "a" commits and "b" fails and unwinds — in that order, decided by the test, not by timing.
        tx_a.finalize()
        tx_b.rollback()
    finally:
        upload_store._atomic_replace = real_replace

    assert overlaps == [], f"two publications into one slot interleaved: {overlaps}"
    assert read_bytes(slot) == body_a, "the surviving file is not the committed request's body"
    assert sorted(p.name for p in root.iterdir()) == [name], "helper files outlived the requests"
    slot.unlink(missing_ok=True)
    root.rmdir()


def test_slot_locks_are_per_destination_not_global():
    """Different slots must not wait on each other: the lock is keyed on the destination itself.

    No claim is made here about case folding. `destination_lock_for` normalises with
    `os.path.normcase`, which is the right thing on both platforms, but whether two names that
    differ only in case are one slot or two is a property of the filesystem under test, so this
    test does not assert it.
    """
    root = upload_root()
    one = root / "hr_audio" / "session_1_hr_q_1_1.webm"
    two = root / "hr_audio" / "session_2_hr_q_1_1.webm"
    assert upload_store.destination_lock_for(one) is upload_store.destination_lock_for(one)
    assert upload_store.destination_lock_for(one) is not upload_store.destination_lock_for(two)


def _publish_two(root: Path, name: str, body_first: bytes, body_second: bytes):
    """Two staged uploads published to one slot, in the order asked for (no threads, no timing)."""
    first = upload_store.transaction()
    staged_first = first.stage(root, name)
    staged_first.write_from(io.BytesIO(body_first))
    staged_first.publish()

    second = upload_store.transaction()
    staged_second = second.stage(root, name)
    staged_second.write_from(io.BytesIO(body_second))
    staged_second.publish()
    return first, second


@pytest.mark.parametrize("winner_publishes_first", [True, False], ids=["winner-first", "winner-last"])
def test_the_committed_request_owns_the_slot_after_both_requests_settle(
        winner_publishes_first):
    """The handover a per-destination lock cannot cover, and the property cleanup has to provide.

    Publication is serialised, but the window between one request publishing and the other committing
    is not: both requests write to the same deterministic clip name. Whichever order the two
    publications happen in, the request that commits must be the one whose bytes are in the slot when
    both have unwound — the failed request may not delete the winner's file, and may not restore an
    older copy over it.
    """
    root = upload_root() / "n3_handover"
    root.mkdir(parents=True, exist_ok=True)
    name = "session_900002_hr_q_1_900002.webm"
    body_a, body_b = b"committed-request-body", b"failed-request-body"

    if winner_publishes_first:
        winner, loser = _publish_two(root, name, body_a, body_b)
    else:
        loser, winner = _publish_two(root, name, body_b, body_a)

    winner.finalize()
    loser.rollback()

    slot = root / name
    assert read_bytes(slot) == body_a, (
        "the committed request's recording did not survive the failed request's cleanup")
    assert marker_leftovers(root) == [], f"helper files outlived both requests: {marker_leftovers(root)}"
    assert [p.name for p in root.iterdir()] == [name]

    slot.unlink(missing_ok=True)
    root.rmdir()


def test_a_rolled_back_upload_restores_what_it_displaced_when_it_still_owns_the_slot():
    """The guard must not disable the restore it exists beside: owning the slot means putting the
    previous recording back, byte for byte."""
    root = upload_root() / "n3_restore"
    root.mkdir(parents=True, exist_ok=True)
    name = "session_900003_hr_q_1_900003.webm"
    slot = root / name
    slot.write_bytes(b"the-earlier-recording")

    tx = upload_store.transaction()
    staged = tx.stage(root, name)
    staged.write_from(io.BytesIO(b"this-request-fails"))
    staged.publish()
    assert read_bytes(slot) == b"this-request-fails"
    assert staged.superseded() is False, "this request still holds the slot it published"

    tx.rollback()
    assert read_bytes(slot) == b"the-earlier-recording", "the displaced recording was not restored"
    assert marker_leftovers(root) == []
    slot.unlink(missing_ok=True)
    root.rmdir()


# ---------------------------------------------------------------------------
# 9 — U1 multi-file rollback: first file published, second fails
# ---------------------------------------------------------------------------
def test_jam_second_file_failure_removes_the_first_files_publication(session_app, db_session,
                                                                     principals, faults):
    before = upload_snapshot()
    # One chunk per file at the default granularity: failing call #2 fails the second file, after
    # the first has already been written, closed and published.
    faults.fail_chunk(2)
    with pytest.raises(OSError):
        create_jam(session_app, principals.caller.auth,
                   {"video": ("clip.mp4", NEW_CLIP, "video/mp4"),
                    "audio": ("clip.webm", RETRY_CLIP, "audio/webm")})

    assert faults.chunk_sizes == [len(NEW_CLIP), len(RETRY_CLIP)], faults.chunk_sizes
    assert upload_added(before) == [], "the published first file survived a failed request"
    assert marker_leftovers() == []


def test_jam_extension_rejection_happens_before_any_file_is_made(session_app, db_session,
                                                                  principals):
    before = upload_snapshot()
    response = create_jam(session_app, principals.caller.auth,
                          {"audio": ("clip.exe", NEW_CLIP, "audio/webm")})
    assert response.status_code == 400, response.text
    assert response.json()["detail"] == "Unsupported file extension: .exe"
    assert upload_added(before) == []
    assert marker_leftovers() == []


# ---------------------------------------------------------------------------
# 10 — U1 both files published, then the commit fails
# ---------------------------------------------------------------------------
def test_jam_files_published_then_commit_fails_leaves_neither(session_app, db_session,
                                                              principals, faults):
    before = upload_snapshot()
    video_before = tree_snapshot(upload_root() / "video")
    audio_before = tree_snapshot(upload_root() / "audio")
    faults.break_commit()
    with pytest.raises(faults.Error):
        create_jam(session_app, principals.caller.auth,
                   {"video": ("clip.mp4", NEW_CLIP, "video/mp4"),
                    "audio": ("clip.webm", RETRY_CLIP, "audio/webm")})

    assert upload_added(before) == []
    assert marker_leftovers() == []
    # Neither destination directory changed at all. Comparing the directories against themselves
    # rather than against "empty" is deliberate: other tests legitimately leave recordings here, and
    # an assertion of global emptiness would be a property of the run order, not of this request.
    assert tree_snapshot(upload_root() / "video") == video_before
    assert tree_snapshot(upload_root() / "audio") == audio_before


# ---------------------------------------------------------------------------
# 11 — Cleanup failure while another cleanup succeeds
# ---------------------------------------------------------------------------
def test_failing_cleanup_is_logged_and_does_not_stop_the_other_one():
    """A temp path replaced by a directory cannot be unlinked on either platform, so this removal
    really does fail — and the contract is that it neither halts the rollback nor hides itself."""
    root = upload_root() / "n3_cleanup"
    root.mkdir(parents=True, exist_ok=True)
    tx = upload_store.transaction()
    stuck = tx.stage(root, "stuck.webm")
    other = tx.stage(root, "other.webm")
    stuck.write_from(io.BytesIO(b"stuck-body"))
    other.write_from(io.BytesIO(b"other-body"))
    stuck.close()
    other.close()

    # Only this test's own two paths are touched, and one of them is made undeletable on purpose.
    stuck.temp_path.unlink()
    stuck.temp_path.mkdir()

    logger = logging.getLogger("speakflow.upload_store")
    records: List[logging.LogRecord] = []

    class Collector(logging.Handler):
        def emit(self, record):
            records.append(record)

    handler = Collector(level=logging.ERROR)
    logger.addHandler(handler)
    logger.setLevel(logging.ERROR)
    try:
        tx.rollback()
    finally:
        logger.removeHandler(handler)

    assert not other.temp_path.exists(), "one failing cleanup blocked the other"
    assert not (root / "other.webm").exists()
    assert stuck.temp_path.is_dir(), "the fixture broke, not the code"
    failures = [r.getMessage() for r in records if "upload cleanup" in r.getMessage()]
    assert failures, "a cleanup failure was not logged at all"
    assert any("abort temp" in message for message in failures), failures

    stuck.temp_path.rmdir()
    root.rmdir()


# ---------------------------------------------------------------------------
# 12 — Retry after a failed upload
# ---------------------------------------------------------------------------
def test_retry_after_a_failed_upload_succeeds_into_its_own_file(session_app, db_session,
                                                                principals, faults):
    before = upload_snapshot()
    faults.break_commit()
    with pytest.raises(faults.Error):
        create_jam(session_app, principals.caller.auth,
                   {"audio": ("clip.webm", NEW_CLIP, "audio/webm")})
    assert upload_added(before) == []

    faults.heal_commit()
    response = create_jam(session_app, principals.caller.auth,
                          {"audio": ("clip.webm", RETRY_CLIP, "audio/webm")})
    assert response.status_code == 201, response.text

    sid = response.json()["id"]
    path = Path(read_session(db_session, sid)["audio_path"])
    assert read_bytes(path) == RETRY_CLIP
    assert upload_added(before) == [str(path.relative_to(upload_root()))]
    assert marker_leftovers() == []
    assert str(path.relative_to(upload_root())) not in before, (
        "the retry wrote over a file the failed attempt had left behind")

    playback = session_app.get(f"/api/sessions/{sid}/audio", headers=principals.caller.auth)
    assert playback.status_code == 200
    assert playback.content == RETRY_CLIP


def test_round_retry_after_a_failed_request_writes_the_new_clip(session_app, db_session,
                                                                principals, faults):
    """A round retries into *its own* slot only when the whole request failed.

    The distinction matters and is the point of this test: an audio-only failure degrades and
    advances the question (§4), so the next submit belongs to the next question and no retry can
    land in the earlier slot. A commit failure leaves the question where it was, so the same
    deterministic slot is exactly what the candidate's next recording must fill — and must fill with
    its own bytes, not with a leftover partial file from the failed attempt.
    """
    ep = endpoint("hr.answer")
    target = make_target(db_session, principals.caller.id, ep)
    slot = round_slot(ep, target.id, principals.caller.id)
    clear_round_clip(slot)

    faults.fail_chunk(1)
    faults.break_commit()
    with pytest.raises(faults.Error):
        submit_round(session_app, ep, principals.caller.auth, target.id, NEW_CLIP)
    assert not slot.exists(), "the discarded recording still occupies the slot"
    assert_row_untouched(ep, db_session, target.id)

    faults.reset()
    faults.heal_commit()
    second = submit_round(session_app, ep, principals.caller.auth, target.id, RETRY_CLIP)
    assert second.status_code == 200, second.text
    assert read_bytes(slot) == RETRY_CLIP, (
        "the retry did not own its slot: bytes from the failed attempt survived")
    assert second.json()["audio_url"] == f"/api/hr/audio/{slot.name}"
    assert marker_leftovers() == []


# ---------------------------------------------------------------------------
# 13 — Resume filename safety and confinement
# ---------------------------------------------------------------------------
HOSTILE_NAMES = [
    "../../outside-resumes.pdf",
    "..\\..\\outside-resumes.pdf",
    "....//....//outside.pdf",
    "C:\\Windows\\Temp\\evil.pdf",
    "/etc/passwd.pdf",
    "session_1_hr_q_2_3.webm.pdf",
    "a/../../b.pdf",
    "..%2f..%2fescape.pdf",
    "null\x00name.pdf",
    "unicode-café-résumé.pdf",
]


@pytest.mark.parametrize("client_name", HOSTILE_NAMES,
                         ids=[i for i in range(len(HOSTILE_NAMES))])
def test_hostile_resume_names_cannot_reach_the_filesystem(session_app, db_session, principals,
                                                           resume_indexer, client_name):
    caller = principals.caller
    before = tree_snapshot(TEMP_ROOT)
    slot = resume_root() / f"user_{caller.id}.pdf"

    response = session_app.post("/api/technical/resume/upload",
                                files={"file": (client_name, PDF_A, "application/pdf")},
                                headers=caller.auth)

    if response.status_code != 200:
        # A refusal is allowed; what is not allowed is a hostile name becoming a path.
        assert added_names(before, tree_snapshot(TEMP_ROOT)) == []
        return

    assert read_bytes(slot) == PDF_A, f"the resume is not at the confined slot: {slot}"
    for name in added_names(before, tree_snapshot(TEMP_ROOT)):
        assert name == str(slot.relative_to(TEMP_ROOT)), (
            f"a hostile resume name wrote something outside the one confined slot: {name}")

    db_session.expire_all()
    user = db_session.get(User, caller.id)
    assert Path(user.resume_path).name == f"user_{caller.id}.pdf"
    # the display metadata is exactly what the route echoed, and no client name became a path
    assert user.resume_name == response.json()["resume_name"]
    assert client_name not in user.resume_path.replace(f"user_{caller.id}.pdf", "")
    assert str(upload_root()) not in json.dumps(response.json())
    assert marker_leftovers() == []


def test_non_pdf_resume_is_refused_before_anything_is_written(session_app, db_session,
                                                               principals, resume_indexer):
    before = tree_snapshot(TEMP_ROOT)
    response = session_app.post("/api/technical/resume/upload",
                                files={"file": ("resume.exe", PDF_A, "application/pdf")},
                                headers=principals.caller.auth)
    assert response.status_code == 400, response.text
    assert response.json()["detail"] == "Only PDF resume files are supported."
    assert added_names(before, tree_snapshot(TEMP_ROOT)) == []
    assert resume_indexer == []


# ---------------------------------------------------------------------------
# 14 — Resume retrieval and indexing consumers with the safe slot name
# ---------------------------------------------------------------------------
def test_resume_status_and_indexing_use_the_confined_path(session_app, db_session, principals,
                                                          resume_indexer):
    caller = principals.caller
    clear_resume_slot(caller.id)
    slot = resume_root() / f"user_{caller.id}.pdf"

    response = session_app.post("/api/technical/resume/upload",
                                files={"file": ("My Cv 2026.pdf", PDF_A, "application/pdf")},
                                headers=caller.auth)
    assert response.status_code == 200, response.text
    assert response.json()["resume_name"] == "My Cv 2026.pdf"

    # the ChromaDB consumer was handed the confined path, and that path is a real, complete file
    assert resume_indexer == [str(slot)]
    assert read_bytes(slot) == PDF_A

    status = session_app.get("/api/technical/resume/status", headers=caller.auth)
    assert status.status_code == 200, status.text
    assert status.json() == {"has_resume": True, "resume_name": "My Cv 2026.pdf"}
    assert str(upload_root()) not in status.text

    # a second upload replaces the one slot; the client's filename never becomes a path
    response2 = session_app.post("/api/technical/resume/upload",
                                 files={"file": ("My Cv 2027.pdf", PDF_B, "application/pdf")},
                                 headers=caller.auth)
    assert response2.status_code == 200, response2.text
    assert read_bytes(slot) == PDF_B
    assert session_app.get("/api/technical/resume/status",
                           headers=caller.auth).json()["resume_name"] == "My Cv 2027.pdf"
    names = sorted(p.name for p in resume_root().iterdir())
    assert f"user_{caller.id}.pdf" in names
    assert not any("Cv 202" in name for name in names), names
    assert marker_leftovers(resume_root()) == []


def test_legacy_resume_display_fallback_still_strips_the_old_prefix(session_app, db_session,
                                                                    principals):
    """`get_resume_status` falls back to the stored basename when `resume_name` is null, and it
    strips the old `user_<id>_` prefix; a legacy row must still display the candidate's name."""
    caller = principals.caller
    legacy = resume_root() / f"user_{caller.id}_legacy-cv.pdf"
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_bytes(PDF_A)

    db_session.expire_all()
    user = db_session.get(User, caller.id)
    user.resume_path = str(legacy)
    user.resume_name = None
    db_session.commit()

    status = session_app.get("/api/technical/resume/status", headers=caller.auth)
    assert status.status_code == 200, status.text
    assert status.json() == {"has_resume": True, "resume_name": "legacy-cv.pdf"}
    legacy.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# 15 — Owner retrieval and non-owner denial of what an upload stored
# ---------------------------------------------------------------------------
def test_jam_owner_plays_the_recording_and_a_non_owner_is_refused(session_app, db_session,
                                                                  principals):
    response = create_jam(session_app, principals.caller.auth,
                          {"audio": ("clip.webm", NEW_CLIP, "audio/webm")})
    sid = response.json()["id"]

    mine = session_app.get(f"/api/sessions/{sid}/audio", headers=principals.caller.auth)
    assert mine.status_code == 200, mine.text
    assert mine.content == NEW_CLIP

    theirs = session_app.get(f"/api/sessions/{sid}/audio", headers=principals.victim.auth)
    assert theirs.status_code == 404, theirs.text
    anonymous = session_app.get(f"/api/sessions/{sid}/audio")
    assert anonymous.status_code == 401, anonymous.text


def test_hr_clip_is_authorised_for_its_owner_and_denied_to_another(session_app, db_session,
                                                                   principals):
    ep = endpoint("hr.answer")
    target = make_target(db_session, principals.caller.id, ep)
    slot = round_slot(ep, target.id, principals.caller.id)
    clear_round_clip(slot)

    response = submit_round(session_app, ep, principals.caller.auth, target.id, NEW_CLIP)
    assert response.status_code == 200, response.text
    filename = slot.name
    assert response.json()["audio_url"] == f"/api/hr/audio/{filename}"

    db_session.expire_all()
    owner = db_session.get(User, principals.caller.id)
    resolved = resolve_hr_audio_path(db_session, owner, filename)
    assert read_bytes(resolved) == NEW_CLIP, "the authorised path is not the recording that was sent"

    db_session.expire_all()
    victim = db_session.get(User, principals.victim.id)
    with pytest.raises(HTTPException) as denial:
        resolve_hr_audio_path(db_session, victim, filename)
    assert denial.value.status_code == 404
    assert denial.value.detail == AUDIO_NOT_FOUND


# ---------------------------------------------------------------------------
# 16 — No partial recording reaches ASR or is advertised through audio_url
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("ep_name", ROUND_ENDPOINTS, ids=ROUND_ENDPOINTS)
def test_partial_recording_reaches_neither_asr_nor_audio_url(session_app, db_session, principals,
                                                             faults, small_chunks,
                                                             stubbed_processing, ep_name):
    ep = endpoint(ep_name)
    label = ep.name.split(".")[0]
    target = make_target(db_session, principals.caller.id, ep)
    slot = round_slot(ep, target.id, principals.caller.id)
    seed_clip(slot, PRIOR_CLIP)

    faults.fail_chunk(2)
    response = submit_round(session_app, ep, principals.caller.auth, target.id, bytes(range(24)))

    assert response.status_code == 200, response.text
    assert stubbed_processing.count(f"{label}.transcribe_audio") == 0, (
        "ASR was handed a file the write never finished")
    assert stubbed_processing.count(f"{label}.analyze_speech_emotion") == 0
    # the text answer is still evaluated, exactly as the optional-audio contract requires
    assert EVALUATOR_FOR_ROUND[ep.name] in stubbed_processing.calls
    assert response.json()["audio_url"] is None
    assert persisted_clip_url(ep, db_session, target.id) is None
    assert read_bytes(slot) == PRIOR_CLIP


@pytest.mark.parametrize("ep_name", ROUND_ENDPOINTS, ids=ROUND_ENDPOINTS)
def test_typed_answer_is_still_evaluated_when_the_recording_fails(session_app, db_session,
                                                                  principals, faults,
                                                                  stubbed_processing, ep_name):
    """The optional-audio contract: losing the recording must not lose the answer."""
    ep = endpoint(ep_name)
    target = make_target(db_session, principals.caller.id, ep)
    slot = round_slot(ep, target.id, principals.caller.id)
    clear_round_clip(slot)

    faults.fail_chunk(1)
    response = submit_round(session_app, ep, principals.caller.auth, target.id, NEW_CLIP)

    assert response.status_code == 200, response.text
    assert EVALUATOR_FOR_ROUND[ep.name] in stubbed_processing.calls, (
        "the evaluation the contract promises never ran")
    assert response.json()["audio_url"] is None
    assert not slot.exists()


# ---------------------------------------------------------------------------
# 17 — Bounded-memory streaming evidence
# ---------------------------------------------------------------------------
def test_round_upload_streams_in_bounded_chunks_without_a_new_size_cap(session_app, db_session,
                                                                       principals, faults,
                                                                       monkeypatch):
    """U2 gains no new limit — a 3 MiB body over a 1 MiB configured cap still succeeds — and it
    streams: the body is copied chunk by chunk, never held as one buffer."""
    monkeypatch.setattr(settings, "max_upload_size_mb", 1)
    monkeypatch.setattr(upload_store, "CHUNK_BYTES", 64 * 1024)

    ep = endpoint("hr.answer")
    target = make_target(db_session, principals.caller.id, ep)
    slot = round_slot(ep, target.id, principals.caller.id)
    clear_round_clip(slot)
    body = bytes(range(256)) * (12 * 1024)  # 3 MiB, three times the configured cap
    assert len(body) == 3 * 1024 * 1024

    response = submit_round(session_app, ep, principals.caller.auth, target.id, body)

    assert response.status_code == 200, response.text
    assert read_bytes(slot) == body
    assert max(faults.chunk_sizes) <= 64 * 1024, f"unbounded write: {set(faults.chunk_sizes)}"
    assert len(faults.chunk_sizes) == 48, faults.chunk_sizes
    assert sum(faults.chunk_sizes) == len(body)


def test_jam_upload_streams_in_bounded_chunks_under_the_unchanged_cap(session_app, db_session,
                                                                      principals, faults,
                                                                      monkeypatch):
    assert settings.max_upload_size_mb == 200, "N3 must not move the U1 size limit"
    monkeypatch.setattr(upload_store, "CHUNK_BYTES", 16 * 1024)
    body = bytes(range(256)) * (64 * 1024)  # 16 MiB, comfortably under the real 200 MB cap

    response = create_jam(session_app, principals.caller.auth,
                          {"audio": ("clip.webm", body, "audio/webm")})

    assert response.status_code == 201, response.text
    assert max(faults.chunk_sizes) <= 16 * 1024
    assert len(faults.chunk_sizes) == 1024
    assert sum(faults.chunk_sizes) == len(body)


def test_jam_rejects_over_cap_with_the_original_413_and_no_file(session_app, db_session,
                                                                principals, monkeypatch):
    before = upload_snapshot()
    monkeypatch.setattr(settings, "max_upload_size_mb", 0)

    response = create_jam(session_app, principals.caller.auth,
                          {"audio": ("clip.webm", NEW_CLIP, "audio/webm")})

    assert response.status_code == 413, response.text
    assert response.json()["detail"] == "File exceeds maximum allowed size of 0 MB"
    assert upload_added(before) == [], (
        "the over-cap path used to unlink a handle it still held open (Windows: PermissionError)")
    assert marker_leftovers() == []


def test_streaming_helper_reads_only_bounded_sizes():
    """`write_from` asks the source for `chunk_bytes` at a time, so nothing holds a whole body."""
    asked: List[int] = []

    class RecordingSource:
        def __init__(self, data: bytes) -> None:
            self._buffer = io.BytesIO(data)

        def read(self, size: int = -1) -> bytes:
            asked.append(size)
            return self._buffer.read(size)

    root = upload_root() / "n3_stream"
    root.mkdir(parents=True, exist_ok=True)
    tx = upload_store.transaction()
    staged = tx.stage(root, "streamed.webm")
    written = staged.write_from(RecordingSource(b"x" * 1000), chunk_bytes=100)
    staged.publish()
    tx.finalize()

    assert written == 1000
    # Eleven asks for ten full chunks: a stream has to be asked once more, and get b"", before its
    # end is known. What must never appear is an unbounded ask (no size / -1), which would hand the
    # whole body to memory.
    assert asked == [100] * 11, asked
    assert all(size > 0 for size in asked), asked
    assert (root / "streamed.webm").read_bytes() == b"x" * 1000
    (root / "streamed.webm").unlink(missing_ok=True)
    root.rmdir()


# ---------------------------------------------------------------------------
# 18 — Optional-audio log content: identifiers yes, absolute paths no
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("ep_name", ROUND_ENDPOINTS, ids=ROUND_ENDPOINTS)
def test_optional_audio_warning_identifies_the_slot_without_a_path(session_app, db_session,
                                                                   principals, faults, caplog,
                                                                   ep_name):
    ep = endpoint(ep_name)
    target = make_target(db_session, principals.caller.id, ep)
    slot = round_slot(ep, target.id, principals.caller.id)
    seed_clip(slot, PRIOR_CLIP)

    # A rename failure is the leaking case: os.replace quotes both absolute paths in its message.
    faults.fail_publish_move()
    with caplog.at_level(logging.WARNING):
        response = submit_round(session_app, ep, principals.caller.auth, target.id, NEW_CLIP)

    assert response.status_code == 200, response.text
    messages = [r.getMessage() for r in caplog.records if "Failed to save" in r.getMessage()]
    assert messages, f"the failed recording was never reported: " \
                     f"{[r.getMessage() for r in caplog.records]}"
    text = messages[0]
    assert f"session={target.id}" in text, text
    assert f"user={principals.caller.id}" in text, text
    assert "OSError" in text, text
    assert str(upload_root()) not in text, f"absolute upload path leaked into the log: {text}"
    assert str(slot) not in text, f"absolute clip path leaked into the log: {text}"
    assert "Bearer" not in text
    assert NEW_CLIP.decode("latin-1") not in text, "the uploaded body appeared in the log"


def test_the_route_response_never_carries_a_filesystem_path(session_app, db_session, principals,
                                                            faults):
    """A storage fault must surface as a status, not as a path or a stack."""
    ep = endpoint("hr.answer")
    target = make_target(db_session, principals.caller.id, ep)
    faults.fail_chunk(1)
    response = submit_round(session_app, ep, principals.caller.auth, target.id, NEW_CLIP)
    assert response.status_code == 200, response.text
    assert str(upload_root()) not in response.text


# ---------------------------------------------------------------------------
# 19 — Static guards over the migrated routes
# ---------------------------------------------------------------------------
def test_no_whole_body_write_remains_in_the_upload_routes():
    for filename in UPLOAD_ROUTES:
        source = route_source(filename)
        assert ".read()" not in source, f"{filename} still reads an upload body in one call"
        assert '"wb"' not in source, f"{filename} still opens a destination for a direct write"


def test_every_upload_route_runs_inside_a_transaction():
    for filename in UPLOAD_ROUTES:
        source = route_source(filename)
        assert "upload_store.transaction()" in source, f"{filename} never opens an upload tx"
        assert "tx.rollback()" in source, f"{filename} never unwinds on failure"
        assert "tx.finalize()" in source, f"{filename} never releases its backups on success"


def test_helper_files_can_never_match_the_auth_e_clip_grammar():
    """A temp, backup or trash name must not be playable by name: the clip patterns are
    authorization inputs, and every file this module makes is `<clip>.upload-<kind><hex>`."""
    from app.services.audio_ownership import (GUESSTIMATE_FILENAME_PATTERN,
                                              HR_FILENAME_PATTERN)
    clip = "session_12_hr_q_2_7.webm"
    for mark in (upload_store._TEMP_MARK, upload_store._BACKUP_MARK, upload_store._TRASH_MARK):
        made = f"{clip}{mark}0123456789abcdef"
        assert HR_FILENAME_PATTERN.fullmatch(made) is None
        assert GUESSTIMATE_FILENAME_PATTERN.fullmatch(made) is None
        # and the marker is what makes that true: the same suffix without it is a real clip name
        assert HR_FILENAME_PATTERN.fullmatch(clip) is not None
