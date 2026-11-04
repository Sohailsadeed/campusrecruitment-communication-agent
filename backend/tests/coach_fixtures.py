"""AUTH-B fixtures: the coach router alone, the curriculum agent stubbed, every row inside
the temp envelope conftest.py exported.

Nothing here imports main.py, so no startup DDL, ALTER TABLE, HR seed, rotating log handler or
emotion-model warm-up can run. The agent stub is installed by an autouse fixture, so no test can
reach a billed OpenRouter call even by accident.

The guest-pool defect keys on the *literal* user id 1, so accounts here can be created with an
explicit id; relying on insertion order would make the security tests depend on engine behaviour.
"""
from __future__ import annotations

import ast
import inspect
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from conftest import BACKEND_DIR, TEMP_ROOT

from app.database.engine import get_db
from app.models.coach import CurriculumPlan
from app.models.session import Session as SessionModel
from app.models.user import User
from app.routes import coach as coach_module
from app.routes.auth import create_access_token
from config import settings

ROUTES_DIR = BACKEND_DIR / "app" / "routes"

# The pre-existing denial body, kept uniform so a foreign or NULL-owned plan is indistinguishable
# from an absent one (coach.py:193 before AUTH-B).
PLAN_NOT_FOUND = "Curriculum plan not found"
# AUTH-A's uniform 401 body; the coach inherits it by reusing get_current_user.
UNAUTHENTICATED = "Could not validate credentials"

GUEST_ID = 1
VICTIM_ID = 2
CALLER_ID = 3

BASE_TIME = datetime(2026, 10, 20, 9, 0, 0)


@dataclass(frozen=True)
class Account:
    id: int
    email: str
    token: str

    @property
    def auth(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}


@dataclass
class AgentStub:
    """Records what the route passed to the agent, and proves the real agent was swapped out."""

    calls: List[Dict[str, Any]] = field(default_factory=list)
    real: Any = None

    @property
    def count(self) -> int:
        return len(self.calls)


def expired_token(subject: str) -> str:
    from jose import jwt

    payload = {"sub": subject, "exp": datetime.now(timezone.utc) - timedelta(days=1)}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def token_signed_elsewhere(subject: str) -> str:
    from jose import jwt

    payload = {"sub": subject, "exp": datetime.now(timezone.utc) + timedelta(hours=1)}
    return jwt.encode(payload, "a-different-secret", algorithm=settings.algorithm)


BAD_AUTH_HEADERS: List[Any] = [
    pytest.param(None, id="no-authorization-header"),
    pytest.param("Bearer ", id="bearer-without-token"),
    pytest.param("Bearer not.a.real.jwt", id="malformed-token"),
    pytest.param("Basic dXNlcjpwYXNz", id="non-bearer-scheme"),
]


def route_calls(name: str, plan_id: int = 1) -> tuple[str, str, Optional[Dict[str, Any]]]:
    """The four coach endpoints as (method, path, json body)."""
    if name == "active-plan":
        return ("get", "/api/coach/active-plan", None)
    if name == "generate-plan":
        return ("post", "/api/coach/generate-plan", {"target_role": "General Placement"})
    if name == "complete-day":
        return ("post", "/api/coach/complete-day", {"plan_id": plan_id, "day_number": 1})
    if name == "auto-sync":
        return ("post", "/api/coach/auto-sync", None)
    raise AssertionError(f"unknown coach route {name!r}")


COACH_ROUTES = ("active-plan", "generate-plan", "complete-day", "auto-sync")


def call_route(client: TestClient, name: str, headers: Optional[Dict[str, str]], plan_id: int = 1):
    method, path, body = route_calls(name, plan_id)
    if method == "get":
        return client.get(path, headers=headers)
    return client.post(path, json=body, headers=headers)


