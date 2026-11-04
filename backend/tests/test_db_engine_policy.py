"""ENV-2: fail-closed database initialization.

Proves that the configured database URL is the only datastore the process can bind, that a
PostgreSQL connectivity failure aborts initialization instead of substituting SQLite, and that
neither logs nor public errors carry connection credentials.

No live PostgreSQL, Redis or network contact: engine construction and connectivity probing are
replaced by recorded fakes, and every real database used here is a temporary SQLite file.
"""
from __future__ import annotations

import ast
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pytest
import sqlalchemy as sa
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session as OrmSession

import app.database.engine  # noqa: F401  (populates sys.modules for the handle below)
import app.models  # noqa: F401  (registers every table on Base.metadata)
from app.models.user import User
from app.routes.auth import get_current_user
from config import settings

# app/database/__init__.py re-exports the Engine object under the name "engine", which shadows the
# submodule attribute, so `app.database.engine` as an attribute is the Engine, not the module.
dbm = sys.modules["app.database.engine"]

ENGINE_PATH = Path(dbm.__file__).resolve()

SENTINEL_PASSWORD = "s3cr3t-pg"
SENTINEL_USER = "alice"
SENTINEL_HOST = "db.internal.invalid"
SENTINEL_PORT = "5544"
SENTINEL_DB = "speakflow_testdb"

PG_SENTINEL = (
    f"postgresql+psycopg2://{SENTINEL_USER}:{SENTINEL_PASSWORD}@{SENTINEL_HOST}:"
    f"{SENTINEL_PORT}/{SENTINEL_DB}?keepalives=1&sslmode=require"
)
SENSITIVE_TOKENS = (SENTINEL_PASSWORD, SENTINEL_USER, SENTINEL_HOST, SENTINEL_PORT, SENTINEL_DB)


# ---------------------------------------------------------------------------
# Recorded fakes
# ---------------------------------------------------------------------------
class _FakeEngine:
    """Stands in for a real Engine; connect() behaviour is armed per test."""

    def __init__(self, url: str, kwargs: Dict[str, Any], *, fail: bool = False) -> None:
        self.url = url
        self.kwargs = kwargs
        self.fail = fail
        self.connect_calls = 0
        self._parent: "_FakeFactory" = None  # type: ignore[assignment]

    def connect(self):
        self.connect_calls += 1
        if self._parent is not None:
            self._parent.connect_calls += 1
        if self.fail:
            raise OperationalError("injected connectivity fault", None, None)

        class _Conn:
            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *exc_info):
                return False

        return _Conn()


class _FakeFactory:
    """Replaces create_engine and records every construction attempt."""

    def __init__(self, *, fail_postgres: bool = False) -> None:
        self.constructions: List[Tuple[str, Dict[str, Any]]] = []
        self.engines: List[_FakeEngine] = []
        self.connect_calls = 0
        self.fail_postgres = fail_postgres

    def __call__(self, url: str, **kwargs):
        self.constructions.append((url, kwargs))
        fail = self.fail_postgres and str(url).startswith("postgresql")
        engine = _FakeEngine(url, kwargs, fail=fail)
        engine._parent = self
        self.engines.append(engine)
        return engine

    @property
    def backends(self) -> List[str]:
        return ["sqlite" if str(u).startswith("sqlite") else "postgresql"
                for u, _ in self.constructions]


@pytest.fixture()
def arm(monkeypatch):
    """Patch create_engine inside the engine module; nothing is ever connected to."""
    def _arm(**factory_kwargs) -> _FakeFactory:
        factory = _FakeFactory(**factory_kwargs)
        monkeypatch.setattr(dbm, "create_engine", factory)
        return factory

    return _arm


# ---------------------------------------------------------------------------
# E1 / E11 — resolution never rewrites the configured URL
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "url",
    [
        PG_SENTINEL,
        "postgresql://user:pw@localhost:5432/app",
        "postgresql+psycopg://user:pw@localhost:5432/app",
    ],
    ids=["sentinel-psycopg2", "bare-postgresql", "psycopg3"],
)
def test_E1_valid_postgresql_url_is_accepted_and_returned_unchanged(url, arm):
    factory = arm()
    assert dbm.resolve_database_url(url) == url
    assert factory.constructions == [], "resolution must not construct an engine"


