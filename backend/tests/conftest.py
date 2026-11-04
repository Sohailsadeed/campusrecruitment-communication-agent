"""AUTH-A test fixtures.

Imports app.routes.auth but never main.py, so no startup DDL, ALTER TABLE migration,
HR seeding, log-file handler or emotion-model warm-up can run. All state is created
outside the repository.
"""
from __future__ import annotations

import atexit
import os
import shutil
import sys
import tempfile
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = BACKEND_DIR.parent

TEMP_ROOT = Path(tempfile.mkdtemp(prefix="speakflow-test-"))
atexit.register(shutil.rmtree, TEMP_ROOT, ignore_errors=True)

TEST_DB_PATH = TEMP_ROOT / "auth_a.db"

os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH}"
os.environ["SECRET_KEY"] = "auth-a-test-secret"
os.environ["UPLOAD_DIR"] = str(TEMP_ROOT / "uploads")
os.environ["LOGS_DIR"] = str(TEMP_ROOT / "logs")
os.environ["RESUME_UPLOAD_DIR"] = str(TEMP_ROOT / "resumes")

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from config import settings  # noqa: E402


def _assert_outside_workspace(label: str, value: str) -> None:
    resolved = str(Path(value).resolve()) if not value.startswith("sqlite") else value
    temp_root = str(TEMP_ROOT.resolve())
    if temp_root not in resolved:
        raise RuntimeError(
            f"AUTH-A isolation tripwire: {label} resolved to {value!r}, outside the "
            f"approved temp envelope {temp_root!r}. Aborting before anything is written."
        )


_assert_outside_workspace("DATABASE_URL", str(settings.database_url))
_assert_outside_workspace("UPLOAD_DIR", str(settings.upload_dir))
_assert_outside_workspace("LOGS_DIR", str(settings.logs_dir))

if TEST_DB_PATH.exists():
    raise RuntimeError(f"AUTH-A isolation tripwire: unexpected pre-existing test DB {TEST_DB_PATH}")

import pytest  # noqa: E402
from fastapi import Depends, FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app.models  # noqa: E402,F401  (registers every table on Base.metadata)
from app.database.engine import Base, SessionLocal, engine, get_db  # noqa: E402
from app.models.user import User  # noqa: E402
from app.routes import auth as auth_module  # noqa: E402
from app.routes.auth import get_current_user  # noqa: E402

DETAIL = "Could not validate credentials"


@pytest.fixture()
def db_session():
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        session.get_bind().dispose()


@pytest.fixture()
def probe_app(db_session):
    application = FastAPI()
    application.include_router(auth_module.router)

    @application.get("/probe/current-user")
    def probe(current_user: User = Depends(get_current_user)) -> dict:
        return {"user_id": current_user.id, "email": current_user.email}

    def _override():
        yield db_session

    application.dependency_overrides[get_db] = _override
    with TestClient(application) as client:
        yield client


@pytest.fixture()
def register_user(probe_app):
    def _register(email: str = "candidate@example.com", username: str = "candidate") -> str:
        response = probe_app.post(
            "/api/auth/register",
            json={"email": email, "username": username, "password": "supersecret"},
        )
        assert response.status_code == 201, response.text
        return response.json()["access_token"]

    return _register
