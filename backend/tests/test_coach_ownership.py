"""AUTH-B (C-05): the coach must prove who is asking, and only ever touch that user's plan.

Before this task every coach handler resolved identity through a fail-open helper that fell back
to the literal user id 1, and complete_day carried `and user_id != 1` in its ownership clause —
so an anonymous caller *was* user 1 and could mark any day of *any* plan complete. NULL-owner
plans were public by a second accident: the guard short-circuits when `plan.user_id` is falsy.

Denials stay in the pre-existing vocabulary: 401 reuses AUTH-A's uniform body, 404 reuses
coach.py's own "Curriculum plan not found". Authenticated payload shapes are unchanged.
"""
from __future__ import annotations

import asyncio

import pytest
from coach_fixtures import (  # noqa: F401  (coach_app/make_account/make_plan/make_session/stubbed_agent are fixtures)
    AGENT_RESULT,
    BAD_AUTH_HEADERS,
    CALLER_ID,
    COACH_ROUTES,
    GUEST_ID,
    PLAN_NOT_FOUND,
    UNAUTHENTICATED,
    VICTIM_ID,
    agent_signature_has_no_identity_default,
    agent_source,
    call_route,
    coach_app,
    coach_tree,
    day,
    envelope_isolated,
    expired_token,
    make_account,
    make_plan,
    make_session,
    read_plan,
    stubbed_agent,
    week,
)
from conftest import BACKEND_DIR  # noqa: F401

from app.routes import coach as coach_module
from app.routes.auth import create_access_token

# ---------------------------------------------------------------------------
# 1-4. every route demands a usable bearer token
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("route", COACH_ROUTES)
@pytest.mark.parametrize("header", BAD_AUTH_HEADERS)
def test_coach_routes_deny_callers_without_a_usable_bearer_token(coach_app, route, header):
    response = call_route(coach_app, route, {"Authorization": header} if header else None, plan_id=999)
    assert response.status_code == 401, response.text
    assert response.json()["detail"] == UNAUTHENTICATED
    assert response.headers.get("WWW-Authenticate") == "Bearer"


@pytest.mark.parametrize("route", COACH_ROUTES)
def test_coach_routes_deny_an_expired_token(coach_app, make_account, route):
    account = make_account()
    response = call_route(coach_app, route, {"Authorization": f"Bearer {expired_token(account.email)}"}, plan_id=999)
    assert response.status_code == 401, response.text
    assert response.json()["detail"] == UNAUTHENTICATED


@pytest.mark.parametrize("route", COACH_ROUTES)
def test_coach_routes_deny_a_signed_token_whose_subject_no_longer_exists(coach_app, route):
    """A well-formed token for a deleted user must never resolve to a standing identity."""
    token = create_access_token("removed-user@coach.test")
    response = call_route(coach_app, route, {"Authorization": f"Bearer {token}"}, plan_id=999)
    assert response.status_code == 401, response.text
    assert response.json()["detail"] == UNAUTHENTICATED


def test_no_denial_falls_back_to_the_guest_identity(coach_app, make_plan, make_account):
    """The pre-existing harm: an anonymous read must not surface the id-1 account's curriculum."""
    make_account(user_id=GUEST_ID)
    guest_plan = make_plan(GUEST_ID)
    assert call_route(coach_app, "active-plan", None).status_code == 401
    assert make_plan is not None and guest_plan.id != 0


# ---------------------------------------------------------------------------
# 5-6. cross-account mutation, including the id-1 bypass that made it possible
# ---------------------------------------------------------------------------


def test_complete_day_denies_a_foreign_plan_for_an_ordinary_caller(coach_app, make_account, make_plan):
    victim = make_account(user_id=VICTIM_ID)
    caller = make_account(user_id=CALLER_ID)
    plan = make_plan(victim.id, days=week(active_day_number=1))

    response = coach_app.post(
        "/api/coach/complete-day",
        json={"plan_id": plan.id, "day_number": 1},
        headers=caller.auth,
    )
    assert response.status_code == 404
    assert response.json()["detail"] == PLAN_NOT_FOUND