def test_E11_resolution_does_not_construct_or_rewrite_any_engine(arm):
    factory = arm()
    url = PG_SENTINEL
    resolved = dbm.resolve_database_url(url)
    assert resolved == url
    assert f":{SENTINEL_PASSWORD}@" in resolved, "credentials must survive untouched, not be stripped"
    assert resolved.split("://")[0] == "postgresql+psycopg2"
    assert factory.constructions == []
    assert factory.connect_calls == 0


# ---------------------------------------------------------------------------
# E2 — approved synchronous PostgreSQL drivers
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "driver",
    ["", "psycopg", "psycopg2", "psycopg2cffi", "pg8000"],
    ids=["default", "psycopg", "psycopg2", "psycopg2cffi", "pg8000"],
)
def test_E2_approved_synchronous_postgresql_drivers_are_accepted(driver, arm):
    scheme = "postgresql" if not driver else f"postgresql+{driver}"
    url = f"{scheme}://user:pw@localhost:5432/app"
    assert dbm.resolve_database_url(url) == url


# ---------------------------------------------------------------------------
# E3 — unsupported backends and asynchronous drivers
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "url",
    [
        "mysql://user:pw@localhost:3306/app",
        "postgres://user:pw@localhost:5432/app",
        "sqlite+aiosqlite:///app.db",
        "oracle://user:pw@localhost:1521/app",
        "",
        "not a url at all",
    ],
    ids=["mysql", "legacy-postgres-alias", "aiosqlite", "oracle", "empty", "unparseable"],
)
def test_E3_unsupported_backends_are_rejected(url, arm):
    factory = arm()
    with pytest.raises(dbm.DatabaseConfigurationError):
        dbm.resolve_database_url(url)
    assert factory.constructions == []


def test_E3_asyncpg_driver_is_rejected_for_the_synchronous_sessionmaker(arm):
    url = "postgresql+asyncpg://user:pw@localhost:5432/app"
    with pytest.raises(dbm.DatabaseConfigurationError) as raised:
        dbm.resolve_database_url(url)
    assert "asyncpg" in str(raised.value)
    assert "pw" not in str(raised.value)


def test_E3_configuration_error_carries_no_connection_details(arm):
    with pytest.raises(dbm.DatabaseConfigurationError) as raised:
        dbm.resolve_database_url(PG_SENTINEL.replace("postgresql+psycopg2", "firebird"))
    text = str(raised.value) + repr(raised.value)
    for token in SENSITIVE_TOKENS:
        assert token not in text


# ---------------------------------------------------------------------------
# E4 — explicitly configured SQLite stays supported
# ---------------------------------------------------------------------------
def test_E4_explicit_sqlite_configuration_is_accepted(tmp_path, arm):
    url = f"sqlite:///{(tmp_path / 'explicit_policy.db').as_posix()}"
    assert dbm.resolve_database_url(url) == url
    factory = arm()
    engine = dbm.build_engine(url)
    assert engine is not None
    assert factory.constructions == [(url, {"connect_args": {"check_same_thread": False}})]


# ---------------------------------------------------------------------------
# E5 — build_engine constructs exactly one engine and performs no I/O
# ---------------------------------------------------------------------------
def test_E5_build_engine_creates_one_engine_without_connecting(arm):
    factory = arm()
    dbm.build_engine(PG_SENTINEL)
    assert len(factory.constructions) == 1
    assert factory.constructions[0][0] == PG_SENTINEL
    assert factory.constructions[0][1] == {"connect_args": {"connect_timeout": 3}}
    assert factory.connect_calls == 0


def test_E5_build_engine_executes_no_ddl_and_creates_no_file(tmp_path):
    path = tmp_path / "lazily_built.db"
    engine = dbm.build_engine(f"sqlite:///{path.as_posix()}")
    assert engine is not None
    assert not path.exists(), "create_engine must stay lazy; no connection, no DDL, no file"
    engine.dispose()


