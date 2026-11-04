"""AUTH-E: session-ownership gate for candidate recording playback.

A media element cannot send an Authorization header, so playback is only safe once the route
itself proves that *this* authenticated user owns the recording. This module is that proof and
nothing else: it decides whether a clip may be served and which confined path holds it. It never
writes, migrates, or opens a transaction of its own.

Order matters. The raw filename is matched against the exact grammar the round routes emit
before it is turned into integers, before it is compared with anything, and before any path is
built — so a hostile name can never reach the filesystem, and a normalising comparison can never
be talked into accepting a lookalike.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn, Optional
from urllib.parse import urlsplit

from fastapi import HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.models.session import Session as SessionModel
from app.models.user import User
from config import settings

# Byte-for-byte the detail the route already used for a genuinely missing clip, so a denial
# cannot be told apart from an absence.
NOT_FOUND_DETAIL = "Audio recording file not found."

HR_SUBDIR = "hr_audio"
GUESSTIMATE_SUBDIR = "guesstimate_audio"
TECHNICAL_SUBDIR = "technical_audio"
HR_ROUTE_PREFIX = "/api/hr/audio/"
GUESSTIMATE_ROUTE_PREFIX = "/api/guesstimate/audio/"
TECHNICAL_ROUTE_PREFIX = "/api/technical/audio/"

# hr.py names its clips session_<id>_hr_q_<n>_<uid>.webm, guesstimate.py
# session_<id>_guesstimate_<uid>.webm and technical.py session_<id>_q_<n>_<uid>.webm.
# A 12-digit cap keeps a 10^40 session id out of int().
# ASCII digits only: \d would accept Arabic-Indic digits that int() then rewrites.
HR_FILENAME_PATTERN = re.compile(r"session_([1-9][0-9]{0,11})_hr_q_([1-9])_([1-9][0-9]{0,11})\.webm")
GUESSTIMATE_FILENAME_PATTERN = re.compile(
    r"session_([1-9][0-9]{0,11})_guesstimate_([1-9][0-9]{0,11})\.webm"
)
TECHNICAL_FILENAME_PATTERN = re.compile(
    r"session_([1-9][0-9]{0,11})_q_([1-9]|10)_([1-9][0-9]{0,11})\.webm"
)

# StartHRRequest caps max_questions at 8; a larger question number is not a clip this app made.
MAX_HR_QUESTION = 8
# StartInterviewRequest caps max_questions at 10, so technical question numbers run 1..10.
MAX_TECHNICAL_QUESTION = 10


@dataclass(frozen=True)
class HrClip:
    session_id: int
    question_number: int
    recording_owner_id: int
    filename: str
    stored_url: str


@dataclass(frozen=True)
class GuesstimateClip:
    session_id: int
    recording_owner_id: int
    filename: str
    stored_url: str


@dataclass(frozen=True)
class TechnicalClip:
    session_id: int
    question_number: int
    recording_owner_id: int
    filename: str
    stored_url: str


def _denied() -> NoReturn:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=NOT_FOUND_DETAIL)


def _canonical_int(raw: str) -> Optional[int]:
    """int() only after proving the digits round-trip, so the rebuilt name equals the raw one."""
    value = int(raw)
    return value if str(value) == raw else None


def parse_hr_filename(filename: str) -> Optional[HrClip]:
    """The canonical HrClip for this raw name, or None. Never a best guess."""
    if not isinstance(filename, str):
        return None
    match = HR_FILENAME_PATTERN.fullmatch(filename)
    if match is None:
        return None
    session_id = _canonical_int(match.group(1))
    question_number = _canonical_int(match.group(2))
    owner_id = _canonical_int(match.group(3))
    if session_id is None or question_number is None or owner_id is None:
        return None
    if not 1 <= question_number <= MAX_HR_QUESTION:
        return None
    canonical = f"session_{session_id}_hr_q_{question_number}_{owner_id}.webm"
    if canonical != filename:
        return None
    return HrClip(session_id, question_number, owner_id, canonical, HR_ROUTE_PREFIX + canonical)


def parse_guesstimate_filename(filename: str) -> Optional[GuesstimateClip]:
    if not isinstance(filename, str):
        return None
    match = GUESSTIMATE_FILENAME_PATTERN.fullmatch(filename)
    if match is None:
        return None
    session_id = _canonical_int(match.group(1))
    owner_id = _canonical_int(match.group(2))
    if session_id is None or owner_id is None:
        return None
    canonical = f"session_{session_id}_guesstimate_{owner_id}.webm"
    if canonical != filename:
        return None
    return GuesstimateClip(session_id, owner_id, canonical, GUESSTIMATE_ROUTE_PREFIX + canonical)


def parse_technical_filename(filename: str) -> Optional[TechnicalClip]:
    if not isinstance(filename, str):
        return None
    match = TECHNICAL_FILENAME_PATTERN.fullmatch(filename)
    if match is None:
        return None
    session_id = _canonical_int(match.group(1))
    question_number = _canonical_int(match.group(2))
    owner_id = _canonical_int(match.group(3))
    if session_id is None or question_number is None or owner_id is None:
        return None
    if not 1 <= question_number <= MAX_TECHNICAL_QUESTION:
        return None
    canonical = f"session_{session_id}_q_{question_number}_{owner_id}.webm"
    if canonical != filename:
        return None
    return TechnicalClip(
        session_id, question_number, owner_id, canonical, TECHNICAL_ROUTE_PREFIX + canonical
    )


def stored_audio_path_matches(stored: object, expected_route: str) -> bool:
    """True only when the stored string is exactly this route plus this clip name.

    The routes always write a root-relative path, so anything carrying a scheme or an authority
    is refused outright — "http://evil.example" and "http://our.own.host" are indistinguishable
    from a string we may treat as a route, and neither was ever written here. The comparison is
    made on split parts rather than normalised text: urlsplit does not collapse dot segments and
    leaves a trailing slash or a ";parameter" inside .path, so equality here means the blob
    really lists this clip. ?query and #fragment are moved out of .path by urlsplit and so need
    their own refusal.
    """
    if not isinstance(stored, str) or not stored:
        return False
    if "\\" in stored or "\x00" in stored:
        return False
    if not expected_route:
        return False
    try:
        parts = urlsplit(stored)
    except ValueError:
        return False
    if parts.scheme or parts.netloc:
        return False
    if parts.query or parts.fragment:
        return False
    return parts.path == expected_route


def authorized_question_urls(detail: object) -> list[str]:
    """Every non-empty audio_url in a round's questions blob, tolerating a corrupted JSON column.

    HR and Technical both keep one entry per answered question in a JSON list, so the same
    extraction proves "this clip is a recording the round itself recorded" for both.
    """
    questions = getattr(detail, "questions", None)
    if not isinstance(questions, list):
        return []
    urls: list[str] = []
    for entry in questions:
        if not isinstance(entry, dict):
            continue
        value = entry.get("audio_url")
        if isinstance(value, str) and value:
            urls.append(value)
    return urls


def _owned_session(db: Session, session_id: int, recording_owner_id: int, current_user: User) -> SessionModel:
    """The session named by the clip must exist, be the requester's, and name them back."""
    if recording_owner_id != current_user.id:
        _denied()
    session = db.get(SessionModel, session_id)
    # user_id IS NULL (a legacy or orphan row) owns the clip as little as anyone else does.
    if session is None or session.user_id != current_user.id:
        _denied()
    return session