def day(
    number: int,
    round_type: str = "jam",
    status: str = "pending",
    *,
    score: Optional[float] = None,
    completed_at: Optional[str] = None,
) -> Dict[str, Any]:
    """One curriculum day, shaped exactly like the agent's contract (coach.py, types/coach.ts)."""
    route = "/record" if round_type == "jam" else f"/{round_type}"
    return {
        "day_number": number,
        "title": f"Day {number}: {round_type} drill",
        "round_type": round_type,
        "drill_route": route,
        "drill_params": {"difficulty": "Intermediate"},
        "focus_dimension": "Clarity & Delivery",
        "pedagogical_rationale": "Fixture rationale.",
        "target_metric_goal": ">= 80",
        "status": status,
        "completed_at": completed_at,
        "score_achieved": score,
    }


def week(active_day_number: int = 1, round_type: str = "jam") -> List[Dict[str, Any]]:
    """Seven days; `active_day_number` is in_progress, earlier days completed, later ones pending."""
    days: List[Dict[str, Any]] = []
    for n in range(1, 8):
        if n < active_day_number:
            days.append(day(n, round_type, "completed", score=81.0, completed_at=BASE_TIME.isoformat()))
        elif n == active_day_number:
            days.append(day(n, round_type, "in_progress"))
        else:
            days.append(day(n, round_type, "pending"))
    return days


AGENT_RESULT: Dict[str, Any] = {
    "plan": {
        "roadmap_title": "7-Day Placement Acceleration Roadmap: Stub",
        "focus_areas": ["Clarity & Delivery", "MECE structure"],
        "days": week(active_day_number=1),
    },
    "bottlenecks": [
        {
            "dimension": "Consulting Sizing Baseline",
            "round": "guesstimate",
            "severity": "high",
            "reason": "Zero guesstimate drills completed.",
            "target_metric": "Complete 1 market sizing case",
        }
    ],
    "history_summary": {
        "jam": {"completed_count": 3},
        "technical": {"completed_count": 1},
        "guesstimate": {"completed_count": 0},
        "hr": {"completed_count": 2},
    },
}


@pytest.fixture(autouse=True)
def stubbed_agent(monkeypatch) -> AgentStub:
    """Replace the agent *at the attribute coach.py actually calls* for every test in the module.

    coach.py:19 imports the symbol into its own namespace, so patching the service module would
    leave the route calling the real LangGraph agent — and a billed OpenRouter request.
    """
    stub = AgentStub(real=coach_module.generate_curriculum_plan)

    async def _fake(*, user_id: int, target_role: str) -> Dict[str, Any]:
        stub.calls.append({"user_id": user_id, "target_role": target_role})
        plan = json.loads(json.dumps(AGENT_RESULT["plan"]))
        return {
            "plan": plan,
            "bottlenecks": json.loads(json.dumps(AGENT_RESULT["bottlenecks"])),
            "history_summary": json.loads(json.dumps(AGENT_RESULT["history_summary"])),
        }

    monkeypatch.setattr(coach_module, "generate_curriculum_plan", _fake)
    return stub


@pytest.fixture()
def coach_app(db_session) -> TestClient:
    application = FastAPI()
    application.include_router(coach_module.router)

    def _override():
        yield db_session

    application.dependency_overrides[get_db] = _override
    with TestClient(application) as client:
        yield client


@pytest.fixture()
def make_account(db_session):
    counter = {"n": 0}

    def _make(email: Optional[str] = None, user_id: Optional[int] = None) -> Account:
        counter["n"] += 1
        name = f"coach-user-{counter['n']}"
        address = email or f"{name}@coach.test"
        kwargs: Dict[str, Any] = {
            "email": address,
            "username": name,
            "hashed_password": "not-a-real-hash",
        }
        if user_id is not None:
            kwargs["id"] = user_id
        user = User(**kwargs)
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
        return Account(id=user.id, email=user.email, token=create_access_token(user.email))

    return _make


