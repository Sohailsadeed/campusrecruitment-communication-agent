"""LiveKit V1 — room access tokens: authentication, authorization, grants, expiry, failure modes.

The contract under test is narrow: an authenticated candidate gets a short-lived token for the room
belonging to *their own* HR session, with microphone publishing only, and everything else gets
either the uniform AUTH-A 401, the uniform AUTH-C 404, a 422 or a 503 — never a token.

Signature verification is real: each accepted token is decoded with the configured API secret, so a
passing test proves the SFU would accept it, not merely that a string came back. Nothing here
contacts a LiveKit server; the browser-connected checks are separate and reported separately.
"""
from __future__ import annotations

import ast
import builtins
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from session_fixtures import (  # noqa: F401  (make_account/envelope_check are fixtures)
    BACKEND_DIR,
    BAD_AUTH_HEADERS,
    NOT_FOUND_DETAIL,
    SERVICES_DIR,
    UNAUTHENTICATED,
    WWW_AUTHENTICATE,
    depends_names,
    envelope_check,
    make_account,
    route_source,
)

from app.models.session import Session as SessionModel
from app.routes import livekit as livekit_module
from app.services import livekit_access
from config import settings

TOKEN_PATH = "/api/livekit/token"
ABSENT_ID = 987_654

API_KEY = "APItestkeyid"
API_SECRET = "test-secret-value-not-a-real-one"
WS_URL = "ws://livekit.test:7880"

NOT_CONFIGURED = "LiveKit room access is not configured on this server."
SIGNING_FAILED = "Could not issue LiveKit room access. Please try again."


# ---------------------------------------------------------------------------
# Wiring
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def livekit_settings(monkeypatch):
    """A configured server by default; the unconfigured cases clear one field."""
    monkeypatch.setattr(settings, "livekit_api_key", API_KEY)
    monkeypatch.setattr(settings, "livekit_api_secret", API_SECRET)
    monkeypatch.setattr(settings, "livekit_url", WS_URL)
    monkeypatch.setattr(settings, "livekit_room_prefix", "speakflow")
    monkeypatch.setattr(settings, "livekit_token_ttl_minutes", 15)


@pytest.fixture
def client(db_session) -> TestClient:
    """The LiveKit router mounted as main.py mounts it, on the test database."""
    from app.database.engine import get_db

    application = FastAPI()
    application.include_router(livekit_module.router)

    def _dependency():
        yield db_session

    application.dependency_overrides[get_db] = _dependency
    with TestClient(application) as test_client:
        yield test_client


@pytest.fixture
def hr_session(db_session):
    counter = {"n": 0}

    def _create(owner_id: Optional[int], round_type: str = "hr") -> SessionModel:
        counter["n"] += 1
        session = SessionModel(
            user_id=owner_id,
            title=f"LiveKit fixture session {counter['n']}",
            description="Fixture row created by the LiveKit V1 suite.",
            duration_seconds=42.0,
            round_type=round_type,
            status="in_progress",
            overall_score=None,
            round_metadata={},
            report=None,
        )
        db_session.add(session)
        db_session.commit()
        db_session.refresh(session)
        return session

    return _create


def request_token(client: TestClient, *, headers: Dict[str, str], body: Any):
    return client.post(TOKEN_PATH, json=body, headers=headers)


def claims_of(token: str) -> Dict[str, Any]:
    """Decode with the configured secret: this is the SFU's own check, run here."""
    return jwt.decode(token, API_SECRET, algorithms=["HS256"])


# ---------------------------------------------------------------------------
# 1 — the owner gets real, correctly-scoped access
# ---------------------------------------------------------------------------
def test_owner_receives_a_token_the_server_would_accept(client, make_account, hr_session):
    owner = make_account()
    session = hr_session(owner.id)

    response = request_token(client, headers=owner.auth, body={"session_id": session.id})

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"url", "token", "room_name", "identity", "expires_at", "ttl_seconds"}
    assert body["url"] == WS_URL

    claims = claims_of(body["token"])
    assert claims["iss"] == API_KEY
    assert claims["sub"] == f"user-{owner.id}" == body["identity"]
    assert claims["video"]["room"] == f"speakflow-hr-{session.id}-{owner.id}" == body["room_name"]


