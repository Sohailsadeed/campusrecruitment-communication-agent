"""Session CRUD + upload routes."""
from __future__ import annotations

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
    UploadFile,
    status,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.engine import get_db
from app.models.session import Session as SessionModel
from app.schemas.session import (
    SessionCreate,
    SessionDetailOut,
    SessionOut,
    SessionUpdate,
)
from config import settings

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


def _save_upload(file: UploadFile, subdir: str) -> str:
    target_dir = settings.upload_dir / subdir
    target_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(file.filename or "").suffix or ".webm"
    unique = f"{uuid.uuid4().hex}{suffix}"
    dest = target_dir / unique
    with dest.open("wb") as out:
        shutil.copyfileobj(file.file, out)
    return str(dest)


@router.get("", response_model=List[SessionOut])
def list_sessions(
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
) -> List[SessionOut]:
    stmt = (
        select(SessionModel)
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
) -> SessionOut:
    video_path: Optional[str] = None
    audio_path: Optional[str] = None
    if video is not None:
        video_path = _save_upload(video, "video")
    if audio is not None:
        audio_path = _save_upload(audio, "audio")

    new_session = SessionModel(
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
    payload: SessionCreate, db: Session = Depends(get_db)
) -> SessionOut:
    new_session = SessionModel(
        title=payload.title,
        description=payload.description,
        duration_seconds=payload.duration_seconds,
        status="pending",
    )
    db.add(new_session)
    db.commit()
    db.refresh(new_session)
    return SessionOut.model_validate(new_session)


@router.get("/{session_id}", response_model=SessionDetailOut)
def get_session(session_id: int, db: Session = Depends(get_db)) -> SessionDetailOut:
    session = db.get(SessionModel, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return SessionDetailOut.model_validate(session)


@router.patch("/{session_id}", response_model=SessionOut)
def update_session(
    session_id: int,
    payload: SessionUpdate,
    db: Session = Depends(get_db),
) -> SessionOut:
    session = db.get(SessionModel, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(session, field, value)
    db.commit()
    db.refresh(session)
    return SessionOut.model_validate(session)


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(session_id: int, db: Session = Depends(get_db)) -> None:
    session = db.get(SessionModel, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    db.delete(session)
    db.commit()
