"""Helpers for safely resolving and exposing original session recordings."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from fastapi import Request

from config import settings

_AUDIO_MEDIA_TYPES = {
    ".webm": "audio/webm",
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".ogg": "audio/ogg",
    ".oga": "audio/ogg",
    ".m4a": "audio/mp4",
    ".mp4": "audio/mp4",
}


def get_session_audio_path(session: object) -> Optional[Path]:
    """Return the stored original recording path if it is safe and readable.

    JAM sessions may persist the recording in either ``audio_path`` or
    ``video_path`` (the video container still holds the original audio track).
    Prefer a dedicated audio file, then fall back to the video recording.
    """
    upload_root = Path(settings.upload_dir).resolve()

    for attr in ("audio_path", "video_path"):
        raw_path = getattr(session, attr, None)
        if not raw_path:
            continue

        path = Path(str(raw_path))
        if path.is_absolute():
            candidates = [path]
        else:
            candidates = [upload_root / path, upload_root.parent / path]

        for candidate in candidates:
            try:
                resolved = candidate.resolve(strict=True)
                resolved.relative_to(upload_root)
            except (OSError, ValueError):
                continue
            if not resolved.is_file() or not os.access(resolved, os.R_OK):
                continue
            try:
                if resolved.stat().st_size <= 0:
                    continue
            except OSError:
                continue
            return resolved

    return None


def get_session_audio_media_type(path: Path) -> str:
    return _AUDIO_MEDIA_TYPES.get(path.suffix.lower(), "application/octet-stream")


def get_session_audio_url(session: object, request: Request) -> Optional[str]:
    """Build an absolute URL only when the original recording is available."""
    if get_session_audio_path(session) is None:
        return None
    base_url = str(request.base_url).rstrip("/")
    return f"{base_url}/api/sessions/{getattr(session, 'id', '')}/audio"
