"""Text-to-Speech (TTS) service using edge-tts with disk caching.

Synthesizes high-fidelity executive coach feedback using Microsoft Neural voices
(default: 'en-US-ChristopherNeural' - authoritative, measured executive voice).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from config import settings

logger = logging.getLogger(__name__)

_EDGE_TTS_AVAILABLE = False
try:
    import edge_tts
    _EDGE_TTS_AVAILABLE = True
except Exception:
    edge_tts = None


TTS_CACHE_DIR = settings.upload_dir / "tts"
TTS_CACHE_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_COACH_VOICE = "en-US-ChristopherNeural"


def is_tts_available() -> bool:
    return _EDGE_TTS_AVAILABLE


async def synthesize_feedback_audio(
    session_id: int,
    text: str,
    voice: str = DEFAULT_COACH_VOICE,
) -> Optional[Path]:
    """Synthesize coach feedback text to an MP3 file with disk caching."""
    if not _EDGE_TTS_AVAILABLE or not text.strip():
        return None

    clean_text = text.strip()
    # Limit length to prevent giant generation if LLM produced huge text
    if len(clean_text) > 1500:
        clean_text = clean_text[:1500] + "... Focus on these key adjustments."

    cache_file = TTS_CACHE_DIR / f"session_{session_id}_coach.mp3"
    if cache_file.exists() and cache_file.stat().st_size > 1000:
        return cache_file

    try:
        communicate = edge_tts.Communicate(clean_text, voice)
        await communicate.save(str(cache_file))
        return cache_file
    except Exception as exc:
        logger.warning("edge-tts generation failed for session %s: %s", session_id, exc)
        return None
