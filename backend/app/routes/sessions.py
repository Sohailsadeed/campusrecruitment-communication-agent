"""Session CRUD + upload routes."""
from __future__ import annotations

import logging
import shutil
import uuid
from pathlib import Path
from typing import List, Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    UploadFile,
    status,
)
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.engine import get_db
from app.models.session import Session as SessionModel
from app.models.user import User
from app.schemas.session import (
    SessionCreate,
    SessionDetailOut,
    SessionOut,
    SessionUpdate,
)
from config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sessions", tags=["sessions"])

# Allowed MIME types and their permitted file extensions
_ALLOWED_VIDEO_TYPES = {"video/webm", "video/mp4", "video/ogg", "video/quicktime"}
_ALLOWED_AUDIO_TYPES = {"audio/webm", "audio/ogg", "audio/mpeg", "audio/wav", "audio/mp4"}
_ALLOWED_EXTENSIONS = {".webm", ".mp4", ".ogg", ".mov", ".mp3", ".wav", ".m4a"}


def _get_current_user(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    """Extract and validate JWT from Authorization header, return the User."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1]
    try:
        from jose import jwt
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        subject: Optional[str] = payload.get("sub")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    if not subject:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    user = db.scalar(select(User).where(User.email == subject))
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def _save_upload(file: UploadFile, subdir: str) -> str:
    """Validate and save an uploaded file. Returns the stored path."""
    # Validate MIME type
    allowed = _ALLOWED_VIDEO_TYPES | _ALLOWED_AUDIO_TYPES
    content_type = (file.content_type or "").split(";")[0].strip()
    if content_type not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {content_type}",
        )

    # Validate extension (use only a safe suffix, never the raw client name)
    client_suffix = Path(file.filename or "").suffix.lower()
    if client_suffix and client_suffix not in _ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file extension: {client_suffix}")
    suffix = client_suffix if client_suffix in _ALLOWED_EXTENSIONS else ".webm"

    target_dir = settings.upload_dir / subdir
    target_dir.mkdir(parents=True, exist_ok=True)
    unique = f"{uuid.uuid4().hex}{suffix}"
    dest = target_dir / unique

    # Enforce max upload size
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    written = 0
    with dest.open("wb") as out:
        while chunk := file.file.read(1024 * 256):  # 256 KB chunks
            written += len(chunk)
            if written > max_bytes:
                dest.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=413,
                    detail=f"File exceeds maximum allowed size of {settings.max_upload_size_mb} MB",
                )
            out.write(chunk)
    return str(dest)


@router.get("", response_model=List[SessionOut])
def list_sessions(
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
) -> List[SessionOut]:
    stmt = (
        select(SessionModel)
        .where(SessionModel.user_id == current_user.id)
        .order_by(SessionModel.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    rows = db.scalars(stmt).all()
    return [SessionOut.model_validate(r) for r in rows]


@router.post("", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
async def create_session(
    title: str = Form(...),
    description: Optional[str] = Form(None),
    duration_seconds: float = Form(0.0),
    video: Optional[UploadFile] = File(None),
    audio: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
) -> SessionOut:
    video_path: Optional[str] = None
    audio_path: Optional[str] = None
    if video is not None:
        video_path = _save_upload(video, "video")
    if audio is not None:
        audio_path = _save_upload(audio, "audio")

    new_session = SessionModel(
        user_id=current_user.id,
        title=title,
        description=description,
        duration_seconds=duration_seconds,
        video_path=video_path,
        audio_path=audio_path,
        status="pending",
    )
    db.add(new_session)
    db.commit()
    db.refresh(new_session)
    return SessionOut.model_validate(new_session)


@router.post("/json", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
def create_session_json(
    payload: SessionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
) -> SessionOut:
    new_session = SessionModel(
        user_id=current_user.id,
        title=payload.title,
        description=payload.description,
        duration_seconds=payload.duration_seconds,
        status="pending",
    )
    db.add(new_session)
    db.commit()
    db.refresh(new_session)
    return SessionOut.model_validate(new_session)


def _get_session_for_user(session_id: int, user: User, db: Session) -> SessionModel:
    """Fetch a session, ensuring it belongs to the current user."""
    session = db.get(SessionModel, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.user_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    return session


@router.get("/{session_id}", response_model=SessionDetailOut)
def get_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
) -> SessionDetailOut:
    session = _get_session_for_user(session_id, current_user, db)
    return SessionDetailOut.model_validate(session)


@router.patch("/{session_id}", response_model=SessionOut)
def update_session(
    session_id: int,
    payload: SessionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
) -> SessionOut:
    session = _get_session_for_user(session_id, current_user, db)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(session, field, value)
    db.commit()
    db.refresh(session)
    return SessionOut.model_validate(session)


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
) -> None:
    session = _get_session_for_user(session_id, current_user, db)
    db.delete(session)
    db.commit()