def test_grants_are_microphone_only(client, make_account, hr_session):
    owner = make_account()
    session = hr_session(owner.id)

    body = request_token(client, headers=owner.auth,
                         body={"session_id": session.id}).json()
    video = claims_of(body["token"])["video"]

    assert video == {
        "room": f"speakflow-hr-{session.id}-{owner.id}",
        "roomJoin": True,
        "canPublish": True,
        "canSubscribe": True,
        "canPublishData": False,
        "canPublishSources": ["microphone"],
        "canUpdateOwnMetadata": False,
    }


def test_token_expiry_matches_the_configured_ttl(client, make_account, hr_session, monkeypatch):
    monkeypatch.setattr(settings, "livekit_token_ttl_minutes", 7)
    owner = make_account()
    session = hr_session(owner.id)

    body = request_token(client, headers=owner.auth,
                         body={"session_id": session.id}).json()
    claims = claims_of(body["token"])

    assert claims["exp"] - claims["nbf"] == 7 * 60
    assert body["ttl_seconds"] == 7 * 60
    # The countdown the client is told is the expiry the token actually carries.
    assert datetime.fromisoformat(body["expires_at"]) == datetime.fromtimestamp(
        claims["exp"], timezone.utc)


def test_two_candidates_and_two_sessions_never_share_a_room(client, make_account, hr_session):
    first = make_account()
    second = make_account()
    first_session = hr_session(first.id)
    second_session = hr_session(second.id)
    other_of_first = hr_session(first.id)

    rooms = [request_token(client, headers=account.auth,
                           body={"session_id": session_id}).json()["room_name"]
             for account, session_id in ((first, first_session.id),
                                         (second, second_session.id),
                                         (first, other_of_first.id))]

    assert len(set(rooms)) == 3, rooms
    # Re-requesting access for the same session is the same identity, so one candidate cannot
    # appear as two participants by asking for a second token.
    repeats = {request_token(client, headers=first.auth,
                             body={"session_id": first_session.id}).json()["identity"]
               for _ in range(3)}
    assert repeats == {f"user-{first.id}"}


# ---------------------------------------------------------------------------
# 2 — refusal: unauthenticated, not-yours, wrong round, malformed
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("authorization", BAD_AUTH_HEADERS)
def test_unauthenticated_and_bad_credentials_get_the_uniform_401(client, make_account,
                                                                  hr_session, authorization):
    owner = make_account()
    owner_session = hr_session(owner.id)
    headers = None if authorization is None else {"Authorization": authorization}

    response = client.post(TOKEN_PATH, json={"session_id": owner_session.id}, headers=headers)

    assert response.status_code == 401, response.text
    assert response.json() == {"detail": UNAUTHENTICATED}
    assert response.headers.get("www-authenticate") == WWW_AUTHENTICATE


def test_a_foreign_session_is_indistinguishable_from_no_session(client, make_account, hr_session):
    victim = make_account()
    caller = make_account()
    victim_session = hr_session(victim.id)

    response = request_token(client, headers=caller.auth,
                             body={"session_id": victim_session.id})

    assert response.status_code == 404, response.text
    assert response.json() == {"detail": NOT_FOUND_DETAIL}
    assert "token" not in response.text


@pytest.mark.parametrize("round_type", ["jam", "technical", "guesstimate"])
def test_a_session_of_another_round_is_refused(client, make_account, hr_session, round_type):
    owner = make_account()
    other = hr_session(owner.id, round_type=round_type)

    response = request_token(client, headers=owner.auth, body={"session_id": other.id})

    assert response.status_code == 404, response.text
    assert response.json() == {"detail": NOT_FOUND_DETAIL}