def test_the_retired_guest_id_can_no_longer_complete_any_plan(coach_app, make_account, make_plan):
    """`and user_id != 1` exempted whoever resolved to id 1 — including an anonymous caller."""
    victim = make_account(user_id=VICTIM_ID)
    guest = make_account(user_id=GUEST_ID)
    plan = make_plan(victim.id, days=week(active_day_number=1))

    response = coach_app.post(
        "/api/coach/complete-day",
        json={"plan_id": plan.id, "day_number": 1},
        headers=guest.auth,
    )
    assert response.status_code == 404, response.text
    assert response.json()["detail"] == PLAN_NOT_FOUND


def test_anonymous_caller_cannot_complete_any_plan_by_id(coach_app, make_account, make_plan):
    victim = make_account(user_id=VICTIM_ID)
    plan = make_plan(victim.id, days=week(active_day_number=1))

    response = coach_app.post("/api/coach/complete-day", json={"plan_id": plan.id, "day_number": 1})
    assert response.status_code == 401, response.text


def test_a_denied_complete_day_leaves_the_foreign_plan_untouched(
    coach_app, db_session, make_account, make_plan
):
    victim = make_account(user_id=VICTIM_ID)
    guest = make_account(user_id=GUEST_ID)
    plan = make_plan(victim.id, days=week(active_day_number=1))
    before = read_plan(db_session, plan.id)

    guest_denial = coach_app.post(
        "/api/coach/complete-day",
        json={"plan_id": plan.id, "day_number": 1},
        headers=guest.auth,
    )
    anonymous_denial = coach_app.post(
        "/api/coach/complete-day", json={"plan_id": plan.id, "day_number": 1}
    )

    # The snapshot alone would also pass on a route that never ran: a router-level 404 answers
    # {"detail": "Not Found"} and a validation failure answers 422, so the ownership body is the
    # proof that the request reached the guard that protects the row.
    assert guest_denial.status_code == 404, guest_denial.text
    assert guest_denial.json() == {"detail": PLAN_NOT_FOUND}
    assert anonymous_denial.status_code == 401, anonymous_denial.text
    assert anonymous_denial.json() == {"detail": UNAUTHENTICATED}

    assert read_plan(db_session, plan.id) == before, "a denied request mutated the plan"


def test_a_denied_complete_day_does_not_unlock_the_next_day(coach_app, db_session, make_account, make_plan):
    victim = make_account(user_id=VICTIM_ID)
    guest = make_account(user_id=GUEST_ID)
    plan = make_plan(victim.id, days=week(active_day_number=1))

    denial = coach_app.post(
        "/api/coach/complete-day",
        json={"plan_id": plan.id, "day_number": 1},
        headers=guest.auth,
    )

    assert denial.status_code == 404, denial.text
    assert denial.json() == {"detail": PLAN_NOT_FOUND}

    statuses = [d["status"] for d in read_plan(db_session, plan.id)["days"]]
    assert statuses[0] == "in_progress", f"day 1 was mutated: {statuses}"
    assert statuses[1] == "pending", f"day 2 was unlocked: {statuses}"


# ---------------------------------------------------------------------------
# 7-8. NULL-owner plans are denied, not public
# ---------------------------------------------------------------------------


def test_active_plan_hides_another_users_plan(coach_app, make_account, make_plan):
    victim = make_account(user_id=VICTIM_ID)
    caller = make_account(user_id=CALLER_ID)
    plan = make_plan(victim.id)

    body = coach_app.get("/api/coach/active-plan", headers=caller.auth).json()
    assert body == {"has_plan": False, "plan": None}
    assert body.get("has_plan") is False and plan.id != 0


def test_active_plan_hides_a_null_owner_plan(coach_app, make_account, make_plan):
    caller = make_account(user_id=CALLER_ID)
    make_plan(None)

    response = coach_app.get("/api/coach/active-plan", headers=caller.auth)
    assert response.status_code == 200
    assert response.json() == {"has_plan": False, "plan": None}, "an unowned plan was served"


def test_a_null_owner_plan_cannot_be_completed_by_id(coach_app, db_session, make_account, make_plan):
    caller = make_account(user_id=CALLER_ID)
    plan = make_plan(None, days=week(active_day_number=1))
    before = read_plan(db_session, plan.id)

    response = coach_app.post(
        "/api/coach/complete-day",
        json={"plan_id": plan.id, "day_number": 1},
        headers=caller.auth,
    )
    assert response.status_code == 404, response.text
    assert response.json()["detail"] == PLAN_NOT_FOUND
    assert read_plan(db_session, plan.id) == before


