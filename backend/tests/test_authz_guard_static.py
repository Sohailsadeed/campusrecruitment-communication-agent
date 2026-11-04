"""AUTH-A static guards. Pure AST: imports nothing from the app, opens no database.

These tests fail the moment the fail-closed fix is widened, reverted, or bypassed by a
route dropping its identity dependency.
"""
from __future__ import annotations

import ast

import pytest
from conftest import BACKEND_DIR

ROUTES_DIR = BACKEND_DIR / "app" / "routes"

# The routers this guard covers. This used to be a per-file handler count, which went stale the day
# an authenticated route was added (the HR speech-trends route) -- a red test about a correct router.
# The guard is the property itself instead: a route handler without get_current_user is permitted
# only when it is named below, so a new unauthenticated route cannot appear without a decision.
ROUTERS_WITH_OWNERSHIP = ("hr.py", "guesstimate.py", "technical.py")

# Round content is public: static track lists and curated question text describe the exercise, not a
# candidate, so these four have never required an identity and are not gaps.
PUBLIC_METADATA_ROUTES = {
    "hr.py": {"get_behavioral_tracks", "get_behavioral_questions"},
    "guesstimate.py": {"get_guesstimate_metadata", "get_random_guesstimate"},
    "technical.py": {"get_resume_status"},  # optional auth: a guest is told only has_resume: false
}

# The inventory of known unauthenticated media routes. It is empty, and that is the finding:
# technical.py used to stream candidate recordings to whoever could name the file while its HR and
# Guesstimate equivalents were authenticated under Decision B below. The route now binds an
# identity and delegates to the same ownership resolver, so the entry is gone rather than reworded.
# Any future entry here must be a deliberate, documented gap, not a route someone forgot about.
UNAUTHENTICATED_MEDIA_ROUTES: dict[str, set[str]] = {}

# Decision B: these must never lose authentication in favour of playback convenience.
MEDIA_ELEMENT_ROUTES = {
    "hr.py": "serve_hr_audio",
    "guesstimate.py": "serve_guesstimate_audio",
    "technical.py": "serve_technical_audio",
}


def _module(filename: str) -> ast.Module:
    return ast.parse((ROUTES_DIR / filename).read_text(encoding="utf-8"))


def _function(tree: ast.Module, name: str) -> ast.FunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"{name} no longer exists")


def _module_constant(tree: ast.Module, name: str) -> ast.expr:
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name for target in node.targets
        ):
            return node.value
    raise AssertionError(f"module-level {name} no longer exists")


def _depends_target(default: ast.expr) -> str | None:
    if isinstance(default, ast.Call) and isinstance(default.func, ast.Name):
        if default.func.id == "Depends" and default.args:
            first = default.args[0]
            if isinstance(first, ast.Name):
                return first.id
    return None


def _is_route_decorator(node: ast.expr) -> bool:
    """True for `@router.get(...)` / `@router.post(...)`, the way these routers declare a route."""
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name) and node.func.value.id == "router")


def _router_handlers(tree: ast.Module) -> set[str]:
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and any(_is_route_decorator(dec) for dec in node.decorator_list)
    }


def _handlers_bound_to(tree: ast.Module, resolver: str) -> list[str]:
    bound = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not node.decorator_list:
            continue
        defaults = [*node.args.defaults, *(kw.value for kw in node.args.kw_defaults if kw)]
        if any(_depends_target(default) == resolver for default in defaults):
            bound.append(node.name)
    return bound


def test_get_current_user_never_constructs_a_user():
    body = _function(_module("auth.py"), "get_current_user")
    constructed = [
        call.func.id
        for call in ast.walk(body)
        if isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
    ]
    assert "User" not in constructed


@pytest.mark.parametrize("mutation", ["add", "commit", "flush", "refresh"])
def test_get_current_user_never_touches_the_session_writer_api(mutation: str):
    body = _function(_module("auth.py"), "get_current_user")
    attributes = {
        call.func.attr
        for call in ast.walk(body)
        if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
    }
    assert mutation not in attributes


def test_get_current_user_raises_only_the_single_401_helper():
    body = _function(_module("auth.py"), "get_current_user")
    raises = [node for node in ast.walk(body) if isinstance(node, ast.Raise)]
    assert raises, "fail-closed resolver must raise"
    for node in raises:
        assert isinstance(node.exc, ast.Call), "raise must call the 401 helper"
        assert isinstance(node.exc.func, ast.Name)
        assert node.exc.func.id == "_unauthenticated"
        assert node.exc.args == [], "the 401 payload must stay uniform"
        assert node.exc.keywords == []


