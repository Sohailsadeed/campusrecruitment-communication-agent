"""Video/face tracking service (MediaPipe + mock fallback)."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.services.multimodal_tracker import analyze_multimodal_stream, is_multimodal_available

logger = logging.getLogger(__name__)


def is_mediapipe_available() -> bool:
    return is_multimodal_available()


def analyze_video(
    video_path: Optional[Path],
    utterances: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Analyze video for presence/eye-contact/posture metrics aligned to utterances."""
    return analyze_multimodal_stream(video_path, utterances=utterances)
