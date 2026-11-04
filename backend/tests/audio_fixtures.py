"""AUTH-E fixtures: only the routers under test, data created inside the temp envelope.

conftest.py owns the environment (DATABASE_URL/UPLOAD_DIR/LOGS_DIR inside a temp dir outside
the repository) and the db_session fixture. Nothing here imports main.py, so no startup DDL,
no ALTER TABLE migration, no HR seeding and no rotating log handlers can run.
"""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from conftest import TEMP_ROOT

from app.database.engine import get_db
from app.models.guesstimate import GuesstimateCase
from app.models.hr import HRInterview
from app.models.session import Session as SessionModel
from app.models.technical import TechnicalInterview
from app.models.user import User
from app.routes import guesstimate as guesstimate_module
from app.routes import hr as hr_module
from app.routes import technical as technical_module
from app.routes.auth import create_access_token
from config import settings

# The detail text every denial must use: the pre-existing missing-file wording, so an
# authorization denial is byte-for-byte indistinguishable from a genuinely absent clip.
NOT_FOUND_DETAIL = "Audio recording file not found."

HR_BODY = b"\x1a\x45\xdf\xa3auth-e-hr-clip"
GUESSTIMATE_BODY = b"\x1a\x45\xdf\xa3auth-e-guesstimate-clip"
TECHNICAL_BODY = b"\x1a\x45\xdf\xa3technical-audio-clip"

# Every clip directory this envelope knows about, so one fixture wipes all of them.
CLIP_DIRS = ("hr_audio", "guesstimate_audio", "technical_audio")


def hr_filename(session_id: int, question_number: int, owner_id: int) -> str:
    return f"session_{session_id}_hr_q_{question_number}_{owner_id}.webm"


def guesstimate_filename(session_id: int, owner_id: int) -> str:
    return f"session_{session_id}_guesstimate_{owner_id}.webm"


def technical_filename(session_id: int, question_number: int, owner_id: int) -> str:
    return f"session_{session_id}_q_{question_number}_{owner_id}.webm"


def hr_url(filename: str) -> str:
    return f"/api/hr/audio/{filename}"


def guesstimate_url(filename: str) -> str:
    return f"/api/guesstimate/audio/{filename}"


def technical_url(filename: str) -> str:
    return f"/api/technical/audio/{filename}"


@dataclass(frozen=True)
class Account:
    id: int
    email: str
    token: str

    @property
    def auth(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}


@pytest.fixture(autouse=True)
def clean_clip_dirs():
    """One temp upload dir serves the whole run and session ids repeat per test, so a clip left
    behind by one test would silently satisfy the next test's missing-file expectation. Wipe every
    clip directory before and after every test."""
    root = Path(settings.upload_dir).resolve()
    if TEMP_ROOT not in root.parents:
        raise AssertionError(f"refusing to clean a clip dir outside the temp envelope: {root}")
    for name in CLIP_DIRS:
        _remove_clips(root, root / name)
    yield
    for name in CLIP_DIRS:
        _remove_clips(root, root / name)


def _remove_clips(root: Path, target: Path) -> None:
    if not target.exists():
        return
    if target.is_dir() and not target.resolve().is_relative_to(root):
        # A directory reached through a link or junction: remove the link, never its contents.
        os.rmdir(target)
        return
    if not target.is_dir():
        return
    for entry in target.iterdir():
        if entry.is_symlink() or entry.is_file():
            entry.unlink()
        elif not entry.resolve().is_relative_to(root):
            os.rmdir(entry)
        else:
            shutil.rmtree(entry)


@pytest.fixture()
def audio_app(db_session):
    application = FastAPI()
    application.include_router(hr_module.router)
    application.include_router(guesstimate_module.router)
    application.include_router(technical_module.router)

    def _override():
        yield db_session

    application.dependency_overrides[get_db] = _override
    with TestClient(application) as client:
        yield client


@pytest.fixture()
def make_account(db_session):
    counter = {"n": 0}

    def _make() -> Account:
        counter["n"] += 1
        name = f"candidate{counter['n']}"
        user = User(
            email=f"{name}@audio.test",
            username=name,
            hashed_password="not-a-real-hash",
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
        return Account(id=user.id, email=user.email, token=create_access_token(user.email))

    return _make


def create_hr_session(
    db,
    owner_id: Optional[int],
    *,
    max_questions: int = 4,
    question_count: int = 1,
    questions: Optional[list[Any]] = None,
    with_detail: bool = True,
) -> SessionModel:
    """A session row, plus its HRInterview row unless the test is about a missing link."""
    session = SessionModel(
        user_id=owner_id,
        title="AUTH-E HR session",
        round_type="hr",
        status="in_progress",
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    if not with_detail:
        return session

    detail = HRInterview(
        session_id=session.id,
        role="Backend Engineer",
        interview_mode="standard_hr",
        max_questions=max_questions,
        question_count=question_count,
        questions=[] if questions is None else questions,
    )
    db.add(detail)
    db.commit()
    db.refresh(session)
    return session


def create_guesstimate_session(
    db,
    owner_id: Optional[int],
    *,
    audio_url: Optional[str] = None,
    with_detail: bool = True,
) -> SessionModel:
    session = SessionModel(
        user_id=owner_id,
        title="AUTH-E guesstimate session",
        round_type="guesstimate",
        status="in_progress",
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    if not with_detail:
        return session

    case = GuesstimateCase(
        session_id=session.id,
        question="Estimate the number of coffee shops in a city.",
        category="Market Sizing",
        difficulty="Intermediate",
        approach_type="top_down",
        candidate_answer="",
        audio_url=audio_url,
    )
    db.add(case)
    db.commit()
    db.refresh(session)
    return session


def create_technical_session(
    db,
    owner_id: Optional[int],
    *,
    max_questions: int = 5,
    question_count: int = 1,
    questions: Optional[list[Any]] = None,
    with_detail: bool = True,
) -> SessionModel:
    """A session row, plus its TechnicalInterview row unless the test is about a missing link."""
    session = SessionModel(
        user_id=owner_id,
        title="Technical audio session",
        round_type="technical",
        status="in_progress",
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    if not with_detail:
        return session

    detail = TechnicalInterview(
        session_id=session.id,
        role="Full Stack Engineer",
        max_questions=max_questions,
        question_count=question_count,
        questions=[] if questions is None else questions,
    )
    db.add(detail)
    db.commit()
    db.refresh(session)
    return session


def write_clip(subdir: str, filename: str, content: bytes = HR_BODY) -> Path:
    """Put a clip inside settings.upload_dir; refuses to write anywhere else."""
    root = Path(settings.upload_dir).resolve()
    dest = (root / subdir / filename).resolve()
    if root not in dest.parents:
        raise AssertionError(f"test fixture refused to write outside the upload dir: {dest}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(content)
    return dest