def test_E5_build_engine_rejects_an_unvalidated_url_without_substitution(arm):
    factory = arm()
    with pytest.raises(dbm.DatabaseConfigurationError):
        dbm.build_engine("mysql://user:pw@localhost:3306/app")
    assert factory.constructions == []


# ---------------------------------------------------------------------------
# E6 — verify_connectivity propagates the injected failure untouched
# ---------------------------------------------------------------------------
def test_E6_verify_connectivity_propagates_the_original_injected_failure(arm):
    factory = arm()
    engine = _FakeEngine(PG_SENTINEL, {}, fail=True)
    engine._parent = factory
    with pytest.raises(OperationalError):
        dbm.verify_connectivity(engine)
    assert engine.connect_calls == 1
    assert factory.constructions == []


def test_E6_verify_connectivity_is_a_bounded_probe_and_builds_nothing(arm):
    factory = arm()
    engine = _FakeEngine(PG_SENTINEL, {})
    engine._parent = factory
    assert dbm.verify_connectivity(engine) is None
    assert engine.connect_calls == 1
    assert factory.constructions == []


# ---------------------------------------------------------------------------
# E7 / E8 — the core ENV-2 guarantee: no substitution, no rebind
# ---------------------------------------------------------------------------
def test_E7_postgresql_failure_does_not_construct_a_replacement_engine(arm):
    factory = arm(fail_postgres=True)
    with pytest.raises(dbm.DatabaseConnectionError):
        dbm.init_database(PG_SENTINEL)
    assert [u for u, _ in factory.constructions] == [PG_SENTINEL], (
        f"expected exactly the configured engine, got {factory.constructions}")
    assert "sqlite" not in factory.backends, "ENV-2: a SQLite substitute was built after a PostgreSQL failure"


def test_E8_every_construction_is_accounted_for_and_none_is_a_substitute(arm):
    factory = arm(fail_postgres=True)
    before_engine, before_factory = dbm.engine, dbm.SessionLocal
    with pytest.raises(dbm.DatabaseConnectionError) as raised:
        dbm.init_database(PG_SENTINEL)

    assert len(factory.constructions) == 1, "a second engine was constructed"
    assert not any(str(u).startswith("sqlite") for u, _ in factory.constructions)
    assert dbm.engine is before_engine, "the module-global engine was rebound"
    assert dbm.SessionLocal is before_factory, "SessionLocal was rebound"
    assert dbm.SessionLocal.kw["bind"] is dbm.engine
    assert raised.value.__cause__ is None
    assert raised.value.__suppress_context__ is True


def test_E7_success_returns_the_verified_configured_engine(arm):
    factory = arm()
    engine = dbm.init_database(PG_SENTINEL)
    assert engine is factory.engines[0]
    assert [u for u, _ in factory.constructions] == [PG_SENTINEL]
    assert engine.connect_calls == 1, "a successful init must have verified connectivity"


# ---------------------------------------------------------------------------
# E9 — SessionLocal is bound to the authoritative engine
# ---------------------------------------------------------------------------
def test_E9_sessionlocal_is_bound_to_the_authoritative_engine():
    assert dbm.SessionLocal.kw["bind"] is dbm.engine
    assert str(dbm.engine.url).startswith(str(settings.database_url).split("://")[0])
    assert dbm.engine.url.get_backend_name() == sa.make_url(settings.database_url).get_backend_name()
    assert dbm.SessionLocal.kw["autoflush"] is False and dbm.SessionLocal.kw["autocommit"] is False


# ---------------------------------------------------------------------------
# E10 — credentials never reach logs or public errors
# ---------------------------------------------------------------------------
def test_E10_credentials_never_appear_in_logs_or_public_errors(arm, caplog):
    factory = arm(fail_postgres=True)

    with caplog.at_level(logging.DEBUG, logger="speakflow.db"):
        with pytest.raises(dbm.DatabaseConnectionError) as raised:
            dbm.init_database(PG_SENTINEL)

    public = str(raised.value) + repr(raised.value)
    for token in SENSITIVE_TOKENS:
        assert token not in public, f"public error leaked {token!r}"
    assert raised.value.__cause__ is None
    assert public.strip(), "the public error must still say something useful"

    assert caplog.records, "no startup diagnostic was emitted at all"
    logged = "\n".join(rec.getMessage() for rec in caplog.records)
    for token in SENSITIVE_TOKENS:
        assert token not in logged, f"startup log leaked {token!r}"
    assert "DATABASE_URL" not in logged
    assert factory.constructions == [(PG_SENTINEL, {"connect_args": {"connect_timeout": 3}})]