def test_missing_foreign_and_unowned_plans_are_denied_identically(
    coach_app, db_session, make_account, make_plan
):
    """plan_id is enumerable, so the three denials must be indistinguishable to the caller.

    The contract promises one uniform 404 for missing/foreign/NULL-owner. Foreign and unowned were
    covered individually; without an absent-id leg the suite cannot notice a regression that
    answers 403, or a distinct "no such plan" body, for an id nobody has ever used — which would
    turn the endpoint into a plan-existence oracle.
    """
    from app.models.coach import CurriculumPlan

    victim = make_account(user_id=VICTIM_ID)
    caller = make_account(user_id=CALLER_ID)
    foreign = make_plan(victim.id, days=week(active_day_number=1))
    unowned = make_plan(None, days=week(active_day_number=1))
    absent_id = max(foreign.id, unowned.id) + 1000
    assert db_session.get(CurriculumPlan, absent_id) is None, "the absent id is not actually absent"

    denials = {}
    for label, plan_id in (("foreign", foreign.id), ("unowned", unowned.id), ("absent", absent_id)):
        denial = coach_app.post(
            "/api/coach/complete-day",
            json={"plan_id": plan_id, "day_number": 1},
            headers=caller.auth,
        )
        assert denial.status_code == 404, f"{label} denial: {denial.text}"
        denials[label] = (
            denial.json(),
            denial.headers.get("content-type"),
            denial.headers.get("WWW-Authenticate"),
        )

    assert denials["absent"] == denials["foreign"], "an absent plan is distinguishable from a foreign one"
    assert denials["unowned"] == denials["foreign"], "an unowned plan is distinguishable from a foreign one"
    assert denials["foreign"][0] == {"detail": PLAN_NOT_FOUND}, denials["foreign"][0]


def test_active_plan_still_serves_the_owners_own_plan(coach_app, make_account, make_plan):
    caller = make_account(user_id=CALLER_ID)
    plan = make_plan(caller.id)

    body = coach_app.get("/api/coach/active-plan", headers=caller.auth).json()
    assert body["has_plan"] is True
    assert body["plan"]["id"] == plan.id


# ---------------------------------------------------------------------------
# 9-11. generation writes a proven owner and never disturbs anyone else's plan
# ---------------------------------------------------------------------------


def test_generate_plan_persists_the_authenticated_users_id(coach_app, db_session, make_account):
    caller = make_account(user_id=CALLER_ID)

    response = coach_app.post("/api/coach/generate-plan", json={}, headers=caller.auth)
    assert response.status_code == 200, response.text

    plans = db_session.query(__import__("app.models.coach", fromlist=["CurriculumPlan"]).CurriculumPlan).all()
    assert len(plans) == 1
    assert plans[0].user_id == caller.id


def test_generate_plan_never_creates_a_null_owner_plan(coach_app, db_session, make_account):
    caller = make_account(user_id=CALLER_ID)
    coach_app.post("/api/coach/generate-plan", json={"force_replan": False}, headers=caller.auth)

    from app.models.coach import CurriculumPlan

    assert [p.user_id for p in db_session.query(CurriculumPlan).all()] == [caller.id]
    assert all(p.user_id is not None for p in db_session.query(CurriculumPlan).all())


def test_generate_plan_does_not_reuse_another_users_active_plan(coach_app, db_session, make_account, make_plan):
    victim = make_account(user_id=VICTIM_ID)
    caller = make_account(user_id=CALLER_ID)
    victim_plan = make_plan(victim.id)

    body = coach_app.post("/api/coach/generate-plan", json={}, headers=caller.auth).json()
    assert body["reused_existing"] is False, "another user's plan was handed out"
    assert read_plan(db_session, victim_plan.id)["status"] == "active"


def test_generate_plan_does_not_archive_a_null_owner_plan(coach_app, db_session, make_account, make_plan):
    """`plan.user_id IS NULL` matched the guest arm, so force_replan archived an unowned row."""
    caller = make_account(user_id=CALLER_ID)
    orphan = make_plan(None)

    response = coach_app.post(
        "/api/coach/generate-plan",
        json={"force_replan": True},
        headers=caller.auth,
    )
    assert response.status_code == 200, response.text
    assert read_plan(db_session, orphan.id)["status"] == "active", "an unowned plan was archived"


