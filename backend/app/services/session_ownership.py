"""AUTH-C: prove a caller owns the session they named, before anything else happens.

Every session-keyed route funnels through here so the ownership rule lives in one place:
``session.user_id == current_user.id``. A foreign session, an orphan row whose ``user_id`` is NULL
and an id that was never issued all raise the same 404 with the same detail, so probing ids cannot
discover which of the three a caller has hit — or that a recording exists at all.

The dependency direction is routes -> services -> models, so this module must never import a route
module: ``progress.py`` used to reach into ``sessions.py`` for its identity resolver, which made the
guest pool a shared dependency instead of a local mistake.
"""
from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import ColumnElement
from sqlalchemy.orm import Session

from app.models.session import Session as SessionModel
from app.models.user import User

# One detail for every refusal, across the session routes and the round routers alike.
NOT_FOUND_DETAIL = "Session not found"


def _not_found() -> HTTPException:
    """A fresh exception per refusal; a shared instance would carry another request's traceback."""
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=NOT_FOUND_DETAIL)


def owned_session(db: Session, session_id: int, current_user: User) -> SessionModel:
    """The session the caller named, or nothing they can distinguish from nothing.

    ``user_id IS NULL`` fails the comparison like any other owner, so legacy and orphan rows are
    private by the same rule as foreign ones rather than public by accident.
    """
    session = db.get(SessionModel, session_id)
    if session is None or session.user_id != current_user.id:
        raise _not_found()
    return session


def owned_round_session(
    db: Session,
    session_id: int,
    current_user: User,
    *,
    round_type: str,
) -> SessionModel:
    """Ownership first, then the round type, because a session of another round is not this round's.

    The round-type check shares the refusal so a caller cannot map which of their own ids belong to
    which round by probing three endpoints.
    """
    session = owned_session(db, session_id, current_user)
    if session.round_type != round_type:
        raise _not_found()
    return session


def owned_session_scope(current_user: User) -> ColumnElement[bool]:
    """The one filter a collection query may use: the caller's own rows, and no pool.

    There is deliberately no argument-less form. A caller without a verified identity never reaches
    here, because their request was refused as unauthenticated.
    """
    return SessionModel.user_id == current_user.id