def test_unauthenticated_helper_builds_a_fresh_exception_with_the_bearer_challenge():
    tree = _module("auth.py")
    helper = _function(tree, "_unauthenticated")

    # A shared exception instance would leak another request's traceback; the helper must
    # construct a new HTTPException on every call.
    returns = [node for node in ast.walk(helper) if isinstance(node, ast.Return)]
    assert len(returns) == 1, "must construct a new HTTPException per call, not return a shared one"
    built = returns[0].value
    assert isinstance(built, ast.Call) and isinstance(built.func, ast.Name)
    assert built.func.id == "HTTPException"
    keywords = {kw.arg for kw in built.keywords}
    assert {"status_code", "detail", "headers"} <= keywords

    source = ast.dump(built)
    assert "HTTP_401_UNAUTHORIZED" in source or "401" in source

    # The header name lives in the module-level constant, so assert it there and prove the
    # helper reads that constant rather than inventing its own challenge.
    challenge = _module_constant(tree, "_WWW_AUTHENTICATE")
    assert "WWW-Authenticate" in ast.dump(challenge)
    assert "Bearer" in ast.dump(challenge)
    referenced = {
        node.id
        for node in ast.walk(helper)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
    }
    assert "_WWW_AUTHENTICATE" in referenced


def test_optional_resolver_is_still_permissive_and_untouched_by_auth_a():
    """AUTH-A left `get_optional_current_user` deliberately permissive for non-owning routes.

    AUTH-C (Q1 amendment) removed the sessions-router clone `_get_optional_user`, so this guard
    covers the shared resolver only; AUTH-C's own suite asserts the retired name is gone.
    """
    auth_tree = _module("auth.py")
    optional = _function(auth_tree, "get_optional_current_user")
    assert any(
        isinstance(node, ast.Return) and isinstance(node.value, ast.Constant) and node.value.value is None
        for node in ast.walk(optional)
    )


@pytest.mark.parametrize("filename", sorted(ROUTERS_WITH_OWNERSHIP))
def test_round_routers_keep_binding_get_current_user(filename: str):
    tree = _module(filename)
    bound = set(_handlers_bound_to(tree, "get_current_user"))
    unbound = _router_handlers(tree) - bound
    allowed = PUBLIC_METADATA_ROUTES.get(filename, set()) | UNAUTHENTICATED_MEDIA_ROUTES.get(filename, set())
    assert unbound - allowed == set(), (
        f"{filename} gained a route with no identity dependency: {sorted(unbound - allowed)}")
    assert allowed - unbound == set(), (
        f"{filename}: routes listed as unauthenticated are now bound -- retire the entry: "
        f"{sorted(allowed - unbound)}")
    assert bound, f"{filename} binds no handler at all"


def test_the_technical_audio_route_is_authenticated_and_uses_the_shared_resolver():
    """The security property, not a route count: no unauthenticated path to a recording is left.

    The tripwire that used to sit here recorded the gap until it could be fixed. It is fixed, so
    this asserts the opposite -- an identity dependency, the AUTH-E ownership resolver, and the
    open-finding inventory back to empty.
    """
    tree = _module("technical.py")
    assert _router_handlers(tree) - set(_handlers_bound_to(tree, "get_current_user")) == (
        PUBLIC_METADATA_ROUTES["technical.py"])

    handler = _function(tree, "serve_technical_audio")
    body = ast.get_source_segment((ROUTES_DIR / "technical.py").read_text(encoding="utf-8"), handler)
    assert body is not None
    assert "resolve_technical_audio_path" in body, "authorization must run before any file is opened"
    assert "FileResponse(" not in body, "the shared response builder is the only way to serve a clip"
    defaults = [*handler.args.defaults, *(kw.value for kw in handler.args.kw_defaults if kw)]
    resolvers = [name for name in (_depends_target(default) for default in defaults) if name]
    assert resolvers == ["get_current_user", "get_db"], (
        f"serve_technical_audio binds {resolvers}; the requester and their session must both "
        "come from request-scoped plumbing")
    assert UNAUTHENTICATED_MEDIA_ROUTES == {}


@pytest.mark.parametrize("filename,handler", sorted(MEDIA_ELEMENT_ROUTES.items()))
def test_media_element_audio_routes_stay_authenticated(filename: str, handler: str):
    bound = _handlers_bound_to(_module(filename), "get_current_user")
    assert handler in bound, f"{handler} lost its identity dependency"


# AUTH-D closed this hole; the guard now requires the opposite of what it once recorded, so the
# fix cannot silently regress back to the state this tripwire tolerated.
AUTHD_SECURED_HANDLERS = {
    "analysis.py": ["analyze_session", "get_analysis", "get_session_tts", "get_transcription"],
    "feedback.py": ["get_feedback"],
}


@pytest.mark.parametrize("filename,handlers", sorted(AUTHD_SECURED_HANDLERS.items()))
def test_analysis_and_feedback_routes_are_authenticated(filename: str, handlers: list):
    tree = _module(filename)
    bound = _handlers_bound_to(tree, "get_current_user")
    assert sorted(bound) == sorted(handlers), f"{filename} binds {sorted(bound)}"
    # Decision D-A2: the permissive resolver may not be used as a second door.
    assert _handlers_bound_to(tree, "get_optional_current_user") == []


@pytest.mark.parametrize("filename", sorted(AUTHD_SECURED_HANDLERS))
def test_analysis_and_feedback_routes_authorize_through_the_shared_helper(filename: str):
    """A session lookup is not authorization; ownership is proven by the AUTH-C helper."""
    source = (ROUTES_DIR / filename).read_text(encoding="utf-8")
    assert "from app.services.session_ownership import owned_session" in source
    assert "owned_session(db, session_id, current_user)" in source
    assert "db.get(SessionModel" not in source