@pytest.fixture()
def make_plan(db_session):
    def _make(
        owner_id: Optional[int],
        *,
        status: str = "active",
        days: Optional[List[Dict[str, Any]]] = None,
        target_role: str = "General Placement",
        created_at: Optional[datetime] = None,
    ) -> CurriculumPlan:
        plan = CurriculumPlan(
            user_id=owner_id,
            target_role=target_role,
            roadmap_title=f"7-Day Roadmap ({status})",
            status=status,
            target_date="2026-12-01",
            identified_bottlenecks=list(AGENT_RESULT["bottlenecks"]),
            days=week() if days is None else days,
            meta_summary={"focus_areas": ["Clarity & Delivery"]},
            created_at=created_at or BASE_TIME,
        )
        db_session.add(plan)
        db_session.commit()
        db_session.refresh(plan)
        return plan

    return _make


@pytest.fixture()
def make_session(db_session):
    def _make(
        owner_id: Optional[int],
        *,
        round_type: str = "jam",
        score: Optional[float] = 88.0,
        status: str = "completed",
        created_at: Optional[datetime] = None,
        title: str = "AUTH-B fixture session",
    ) -> SessionModel:
        session = SessionModel(
            user_id=owner_id,
            title=title,
            duration_seconds=60.0,
            status=status,
            round_type=round_type,
            overall_score=score,
            round_metadata={},
            created_at=created_at or (BASE_TIME + timedelta(minutes=30)),
        )
        db_session.add(session)
        db_session.commit()
        db_session.refresh(session)
        return session

    return _make


def read_plan(db, plan_id: int) -> Dict[str, Any]:
    """The plan exactly as the database holds it, after expiring the identity map."""
    db.expire_all()
    plan = db.get(CurriculumPlan, plan_id)
    if plan is None:
        raise AssertionError(f"plan {plan_id} vanished from the database")
    return {
        "user_id": plan.user_id,
        "status": plan.status,
        "days": json.loads(json.dumps(plan.days)),
        "updated_at": plan.updated_at.isoformat(),
    }


def coach_source(filename: str) -> str:
    return (ROUTES_DIR / filename).read_text(encoding="utf-8")


def agent_source() -> str:
    return (
        BACKEND_DIR / "app" / "services" / "coach" / "curriculum_agent.py"
    ).read_text(encoding="utf-8")


def _depends_names(tree: ast.Module, handler: str) -> set[str]:
    """Names bound through Depends(...) in a top-level handler's default arguments."""
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or node.name != handler:
            continue
        found: set[str] = set()
        defaults = [*node.args.defaults, *(kw.value for kw in node.args.kw_defaults if kw)]
        for default in defaults:
            if (
                isinstance(default, ast.Call)
                and isinstance(default.func, ast.Name)
                and default.func.id == "Depends"
                and default.args
                and isinstance(default.args[0], ast.Name)
            ):
                found.add(default.args[0].id)
        return found
    raise AssertionError(f"handler {handler} no longer exists")


def coach_tree() -> ast.Module:
    return ast.parse(coach_source("coach.py"))


def envelope_isolated() -> None:
    """Every stateful target must resolve inside the temp dir; the live Postgres must be unused."""
    url = str(settings.database_url)
    if not url.startswith("sqlite"):
        raise AssertionError(f"coach tests must not bind a real server: {url.split('://')[0]}")
    temp_root = str(TEMP_ROOT.resolve())
    for label, value in (("DATABASE_URL", url), ("UPLOAD_DIR", str(settings.upload_dir)), ("LOGS_DIR", str(settings.logs_dir))):
        if temp_root not in str(Path(value).resolve() if not value.startswith("sqlite") else value):
            raise AssertionError(f"AUTH-B isolation tripwire: {label} left the envelope: {value}")


def agent_signature_has_no_identity_default() -> bool:
    """generate_curriculum_plan must not carry a default identity at all."""
    from app.services.coach.curriculum_agent import generate_curriculum_plan

    parameter = inspect.signature(generate_curriculum_plan).parameters.get("user_id")
    return parameter is not None and parameter.default is inspect.Parameter.empty
