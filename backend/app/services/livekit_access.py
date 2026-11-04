"""LiveKit room access: who may join which room, with which rights, and for how long.

Two rules shape everything here.

*Nothing about the room comes from the request body.* A candidate may name a session id, and the
route has already proved they own that session; the room name and the participant identity are
derived from those two ids. There is no parameter through which a caller could ask to join another
user's room or to be someone else, and LiveKit enforces the identity in the token (`sub`) rather
than any identity the client offers.

*V1 is a microphone.* The grant set lets a candidate publish exactly one kind of track
(`microphone`) and nothing else: no data channel, no screen share, no agent, no ingress, no
metadata editing, no room administration, and no ability to create or list rooms. The next
milestone — the Python voice agent — needs its own identity and its own grant set; it must not
widen this one.

The SDK is imported lazily. The token is HMAC-signed, so minting needs no network call, but the
package is an optional dependency: an environment that has not installed it must still boot and
must answer 503, not fail at import.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, NamedTuple, Optional

from config import settings

logger = logging.getLogger(__name__)

# The only media source a browser participant may publish in V1.
MICROPHONE_SOURCE = "microphone"

# LiveKit accepts almost any string as a room name, so a name built from user-supplied text would
# need a charset rule of our own. These patterns are the belt to the route's ownership check: an
# id is an int, and anything else fails here instead of reaching the SFU.
ROOM_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
PREFIX_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,31}$")


class LiveKitConfigurationError(RuntimeError):
    """The server cannot issue access: no keys, no URL, or the SDK is not installed.

    An operator problem, never a candidate's fault, so the route turns it into a 503 and the
    message stays general — the detail names which setting is missing, not any secret value.
    """


class LiveKitTokenError(RuntimeError):
    """The SDK refused to sign a token. Cause is logged as an exception class only."""


class RoomAccess(NamedTuple):
    """Everything a client needs to join, and nothing it needs to sign anything."""

    url: str
    token: str
    room_name: str
    identity: str
    expires_at: str
    ttl_seconds: int


def _load_sdk() -> tuple:
    try:
        from livekit.api import AccessToken, VideoGrants
    except ImportError as exc:
        raise LiveKitConfigurationError(
            "the LiveKit server SDK is not installed in this environment"
        ) from exc
    return AccessToken, VideoGrants


def configuration_problem() -> Optional[str]:
    """What is missing, as a short field name — or None when this server can issue access."""
    if not settings.livekit_api_key or not settings.livekit_api_secret:
        return "LIVEKIT_API_KEY/LIVEKIT_API_SECRET"
    if not settings.livekit_url:
        return "LIVEKIT_URL"
    if not PREFIX_PATTERN.match((settings.livekit_room_prefix or "").lower()):
        return "LIVEKIT_ROOM_PREFIX"
    return None


def is_configured() -> bool:
    return configuration_problem() is None


def hr_room_name(session_id: int, user_id: int) -> str:
    """One room per (HR session, candidate), derived from ids the route already verified.

    The user id is in the name even though a session already belongs to one user: a room must be
    unshareable even if a session row is ever re-assigned, and the name is the only thing that
    makes two candidates' tokens collide or not.
    """
    prefix = (settings.livekit_room_prefix or "speakflow").lower()
    name = f"{prefix}-hr-{int(session_id)}-{int(user_id)}"
    if not ROOM_NAME_PATTERN.match(name):
        raise LiveKitConfigurationError("LIVEKIT_ROOM_PREFIX produces an unusable room name")
    return name


def participant_identity(user_id: int) -> str:
    return f"user-{int(user_id)}"


def _ttl() -> timedelta:
    return timedelta(minutes=int(settings.livekit_token_ttl_minutes))


def mint_hr_room_access(session_id: int, user_id: int) -> RoomAccess:
    """Sign a short-lived token for exactly one candidate's own HR room."""
    problem = configuration_problem()
    if problem is not None:
        raise LiveKitConfigurationError(f"LiveKit is not configured: {problem} is unset")

    AccessToken, VideoGrants = _load_sdk()
    room = hr_room_name(session_id, user_id)
    identity = participant_identity(user_id)

    grants = VideoGrants(
        room=room,
        room_join=True,
        can_publish=True,
        can_subscribe=True,
        can_publish_data=False,
        can_publish_sources=[MICROPHONE_SOURCE],
        can_update_own_metadata=False,
    )

    try:
        signed = (
            AccessToken(settings.livekit_api_key, settings.livekit_api_secret)
            .with_identity(identity)
            .with_ttl(_ttl())
            .with_grants(grants)
            .to_jwt()
        )
    except LiveKitConfigurationError:
        raise
    except Exception as exc:
        # No token text, no key, no secret-bearing message: the class is enough to act on.
        raise LiveKitTokenError(type(exc).__name__) from exc

    return RoomAccess(
        url=settings.livekit_url,
        token=signed,
        room_name=room,
        identity=identity,
        expires_at=_expiry_of(signed),
        ttl_seconds=int(_ttl().total_seconds()),
    )


def _expiry_of(token: str) -> str:
    """The expiry the SFU will actually enforce, read back from the token we just signed.

    Unverified decode of our own output: this is not authorisation, it is a countdown for the
    client, and it keeps the client from believing it has longer than the server does.
    """
    import jwt

    claims: Any = jwt.decode(token, options={"verify_signature": False})
    exp = int(claims.get("exp", 0))
    return datetime.fromtimestamp(exp, timezone.utc).isoformat()