def test_an_orphaned_session_is_refused(client, make_account, hr_session):
    owner = make_account()
    orphan = hr_session(None)

    response = request_token(client, headers=owner.auth, body={"session_id": orphan.id})

    assert response.status_code == 404, response.text


def test_an_absent_session_is_refused(client, make_account):
    owner = make_account()

    response = request_token(client, headers=owner.auth, body={"session_id": ABSENT_ID})

    assert response.status_code == 404, response.text
    assert response.json() == {"detail": NOT_FOUND_DETAIL}


@pytest.mark.parametrize("body", [
    pytest.param({}, id="missing-session-id"),
    pytest.param({"session_id": 0}, id="zero"),
    pytest.param({"session_id": -1}, id="negative"),
    pytest.param({"session_id": "not-a-number"}, id="non-numeric"),
    pytest.param({"session_id": None}, id="null"),
    pytest.param({"session_id": 1.5}, id="fractional"),
])
def test_an_unusable_session_id_never_reaches_the_signer(client, make_account, monkeypatch, body):
    owner = make_account()
    reached: List[str] = []
    monkeypatch.setattr(livekit_access, "mint_hr_room_access",
                        lambda *a, **k: reached.append("minted"))

    response = request_token(client, headers=owner.auth, body=body)

    assert response.status_code == 422, response.text
    assert reached == []


def test_clients_cannot_choose_their_identity_or_room(client, make_account, hr_session):
    owner = make_account()
    session = hr_session(owner.id)

    body = request_token(client, headers=owner.auth, body={
        "session_id": session.id,
        "identity": "admin",
        "room": "speakflow-hr-999-999",
        "room_name": "speakflow-hr-999-999",
        "user_id": 1,
        "can_publish_data": True,
        "can_publish_sources": ["screen_share"],
    }).json()
    claims = claims_of(body["token"])

    assert claims["sub"] == f"user-{owner.id}"
    assert claims["video"]["room"] == f"speakflow-hr-{session.id}-{owner.id}"
    assert claims["video"]["canPublishData"] is False
    assert claims["video"]["canPublishSources"] == ["microphone"]
    assert body["identity"] == f"user-{owner.id}"


# ---------------------------------------------------------------------------
# 3 — failure modes: unconfigured, missing SDK, signer failure
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("unset", ["livekit_api_key", "livekit_api_secret", "livekit_url"])
def test_missing_configuration_refuses_without_naming_a_value(client, make_account, hr_session,
                                                              monkeypatch, unset):
    monkeypatch.setattr(settings, unset, "")
    owner = make_account()
    session = hr_session(owner.id)

    response = request_token(client, headers=owner.auth, body={"session_id": session.id})

    assert response.status_code == 503, response.text
    assert response.json() == {"detail": NOT_CONFIGURED}
    assert API_SECRET not in response.text


def test_an_invalid_room_prefix_refuses_rather_than_joining_someone_elses_room(client,
                                                                              make_account,
                                                                              hr_session,
                                                                              monkeypatch):
    monkeypatch.setattr(settings, "livekit_room_prefix", "not a valid prefix")
    owner = make_account()
    session = hr_session(owner.id)

    response = request_token(client, headers=owner.auth, body={"session_id": session.id})

    assert response.status_code == 503, response.text
    assert response.json() == {"detail": NOT_CONFIGURED}


def test_a_server_without_the_sdk_refuses_instead_of_crashing(client, make_account, hr_session,
                                                              monkeypatch):
    """The SDK is imported at call time, so an environment that never installed it still answers."""
    owner = make_account()
    session = hr_session(owner.id)
    real_import = builtins.__import__

    def _blocked(name, *args, **kwargs):
        if str(name).startswith("livekit"):
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    for module in [m for m in list(sys.modules) if m.startswith("livekit")]:
        monkeypatch.delitem(sys.modules, module)
    monkeypatch.setattr(builtins, "__import__", _blocked)

    response = request_token(client, headers=owner.auth, body={"session_id": session.id})

    assert response.status_code == 503, response.text
    assert response.json() == {"detail": NOT_CONFIGURED}


