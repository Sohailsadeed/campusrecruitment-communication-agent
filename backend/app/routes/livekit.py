"""LiveKit room access endpoints — the only place a SpeakFlow client gets a token from.

The handler order is the security order: prove the caller owns the session, then derive the room,
then sign. A foreign, orphaned or absent session is refused with AUTH-C's single 404 before any
cryptographic work happens, so this endpoint cannot be used to probe which rooms exist, and an
unconfigured server answers 503 rather than 500.

Nothing that leaves this handler can be used to sign anything else: the response carries the token,
its expiry and the room it opens. The API secret stays in the backend's environment.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database.engine import get_db
from app.models.user import User
from app.routes.auth import get_current_user
from app.services import livekit_access
from app.services.session_ownership import owned_round_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/livekit", tags=["LiveKit"])

# General on purpose: which setting is missing is an operator question, and the answer is not
# something an unauthenticated caller should be able to read off a public endpoint.
NOT_CONFIGURED_DETAIL = "LiveKit room access is not configured on this server."
TOKEN_FAILED_DETAIL = "Could not issue LiveKit room access. Please try again."


class RoomAccessRequest(BaseModel):
    """A session id, and nothing else.

    No identity, no display name, no room, no grant: every one of those is derived server-side
    from the authenticated caller and the session they have already been proved to own.
    """

    session_id: int = Field(gt=0, description="HR session the caller owns")


@router.post("/token")
def issue_room_token(
    payload: RoomAccessRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Short-lived access to one candidate's own HR room, for microphone publishing only."""
    session = owned_round_session(db, payload.session_id, current_user, round_type="hr")

    try:
        access = livekit_access.mint_hr_room_access(session.id, current_user.id)
    except livekit_access.LiveKitConfigurationError as exc:
        # The message names a setting, never a value; the secret is not in it and not logged.
        logger.warning("LiveKit access refused, not configured (session=%s user=%s): %s",
                       session.id, current_user.id, exc)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail=NOT_CONFIGURED_DETAIL)
    except livekit_access.LiveKitTokenError as exc:
        logger.error("LiveKit token signing failed (session=%s user=%s): %s",
                     session.id, current_user.id, exc)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail=TOKEN_FAILED_DETAIL)

    logger.info("Issued LiveKit room access (session=%s user=%s ttl=%ss)",
                session.id, current_user.id, access.ttl_seconds)

    return {
        "url": access.url,
        "token": access.token,
        "room_name": access.room_name,
        "identity": access.identity,
        "expires_at": access.expires_at,
        "ttl_seconds": access.ttl_seconds,
    }
