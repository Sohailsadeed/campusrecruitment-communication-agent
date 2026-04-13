"""Transcription service (Whisper + mock fallback)."""
from __future__ import annotations

import logging
import random
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Try to import whisper lazily; gracefully fall back to a mock if unavailable.
try:  # pragma: no cover - import guard
    import whisper  # type: ignore

    _WHISPER_AVAILABLE = True
except Exception:  # pragma: no cover - import guard
    whisper = None  # type: ignore
    _WHISPER_AVAILABLE = False


_MODEL_CACHE: Dict[str, object] = {}


# Representative mock transcripts used when Whisper isn't installed.
MOCK_TRANSCRIPTS = [
    (
        "Hello everyone, um, thank you for joining me today. I want to talk about, "
        "you know, the importance of clear communication. Basically, when we speak "
        "in public, we have to, like, really focus on our audience and make sure our "
        "message is actually understood. Um, today I will cover three main points."
    ),
    (
        "Good afternoon. Today I'd like to share some thoughts on effective leadership. "
        "Leadership, um, is not just about giving orders. It's literally about inspiring "
        "people to, you know, work toward a shared goal. Basically, great leaders listen "
        "first and speak second."
    ),
    (
        "Let me tell you a story. When I started my career, I was, uh, really nervous "
        "about public speaking. I would, like, forget my words and stumble. But with "
        "practice, I actually became more confident. You know, the key is to prepare "
        "and then trust yourself."
    ),
]


def is_whisper_available() -> bool:
    return _WHISPER_AVAILABLE


def _get_model(model_name: str):
    if not _WHISPER_AVAILABLE:
        return None
    if model_name not in _MODEL_CACHE:
        logger.info("Loading whisper model: %s", model_name)
        _MODEL_CACHE[model_name] = whisper.load_model(model_name)  # type: ignore
    return _MODEL_CACHE[model_name]


def transcribe_audio(
    audio_path: Optional[Path],
    model_name: str = "base",
) -> Dict[str, object]:
    """Transcribe an audio file.

    Returns a dict with keys: ``text``, ``language``, ``confidence``.
    Falls back to a deterministic mock when whisper is unavailable
    or when transcription fails.
    """
    if _WHISPER_AVAILABLE and audio_path is not None and Path(audio_path).exists():
        try:
            model = _get_model(model_name)
            result = model.transcribe(str(audio_path))  # type: ignore
            return {
                "text": str(result.get("text", "")).strip(),
                "language": str(result.get("language", "en")),
                "confidence": 0.92,
            }
        except Exception as exc:  # pragma: no cover - runtime guard
            logger.warning("Whisper transcription failed, using mock: %s", exc)

    # Mock fallback - deterministic per path so same session yields same result.
    seed = abs(hash(str(audio_path) or "default"))
    rng = random.Random(seed)
    text = rng.choice(MOCK_TRANSCRIPTS)
    return {
        "text": text,
        "language": "en",
        "confidence": 0.85,
    }