def test_a_signing_fault_is_503_not_500_and_says_nothing_about_itself(client, make_account,
                                                                     hr_session, monkeypatch):
    owner = make_account()
    session = hr_session(owner.id)

    def _signing_explodes(*args, **kwargs):
        raise livekit_access.LiveKitTokenError("RuntimeError")

    monkeypatch.setattr(livekit_access, "mint_hr_room_access", _signing_explodes)

    response = request_token(client, headers=owner.auth, body={"session_id": session.id})

    assert response.status_code == 503, response.text
    assert response.json() == {"detail": SIGNING_FAILED}
    assert "RuntimeError" not in response.text


def test_an_unexpected_fault_inside_the_service_is_not_swallowed(client, make_account,
                                                                 hr_session, monkeypatch):
    """Only the two named LiveKit faults become 503; a real bug still surfaces as a 500."""
    owner = make_account()
    session = hr_session(owner.id)

    def _bug(*args, **kwargs):
        raise ZeroDivisionError("a genuine defect, not a configuration problem")

    monkeypatch.setattr(livekit_access, "mint_hr_room_access", _bug)

    with pytest.raises(ZeroDivisionError):
        request_token(client, headers=owner.auth, body={"session_id": session.id})


def test_neither_the_secret_nor_a_token_is_ever_logged(client, make_account, hr_session, caplog):
    owner = make_account()
    session = hr_session(owner.id)

    with caplog.at_level("DEBUG"):
        body = request_token(client, headers=owner.auth,
                             body={"session_id": session.id}).json()

    logged = " ".join(record.getMessage() for record in caplog.records)
    assert API_SECRET not in logged
    assert body["token"] not in logged
    assert body["token"].split(".")[1] not in logged


# ---------------------------------------------------------------------------
# 4 — static guards over the new modules
# ---------------------------------------------------------------------------
def test_the_handler_binds_authentication_and_proves_ownership_before_signing():
    source = route_source("livekit.py")
    deps = depends_names(ast.parse(source), "issue_room_token")

    assert {"get_current_user", "get_db"} <= deps

    handler = source[source.index("def issue_room_token"):]
    assert handler.index("owned_round_session") < handler.index("mint_hr_room_access")
    assert 'round_type="hr"' in source


def test_neither_new_module_imports_the_sdk_at_module_scope():
    """An environment without livekit-api must still import config, routes and services.

    `imported_modules` walks the whole tree, so it cannot tell a module-scope import from a
    call-time one; these are the top-level statements only, which is the thing that decides
    whether the app boots.
    """
    assert [name for name in module_scope_imports(route_source("livekit.py"))
            if name.startswith("livekit")] == []

    service = (SERVICES_DIR / "livekit_access.py").read_text(encoding="utf-8")
    assert [name for name in module_scope_imports(service) if name.startswith("livekit")] == []
    # ...and it is imported where it is needed, which is what makes the 503 path reachable.
    assert "from livekit.api import AccessToken, VideoGrants" in service


def module_scope_imports(source: str) -> List[str]:
    """Names imported at the top level of a module — the imports that run on `import app`."""
    found: List[str] = []
    for node in ast.parse(source).body:
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.append(node.module)
    return found


def test_the_route_is_mounted_once_under_its_own_prefix():
    main_source = (BACKEND_DIR / "main.py").read_text(encoding="utf-8")
    assert main_source.count("livekit.router") == 1
    assert "app.include_router(livekit.router)" in main_source

    source = route_source("livekit.py")
    assert 'prefix="/api/livekit"' in source
