"""Helpers for raw 16-bit PCM chunks streamed from the browser."""

from __future__ import annotations

from typing import Optional

import numpy as np

PCM16_SAMPLE_RATE = 16000
PCM16_CHUNK_BYTES = 3200
_MAGIC = (b"\x1aE\xdf\xa3", b"RIFF", b"OggS", b"fLaC", b"ID3")


def is_pcm16_chunk(audio_bytes: bytes) -> bool:
    if not audio_bytes or len(audio_bytes) % 2 != 0:
        return False
    if audio_bytes.startswith(_MAGIC):
        return False
    return len(audio_bytes) % PCM16_CHUNK_BYTES == 0


def decode_pcm16_chunk(audio_bytes: bytes) -> Optional[np.ndarray]:
    if not is_pcm16_chunk(audio_bytes):
        return None
    samples = np.frombuffer(audio_bytes, dtype="<i2")
    if samples.size == 0:
        return None
    return samples.astype(np.float32) / 32768.0
