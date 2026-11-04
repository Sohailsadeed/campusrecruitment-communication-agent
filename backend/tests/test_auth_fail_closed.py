"""AUTH-A (C-01): get_current_user fails closed and never creates an identity."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from jose import jwt
from sqlalchemy import func, select

from app.models.user import User
from app.routes.auth import create_access_token, decode_token, get_current_user
from conftest import DETAIL, BACKEND_DIR
from config import settings


class _NoWriteDb:
    """Stands in for the ORM session. Any write attempt is itself the test failure."""

    def __init__(self, scalar_result=None, scalar_raises=None):
        self._scalar_result = scalar_result
        self._scalar_raises = scalar_raises
        self.writes = 0

    def scalar(self, statement):
        if self._scalar_raises is not None:
            raise self._scalar_raises
        return self._scalar_result

    def add(self, *args, **kwargs):
        self.writes += 1
        raise AssertionError("get_current_user must never add a row")

    def commit(self, *args, **kwargs):
        self.writes += 1
        raise AssertionError("get_current_user must never commit")

    def flush(self, *args, **kwargs):
        self.writes += 1
        raise AssertionError("get_current_user must never flush")

    def refresh(self, *args, **kwargs):
        self.writes += 1
        raise AssertionError("get_current_user must never refresh")


def _expired_token(subject: str) -> str:
    payload = {"sub": subject, "exp": datetime.now(timezone.utc) - timedelta(days=1)}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def _token_signed_elsewhere(subject: str) -> str:
    payload = {"sub": subject, "exp": datetime.now(timezone.utc) + timedelta(hours=1)}
    return jwt.encode(payload, "a-different-secret", algorithm=settings.algorithm)


SUBJECT = "candidate@example.com"
REJECTED_HEADERS = [
    pytest.param(None, id="missing-header"),
    pytest.param("", id="empty-header"),
    pytest.param("Bearer", id="scheme-without-space"),
    pytest.param("token abcdef", id="no-bearer-scheme"),
    pytest.param("Basic dXNlcjpwYXNz", id="basic-scheme"),
    pytest.param("Bearer ", id="bearer-without-token"),
    pytest.param("Bearer    ", id="bearer-whitespace-only"),
    pytest.param("Bearer not.a.real.jwt", id="malformed-token"),
    pytest.param(f"Bearer {_expired_token(SUBJECT)}", id="expired-token"),
    pytest.param(f"Bearer {_token_signed_elsewhere(SUBJECT)}", id="wrong-signing-secret"),
]


@pytest.mark.parametrize("authorization", [param for param in REJECTED_HEADERS])
def test_invalid_credentials_are_rejected_uniformly(authorization):
    db = _NoWriteDb(scalar_result=User(id=1, email=SUBJECT))
    with pytest.raises(HTTPException) as raised:
        get_current_user(authorization, db)
    assert raised.value.status_code == 401
    assert raised.value.detail == DETAIL
    assert raised.value.headers == {"WWW-Authenticate": "Bearer"}


def test_valid_token_returns_the_resolved_user():
    stored = User(id=7, email=SUBJECT, username="candidate")
    db = _NoWriteDb(scalar_result=stored)
    assert get_current_user(f"Bearer {create_access_token(SUBJECT)}", db) is stored


def test_unknown_subject_is_rejected_without_any_write():
    db = _NoWriteDb(scalar_result=None)
    with pytest.raises(HTTPException) as raised:
        get_current_user(f"Bearer {create_access_token('removed@example.com')}", db)
    assert raised.value.status_code == 401
    assert db.writes == 0


def test_empty_users_table_is_rejected_without_creating_a_developer():
    db = _NoWriteDb(scalar_result=None)
    with pytest.raises(HTTPException) as raised:
        get_current_user(f"Bearer {create_access_token('anyone@example.com')}", db)
    assert raised.value.status_code == 401
    assert raised.value.detail == DETAIL
    assert db.writes == 0


def test_database_fault_propagates_instead_of_becoming_an_authentication_failure():
    """An operational failure must not be laundered into a 401."""
    db = _NoWriteDb(scalar_raises=RuntimeError("database is down"))
    with pytest.raises(RuntimeError, match="database is down"):
        get_current_user(f"Bearer {create_access_token(SUBJECT)}", db)


def test_decode_token_stays_narrow():
    assert decode_token("not.a.real.jwt") is None
    assert decode_token(create_access_token(SUBJECT)) == SUBJECT


# --- Route-level behaviour ----------------------------------------------------

def test_route_rejects_a_headerless_request(probe_app):
    response = probe_app.get("/probe/current-user")
    assert response.status_code == 401
    assert response.json() == {"detail": DETAIL}
    assert response.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.parametrize(
    "header",
    ["Bearer", "token abcdef", "Basic dXNlcjpwYXNz", "Bearer ", "Bearer not.a.real.jwt"],
    ids=["scheme-without-space", "no-bearer-scheme", "basic-scheme", "empty-token", "malformed"],
)
def test_route_rejects_every_invalid_credential_the_same_way(probe_app, header):
    response = probe_app.get("/probe/current-user", headers={"Authorization": header})
    assert response.status_code == 401
    assert response.json() == {"detail": DETAIL}
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_route_accepts_a_registered_users_token(probe_app, register_user):
    response = probe_app.get(
        "/probe/current-user", headers={"Authorization": f"Bearer {register_user()}"}
    )
    assert response.status_code == 200, response.text
    assert response.json()["email"] == SUBJECT


def test_unknown_subject_yields_401_and_still_no_user_row(probe_app, db_session):
    token = create_access_token("ghost@example.com")
    response = probe_app.get("/probe/current-user", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert db_session.scalar(select(func.count()).select_from(User)) == 0


def test_expired_token_is_rejected_at_the_route(probe_app, register_user):
    register_user()
    response = probe_app.get(
        "/probe/current-user", headers={"Authorization": f"Bearer {_expired_token(SUBJECT)}"}
    )
    assert response.status_code == 401


def test_public_auth_endpoints_stay_reachable(probe_app):
    registered = probe_app.post(
        "/api/auth/register",
        json={"email": "public@example.com", "username": "publicuser", "password": "supersecret"},
    )
    assert registered.status_code == 201, registered.text
    logged_in = probe_app.post(
        "/api/auth/login", json={"email": "public@example.com", "password": "supersecret"}
    )
    assert logged_in.status_code == 200, logged_in.text
    token = logged_in.json()["access_token"]

    assert probe_app.get("/api/auth/me").status_code == 401
    assert probe_app.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {token}"}
    ).status_code == 200


def test_no_hardcoded_fallback_identity_remains():
    offenders = [
        str(path.relative_to(BACKEND_DIR))
        for path in (BACKEND_DIR / "app").rglob("*.py")
        if "developer@verbaliq.local" in path.read_text(encoding="utf-8", errors="ignore")
        or "verbaliq123" in path.read_text(encoding="utf-8", errors="ignore")
    ]
    assert offenders == []