def test_generate_plan_does_not_archive_a_foreign_active_plan(coach_app, db_session, make_account, make_plan):
    victim = make_account(user_id=VICTIM_ID)
    guest = make_account(user_id=GUEST_ID)
    victim_plan = make_plan(victim.id)
    guest_plan = make_plan(guest.id)

    response = coach_app.post(
        "/api/coach/generate-plan",
        json={"force_replan": True},
        headers=guest.auth,
    )

    # force_replan must reach the archive step and run it. A 401 or a 422 would also leave every
    # row untouched, so the successful generation is what makes the untouched victim row evidence.
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"has_plan", "reused_existing", "plan"}
    assert body["reused_existing"] is False
    assert body["plan"]["id"] not in (victim_plan.id, guest_plan.id)

    assert read_plan(db_session, victim_plan.id)["status"] == "active"
    # The caller's own plan is the one the archive was entitled to touch.
    assert read_plan(db_session, guest_plan.id)["status"] == "archived"


# ---------------------------------------------------------------------------
# 12. auto-sync reads only the caller's sessions and only the caller's plan
# ---------------------------------------------------------------------------


def test_auto_sync_only_processes_the_authenticated_users_sessions(
    coach_app, make_account, make_plan, make_session
):
    """The id-1 account must not complete a curriculum from somebody else's orphan session."""
    guest = make_account(user_id=GUEST_ID)
    make_plan(guest.id, days=week(active_day_number=1, round_type="jam"))
    make_session(None, round_type="jam", score=95.0, title="someone else's orphan session")

    response = coach_app.post("/api/coach/auto-sync", headers=guest.auth)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["synced"] is False, f"guest pool leaked a foreign session: {body}"
    assert "score_achieved" not in body or body.get("score_achieved") is None


def test_auto_sync_ignores_another_users_sessions(coach_app, make_account, make_plan, make_session):
    victim = make_account(user_id=VICTIM_ID)
    caller = make_account(user_id=CALLER_ID)
    make_plan(caller.id, days=week(active_day_number=1, round_type="hr"))
    make_session(victim.id, round_type="hr", score=91.0)

    body = coach_app.post("/api/coach/auto-sync", headers=caller.auth).json()
    assert body["synced"] is False, f"a foreign session completed the plan: {body}"


def test_auto_sync_does_not_complete_a_null_owner_plan(coach_app, db_session, make_account, make_plan, make_session):
    caller = make_account(user_id=CALLER_ID)
    orphan = make_plan(None, days=week(active_day_number=1, round_type="jam"))
    make_session(caller.id, round_type="jam", score=77.0)

    body = coach_app.post("/api/coach/auto-sync", headers=caller.auth).json()
    assert body["synced"] is False, f"an unowned plan was synced: {body}"
    statuses = [d["status"] for d in read_plan(db_session, orphan.id)["days"]]
    assert statuses[0] == "in_progress"


def test_auto_sync_completes_the_owners_own_day_from_their_own_session(
    coach_app, db_session, make_account, make_plan, make_session
):
    caller = make_account(user_id=CALLER_ID)
    plan = make_plan(caller.id, days=week(active_day_number=1, round_type="jam"))
    session = make_session(caller.id, round_type="jam", score=88.0)

    body = coach_app.post("/api/coach/auto-sync", headers=caller.auth).json()
    assert body["synced"] is True, body
    assert body["completed_day"] == 1
    assert body["score_achieved"] == 88.0
    assert body["session_id"] == session.id

    days = read_plan(db_session, plan.id)["days"]
    assert days[0]["status"] == "completed"
    assert days[0]["score_achieved"] == 88.0
    assert days[1]["status"] == "in_progress", "the next day was not unlocked"


# ---------------------------------------------------------------------------
# 16. the billed agent is stubbed, and receives the authenticated identity
# ---------------------------------------------------------------------------


def test_generate_plan_invokes_the_stubbed_agent_with_the_authenticated_identity(
    coach_app, make_account, stubbed_agent
):
    caller = make_account(user_id=CALLER_ID)

    coach_app.post("/api/coach/generate-plan", json={"target_role": "Data & AI Engineer"}, headers=caller.auth)

    assert stubbed_agent.count == 1, "the route did not call the agent stub"
    assert stubbed_agent.calls[0] == {"user_id": caller.id, "target_role": "Data & AI Engineer"}
    assert stubbed_agent.real is not None