def test_E10_connection_error_exposes_only_class_and_backend_tokens(arm, caplog):
    arm(fail_postgres=True)
    caplog.set_level(logging.DEBUG, logger="speakflow.db")
    with pytest.raises(dbm.DatabaseConnectionError) as raised:
        dbm.init_database(PG_SENTINEL)
    err = raised.value
    assert getattr(err, "backend", None) == "postgresql"
    assert getattr(err, "cause_class", None) == "OperationalError"
    assert str(err) == "configured database is unreachable"


# ---------------------------------------------------------------------------
# E12 — structural guard against re-introducing the fallback
# ---------------------------------------------------------------------------
LOGGING_CHANNEL = "speakflow.db"

# Verbatim shape of the pre-ENV-2 defect. The guards below must report it as an offender; if a
# guard ever stops firing on this source it no longer protects anything.
LEGACY_FALLBACK_SOURCE = '''
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger("speakflow.db")

try:
    engine = create_engine(database_url, connect_args={})
except Exception as _exc:
    logger.warning("falling back (%s)", _exc)
    sqlite_path = settings.upload_dir.parent / "speakflow.db"
    database_url = f"sqlite:///{sqlite_path}"
    engine = create_engine(database_url, connect_args={})

SessionLocal = sessionmaker(bind=engine)
'''


def _source() -> str:
    return ENGINE_PATH.read_text(encoding="utf-8")


def _tree(source: str) -> ast.Module:
    return ast.parse(source)


def _engines_built_in_handlers(tree: ast.Module) -> List[str]:
    offenders: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            for inner in ast.walk(node):
                if isinstance(inner, ast.Call):
                    func = inner.func
                    name = getattr(func, "id", None) or getattr(func, "attr", None)
                    if name in {"create_engine", "init_database", "build_engine"}:
                        offenders.append(f"{name} at line {inner.lineno}")
    return offenders


def _fallback_literals(tree: ast.Module) -> List[str]:
    """String literals that name a fallback database, excluding getLogger() channel arguments."""
    exempt = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "attr", None) == "getLogger":
            exempt.update(id(arg) for arg in node.args)
    offenders: List[str] = []
    for node in ast.walk(tree):
        if id(node) in exempt or not isinstance(node, ast.Constant):
            continue
        value = node.value
        if isinstance(value, str) and ("speakflow.db" in value or "sqlite:///" in value):
            offenders.append(value)
    return offenders


def _sessionmaker_calls(tree: ast.Module) -> List[ast.Call]:
    return [node for node in ast.walk(tree)
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "sessionmaker"]


def _unsafe_logging_arguments(tree: ast.Module) -> List[str]:
    unsafe: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr in {"info", "warning", "error", "exception"}:
            for arg in [*node.args, *(kw.value for kw in node.keywords)]:
                rendered = ast.unparse(arg)
                leaks_exception = ("exc" in rendered and "cause_class" not in rendered
                                   and "cause=" not in rendered)
                leaks_url = "database_url" in rendered or ".url" in rendered
                if leaks_exception or leaks_url:
                    unsafe.append(rendered)
    return unsafe


def test_E12_guards_fire_on_the_original_fallback_source():
    tree = _tree(LEGACY_FALLBACK_SOURCE)
    assert _engines_built_in_handlers(tree), "the guard no longer detects construction in a handler"
    assert _fallback_literals(tree), "the guard no longer detects a hardcoded fallback database"
    assert _unsafe_logging_arguments(tree), "the guard no longer detects raw-exception logging"
    assert _sessionmaker_calls(_tree(_source())), "the guards have no reference implementation"


def test_E12_no_engine_is_constructed_inside_an_exception_handler():
    offenders = _engines_built_in_handlers(_tree(_source()))
    assert not offenders, f"fallback engine construction remains in an except handler: {offenders}"


