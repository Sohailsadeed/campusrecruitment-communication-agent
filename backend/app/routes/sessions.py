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
    HTTPException,
    Request,
    UploadFile,
    Response,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.engine import get_db
from app.models.session import Session as SessionModel
from app.models.user import User
from app.routes.auth import get_current_user
from app.schemas.session import (
    SessionCreate,
    SessionDetailOut,
    SessionOut,
    SessionUpdate,
)
from app.services import upload_store
from app.services.session_ownership import (
    owned_session,
    owned_session_scope,
)
from app.services.session_media import (
    get_session_audio_media_type,
    get_session_audio_path,
    get_session_audio_url,
)
from config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sessions", tags=["sessions"])

# Allowed MIME types and their permitted file extensions
_ALLOWED_VIDEO_TYPES = {
    "video/webm",
    "video/mp4",
    "video/ogg",
    "video/quicktime",
    "video/x-matroska",
    "application/octet-stream",
}
_ALLOWED_AUDIO_TYPES = {
    "audio/webm",
    "audio/ogg",
    "audio/mpeg",
    "audio/wav",
    "audio/mp4",
    "application/octet-stream",
}
_ALLOWED_EXTENSIONS = {".webm", ".mp4", ".ogg", ".mov", ".mp3", ".wav", ".m4a"}


def _save_upload(tx: upload_store.UploadTransaction, file: UploadFile, subdir: str) -> str:
    """Validate with the existing rules, then stream this file into the request's transaction.

    Nothing about the contract changes: the same MIME and extension checks produce the same 400
    bodies, the same uuid name is the final name, the same 200 MB budget produces the same 413.
    What changes is where the bytes go while they arrive — a private temp file in the destination
    directory, closed before it is moved into place, so a failing write never leaves a partial
    file at a path anything could read.
    """
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

    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    staged = tx.stage(target_dir, unique)
    try:
        staged.write_from(file.file, max_bytes=max_bytes)
    except upload_store.UploadTooLarge:
        # The temp keeps its open descriptor until the request unwinds and aborts it, which is the
        # only order that can delete the file on Windows.
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds maximum allowed size of {settings.max_upload_size_mb} MB",
        ) from None
    return str(staged.publish())


@router.get("", response_model=List[SessionOut])
def list_sessions(
    limit: int = 50,
    offset: int = 0,
    round_type: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[SessionOut]:
    stmt = select(SessionModel).where(owned_session_scope(current_user))
    stmt = stmt.order_by(SessionModel.created_at.desc())
    if round_type:
        stmt = stmt.where(SessionModel.round_type == round_type)
    stmt = stmt.offset(offset).limit(limit)
    rows = db.scalars(stmt).all()
    return [SessionOut.model_validate(r) for r in rows]


@router.post("", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
async def create_session(
    title: str = Form(...),
    description: Optional[str] = Form(None),
    duration_seconds: float = Form(0.0),
    round_type: str = Form("jam"),
    round_metadata: Optional[str] = Form(None),
    video: Optional[UploadFile] = File(None),
    audio: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SessionOut:
    video_path: Optional[str] = None
    audio_path: Optional[str] = None
    tx = upload_store.transaction()
    try:
        if video is not None:
            video_path = _save_upload(tx, video, "video")
        if audio is not None:
            audio_path = _save_upload(tx, audio, "audio")

        meta_dict = {}
        if round_metadata:
            try:
                import json
                meta_dict = json.loads(round_metadata) if isinstance(round_metadata, str) else dict(round_metadata)
            except Exception:
                meta_dict = {}

        new_session = SessionModel(
            user_id=current_user.id,
            title=title,
            description=description,
            duration_seconds=duration_seconds,
            video_path=video_path,
            audio_path=audio_path,
            round_type=round_type,
            round_metadata=meta_dict,
            status="pending",
        )
        db.add(new_session)
        db.commit()
        db.refresh(new_session)
    except BaseException:
        # This request as a whole failed, so nothing it published stays behind — including the file
        # the first upload completed when the second upload or the commit is what broke.
        tx.rollback()
        raise
    tx.finalize()
    return SessionOut.model_validate(new_session)


@router.post("/json", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
def create_session_json(
    payload: SessionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SessionOut:
    new_session = SessionModel(
        user_id=current_user.id,
        title=payload.title,
        description=payload.description,
        duration_seconds=payload.duration_seconds,
        round_type=payload.round_type,
        overall_score=payload.overall_score,
        round_metadata=payload.round_metadata,
        report=payload.report,
        status="pending",
    )
    db.add(new_session)
    db.commit()
    db.refresh(new_session)
    return SessionOut.model_validate(new_session)


@router.get("/{session_id}", response_model=SessionDetailOut)
def get_session(
    session_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SessionDetailOut:
    session = owned_session(db, session_id, current_user)
    detail = SessionDetailOut.model_validate(session)
    detail.audio_url = get_session_audio_url(session, request)
    return detail


@router.get("/{session_id}/audio")
def get_session_audio(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FileResponse:
    """Stream the candidate's original JAM recording when it still exists."""
    session = owned_session(db, session_id, current_user)
    audio_path = get_session_audio_path(session)
    if audio_path is None:
        raise HTTPException(status_code=404, detail="Original recording unavailable")

    return FileResponse(
        path=str(audio_path),
        media_type=get_session_audio_media_type(audio_path),
        filename=f"session_{session.id}{audio_path.suffix.lower()}",
        content_disposition_type="inline",
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.patch("/{session_id}", response_model=SessionOut)
def update_session(
    session_id: int,
    payload: SessionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SessionOut:
    session = owned_session(db, session_id, current_user)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(session, field, value)
    db.commit()
    db.refresh(session)
    return SessionOut.model_validate(session)


@router.delete(
    "/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
def delete_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    session = owned_session(db, session_id, current_user)
    db.delete(session)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