def test_anonymous_callers_cannot_spend_llm_calls(coach_app, stubbed_agent):
    coach_app.post("/api/coach/generate-plan", json={"force_replan": True})
    assert stubbed_agent.count == 0, "the agent ran for an unauthenticated caller"


# ---------------------------------------------------------------------------
# 15. authenticated payload shapes are exactly what they were
# ---------------------------------------------------------------------------

PLAN_KEYS = {
    "id",
    "target_role",
    "roadmap_title",
    "status",
    "target_date",
    "identified_bottlenecks",
    "days",
    "meta_summary",
    "created_at",
    "updated_at",
}


def test_active_plan_response_shape_is_unchanged(coach_app, make_account, make_plan):
    caller = make_account(user_id=CALLER_ID)
    make_plan(caller.id)

    body = coach_app.get("/api/coach/active-plan", headers=caller.auth).json()
    assert set(body) == {"has_plan", "plan"}
    assert set(body["plan"]) == PLAN_KEYS
    assert set(body["plan"]["days"][0]) == {
        "day_number", "title", "round_type", "drill_route", "drill_params", "focus_dimension",
        "pedagogical_rationale", "target_metric_goal", "status", "completed_at", "score_achieved",
    }


def test_generate_plan_response_shape_is_unchanged(coach_app, make_account):
    caller = make_account(user_id=CALLER_ID)

    body = coach_app.post("/api/coach/generate-plan", json={}, headers=caller.auth).json()
    assert set(body) == {"has_plan", "reused_existing", "plan"}
    assert set(body["plan"]) == PLAN_KEYS
    assert len(body["plan"]["days"]) == 7


def test_generate_plan_reuses_the_callers_own_active_plan(coach_app, make_account, make_plan):
    caller = make_account(user_id=CALLER_ID)
    plan = make_plan(caller.id)

    body = coach_app.post("/api/coach/generate-plan", json={}, headers=caller.auth).json()
    assert body["reused_existing"] is True
    assert body["plan"]["id"] == plan.id


def test_complete_day_response_shape_is_unchanged(coach_app, make_account, make_plan):
    caller = make_account(user_id=CALLER_ID)
    plan = make_plan(caller.id, days=week(active_day_number=1))

    body = coach_app.post(
        "/api/coach/complete-day",
        json={"plan_id": plan.id, "day_number": 1},
        headers=caller.auth,
    ).json()
    assert set(body) == {"success", "plan"}
    assert set(body["plan"]) == {"id", "status", "days", "completed_day"}
    assert body["success"] is True
    assert body["plan"]["id"] == plan.id