def test_E12_no_hardcoded_sqlite_fallback_path():
    offenders = _fallback_literals(_tree(_source()))
    assert not offenders, f"hardcoded fallback database remains: {offenders}"


def test_E12_exactly_one_sessionmaker_bound_to_the_authoritative_engine():
    calls = _sessionmaker_calls(_tree(_source()))
    assert len(calls) == 1
    keywords = {kw.arg for kw in calls[0].keywords}
    assert "bind" in keywords


def test_E12_the_module_never_logs_a_raw_exception_object_or_url():
    unsafe = _unsafe_logging_arguments(_tree(_source()))
    assert not unsafe, f"logging call may leak an exception object or URL: {unsafe}"
    source = _source()
    assert "exc_info=True" not in source
    assert "logger.exception" not in source


# ---------------------------------------------------------------------------
# E13 — a database fault during authentication stays a server error
# ---------------------------------------------------------------------------
_ORIGINAL_SCALAR = OrmSession.scalar


class _Fault:
    """Holds the armed flag for the injected outage."""

    def __init__(self) -> None:
        self.armed = False


def _build_app(db_session) -> FastAPI:
    application = FastAPI()
    application.include_router(_auth_router())

    @application.get("/probe/current-user")
    def probe(current_user: User = Depends(get_current_user)) -> dict:
        return {"user_id": current_user.id}

    def _override():
        yield db_session

    application.dependency_overrides[dbm.get_db] = _override
    return application


def _auth_router():
    from app.routes import auth as auth_module

    return auth_module.router


@pytest.fixture()
def faulted(monkeypatch):
    """Arm an OperationalError on the ORM read path; the patch stays a plain function so descriptor binding still supplies the Session."""
    fault = _Fault()

    def _scalar(self, *args, **kwargs):
        if fault.armed:
            raise OperationalError("injected database outage", None, None)
        return _ORIGINAL_SCALAR(self, *args, **kwargs)

    monkeypatch.setattr(OrmSession, "scalar", _scalar)
    return fault


def _token_for(client: TestClient, email: str) -> str:
    response = client.post(
        "/api/auth/register",
        json={"email": email, "username": "env2", "password": "supersecret"},
    )
    assert response.status_code == 201, response.text
    return response.json()["access_token"]


def test_E13a_database_fault_during_authentication_surfaces_as_http_500(db_session, faulted):
    app = _build_app(db_session)
    with TestClient(app, raise_server_exceptions=False) as client:
        token = _token_for(client, "env2-500@ownership.test")
        faulted.armed = True
        response = client.get("/probe/current-user", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 500, (
        f"a database outage was reported as {response.status_code}: {response.text!r}")
    assert response.status_code != 401
    assert "Could not validate credentials" not in response.text
    assert response.status_code != 404


def test_E13b_the_same_database_fault_propagates_unchanged(db_session, faulted):
    app = _build_app(db_session)
    with TestClient(app) as client:
        token = _token_for(client, "env2-prop@ownership.test")
        faulted.armed = True
        with pytest.raises(OperationalError):
            client.get("/probe/current-user", headers={"Authorization": f"Bearer {token}"})


def test_E13_authentication_still_fails_closed_without_a_database_fault(db_session):
    app = _build_app(db_session)
    with TestClient(app) as client:
        response = client.get("/probe/current-user", headers={"Authorization": "Bearer nonsense"})
    assert response.status_code == 401
    assert response.json() == {"detail": "Could not validate credentials"}


# ---------------------------------------------------------------------------
# E14 — a real explicitly configured SQLite database remains usable
# ---------------------------------------------------------------------------
def test_E14_temporary_sqlite_remains_usable_through_the_full_lifecycle(tmp_path):
    path = tmp_path / "lifecycle.db"
    url = f"sqlite:///{path.as_posix()}"
    resolved = dbm.resolve_database_url(url)
    engine = dbm.init_database(resolved)
    try:
        dbm.Base.metadata.create_all(bind=engine)
        with OrmSession(bind=engine) as session:
            session.add(User(email="lifecycle@ownership.test", username="env2",
                             hashed_password="x"))
            session.commit()
            assert session.query(User).count() == 1
    finally:
        engine.dispose()
    assert path.exists()