def _confined_clip_path(subdir: str, filename: str) -> Path:
    """Build and resolve the clip path, refusing anything that lands outside the upload root.

    `filename` is a canonical reconstruction with no separators, so this check exists for the
    directory itself and for a symlink planted in it.
    """
    root = Path(settings.upload_dir).resolve()
    resolved = (root / subdir / filename).resolve()
    if not resolved.is_relative_to(root):
        _denied()
    return resolved


def _is_readable_non_empty_file(path: Path) -> bool:
    try:
        if not path.is_file():
            return False
        return path.stat().st_size > 0 and os.access(path, os.R_OK)
    except OSError:
        return False


def resolve_hr_audio_path(db: Session, current_user: User, filename: str) -> Path:
    clip = parse_hr_filename(filename)
    if clip is None:
        _denied()
    session = _owned_session(db, clip.session_id, clip.recording_owner_id, current_user)
    detail = session.hr_detail
    if detail is None:
        _denied()
    if not any(
        stored_audio_path_matches(url, clip.stored_url)
        for url in authorized_question_urls(detail)
    ):
        _denied()
    path = _confined_clip_path(HR_SUBDIR, clip.filename)
    if not _is_readable_non_empty_file(path):
        _denied()
    return path


def resolve_guesstimate_audio_path(db: Session, current_user: User, filename: str) -> Path:
    clip = parse_guesstimate_filename(filename)
    if clip is None:
        _denied()
    session = _owned_session(db, clip.session_id, clip.recording_owner_id, current_user)
    case = session.guesstimate_detail
    if case is None:
        _denied()
    if not stored_audio_path_matches(case.audio_url, clip.stored_url):
        _denied()
    path = _confined_clip_path(GUESSTIMATE_SUBDIR, clip.filename)
    if not _is_readable_non_empty_file(path):
        _denied()
    return path


def resolve_technical_audio_path(db: Session, current_user: User, filename: str) -> Path:
    clip = parse_technical_filename(filename)
    if clip is None:
        _denied()
    session = _owned_session(db, clip.session_id, clip.recording_owner_id, current_user)
    detail = session.technical_detail
    if detail is None:
        _denied()
    if not any(
        stored_audio_path_matches(url, clip.stored_url)
        for url in authorized_question_urls(detail)
    ):
        _denied()
    path = _confined_clip_path(TECHNICAL_SUBDIR, clip.filename)
    if not _is_readable_non_empty_file(path):
        _denied()
    return path


def audio_file_response(path: Path) -> FileResponse:
    """Serve an already-authorised clip.

    private, no-store: these are spoken answers by a named candidate, the authorisation decision
    is per-request, and a shared cache must not be able to hand a clip to the next reader.
    No Content-Disposition: an attachment prompt would leak the recording name into the browser's
    download UI and break the inline <audio> playback the reports rely on.

    Accepted residual race: FileResponse stats and opens the path when it is sent, not now, so a
    file swapped between the check above and the send is still served. Closing it needs a
    descriptor-based send (O_NOFOLLOW / openat), which is AUTH-E2, deliberately out of scope.
    """
    return FileResponse(
        path=str(path),
        media_type="audio/webm",
        headers={"Cache-Control": "private, no-store"},
    )