def test_complete_day_rejects_a_day_that_is_not_in_the_plan(coach_app, make_account, make_plan):
    caller = make_account(user_id=CALLER_ID)
    plan = make_plan(caller.id, days=week(active_day_number=1))

    response = coach_app.post(
        "/api/coach/complete-day",
        json={"plan_id": plan.id, "day_number": 42},
        headers=caller.auth,
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Day 42 not found in plan"


def test_completing_the_last_day_marks_the_plan_completed(coach_app, db_session, make_account, make_plan):
    caller = make_account(user_id=CALLER_ID)
    days = week(active_day_number=7)
    for d in days[:6]:
        d["status"] = "completed"
        d["score_achieved"] = 80.0
    plan = make_plan(caller.id, days=days)

    coach_app.post(
        "/api/coach/complete-day",
        json={"plan_id": plan.id, "day_number": 7},
        headers=caller.auth,
    )
    assert read_plan(db_session, plan.id)["status"] == "completed"


def test_auto_sync_response_shape_is_unchanged_when_nothing_matches(coach_app, make_account):
    caller = make_account(user_id=CALLER_ID)

    body = coach_app.post("/api/coach/auto-sync", headers=caller.auth).json()
    assert body == {"synced": False, "message": "No active curriculum plan found"}


# ---------------------------------------------------------------------------
# 13-14. static guards: the guest identity must not come back
# ---------------------------------------------------------------------------

COACH_HANDLERS = ("get_active_plan", "create_plan", "complete_day", "auto_sync_recent_drills")


@pytest.mark.parametrize("handler", COACH_HANDLERS)
def test_every_coach_handler_binds_the_fail_closed_resolver(handler):
    from coach_fixtures import _depends_names

    bound = _depends_names(coach_tree(), handler)
    assert "get_current_user" in bound, f"{handler} binds {sorted(bound)}"
    assert "_get_optional_user" not in bound, f"{handler} is still optional-auth"


@pytest.mark.parametrize(
    "forbidden",
    [
        "user_id != 1",
        "_resolve_user_id",
        "current_user else 1",
        "_get_optional_user",
        "CurriculumPlan.user_id.is_(None)",
        "user_id > 1",
    ],
)
def test_the_guest_identity_patterns_are_gone_from_the_coach_route(forbidden):
    from coach_fixtures import coach_source

    assert forbidden not in coach_source("coach.py"), f"{forbidden!r} still in coach.py"


@pytest.mark.parametrize("forbidden", ["user_id > 1", "user_id == 1", 'state.get("user_id", 1)'])
def test_the_guest_identity_patterns_are_gone_from_the_agent(forbidden):
    assert forbidden not in agent_source(), f"{forbidden!r} still in curriculum_agent.py"


def test_the_agent_no_longer_defaults_to_an_identity():
    assert agent_signature_has_no_identity_default(), "generate_curriculum_plan still defaults to user 1"


# ---------------------------------------------------------------------------
# agent read side, exercised directly (D2: curriculum_agent.py is in AUTH-B's scope)
# ---------------------------------------------------------------------------


def test_extract_candidate_history_ignores_orphans_for_the_guest_account(db_session, make_account, make_session):
    from app.services.coach.curriculum_agent import extract_candidate_history

    guest = make_account(user_id=GUEST_ID)
    make_session(None, round_type="jam", score=90.0, title="orphan session")
    make_session(VICTIM_ID if guest.id != VICTIM_ID else CALLER_ID, round_type="technical", score=70.0)

    history = extract_candidate_history(guest.id, db_session)
    assert history["total_sessions"] == 0, "the guest pool merged other people's sessions"


def test_extract_candidate_history_sees_only_its_own_sessions(db_session, make_account, make_session):
    from app.services.coach.curriculum_agent import extract_candidate_history

    caller = make_account(user_id=CALLER_ID)
    make_session(caller.id, round_type="jam", score=81.0)
    make_session(None, round_type="hr", score=95.0)

    history = extract_candidate_history(caller.id, db_session)
    assert history["total_sessions"] == 1
    assert history["jam"]["attempt_count"] == 1
    assert history["hr"]["attempt_count"] == 0


def test_audit_history_node_fails_explicitly_without_an_identity(db_session):
    """No silent default: a state missing user_id must raise rather than borrow user 1."""
    from app.services.coach.curriculum_agent import audit_history_node

    with pytest.raises(KeyError):
        asyncio.run(audit_history_node({"target_role": "General Placement", "history_summary": {}}))


def test_audit_history_node_runs_for_an_explicit_identity(db_session, make_account, make_session):
    from app.services.coach.curriculum_agent import audit_history_node

    caller = make_account(user_id=CALLER_ID)
    make_session(caller.id, round_type="jam", score=82.0)

    result = asyncio.run(audit_history_node({"user_id": caller.id, "target_role": "General Placement", "history_summary": {}}))
    assert result["history_summary"]["total_sessions"] == 1


# ---------------------------------------------------------------------------
# 17. isolation
# ---------------------------------------------------------------------------


def test_the_run_uses_only_the_isolated_temp_envelope():
    envelope_isolated()


def test_the_coach_router_mounts_under_the_same_prefix():
    """A renamed prefix would silently 404 every frontend call; the guard keeps the contract."""
    assert coach_module.router.prefix == "/api/coach"
    paths = {route.path for route in coach_module.router.routes}
    assert paths == {
        "/api/coach/active-plan",
        "/api/coach/generate-plan",
        "/api/coach/complete-day",
        "/api/coach/auto-sync",
    }


def test_the_stub_is_what_the_route_calls(coach_app, stubbed_agent, make_account):
    """If coach.py ever re-imports the agent elsewhere, this stops the suite spending money."""
    caller = make_account(user_id=CALLER_ID)
    coach_app.post("/api/coach/generate-plan", json={}, headers=caller.auth)
    assert stubbed_agent.calls, "the route bypassed the stub"
    assert coach_module.generate_curriculum_plan is not stubbed_agent.real
