"""Laya cadence sensing, stall detection, and instant category scaffolds."""

import io
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

SILENCE_RMS_THRESHOLD = 0.015
TIER1_STALL_SECONDS = 5.0
TIER2_STALL_SECONDS = 10.0
_MAX_HISTORY = 2000

CATEGORY_SCAFFOLDS = {
    "Market Sizing": "💡 Scope Check: Have you clarified household vs. individual demand, or replacement rate?",
    "Revenue Estimation": "💡 Revenue Tree: Break this into (Average Footfall / Hour) × (Average Spend per Customer).",
    "Operational & Capacity Sizing": "💡 Bottleneck Check: What is the limiting resource (counters/runways/staff) and its hourly throughput?",
    "Abstract / Fermi Problems": "💡 Proxy Check: Pick a known anchor number (e.g. city population) and work backward.",
}


def get_tier1_hint(category: str) -> str:
    return CATEGORY_SCAFFOLDS.get(category, CATEGORY_SCAFFOLDS["Market Sizing"])


@dataclass
class LayaSessionState:
    consecutive_silent_seconds: float = 0.0
    consecutive_stall_seconds: float = 0.0
    tier1_fired: bool = False
    tier2_fired: bool = False
    rebound_success_count: int = 0
    cadence_history: List[float] = field(default_factory=list)
    active_hint_tier: int = 0
    hints_issued: int = 0
    hint_stall_seconds: float = 0.0
    rebound_latencies: List[float] = field(default_factory=list)
    total_speech_seconds: float = 0.0
    total_silent_seconds: float = 0.0


_LAYAS: Dict[int, LayaSessionState] = {}


def _decode_samples(audio_bytes: bytes) -> Optional[np.ndarray]:
    try:
        import av

        with av.open(io.BytesIO(audio_bytes)) as container:
            frames: List[np.ndarray] = []
            for frame in container.decode(audio=0):
                samples = frame.to_ndarray()
                if np.issubdtype(samples.dtype, np.integer):
                    samples = samples.astype(np.float32) / float(
                        np.iinfo(samples.dtype).max
                    )
                else:
                    samples = samples.astype(np.float32)
                frames.append(samples.reshape(-1))
        if not frames:
            return None
        return np.concatenate(frames)
    except Exception:
        return None


def _raw_byte_samples(audio_bytes: bytes) -> Optional[np.ndarray]:
    if not audio_bytes:
        return None
    raw = np.frombuffer(audio_bytes, dtype=np.uint8).astype(np.float32)
    return (raw - 128.0) / 128.0


def _compute_rms(audio_bytes: bytes) -> float:
    samples = _decode_samples(audio_bytes)
    if samples is None or samples.size == 0:
        samples = _raw_byte_samples(audio_bytes)
    if samples is None or samples.size == 0:
        return 0.0
    samples = samples.astype(np.float64, copy=False)
    return float(np.sqrt(np.mean(np.square(samples))))


def _get_state(session_id: int) -> LayaSessionState:
    return _LAYAS.setdefault(int(session_id), LayaSessionState())


def process_laya_chunk(
    session_id: int, audio_bytes: bytes, elapsed_chunk_sec: float = 1.5
) -> dict:
    state = _get_state(session_id)
    rms = _compute_rms(audio_bytes)
    is_speaking = rms >= SILENCE_RMS_THRESHOLD

    trigger_tier: Optional[int] = None
    rebound = False

    if is_speaking:
        if state.active_hint_tier:
            latency = max(
                0.0, state.consecutive_stall_seconds - state.hint_stall_seconds
            )
            state.rebound_latencies.append(latency)
            state.rebound_success_count += 1
            state.active_hint_tier = 0
            state.hint_stall_seconds = 0.0
            rebound = True

        state.consecutive_silent_seconds = 0.0
        state.consecutive_stall_seconds = 0.0
        state.tier1_fired = False
        state.tier2_fired = False
        state.total_speech_seconds += elapsed_chunk_sec
    else:
        state.consecutive_silent_seconds += elapsed_chunk_sec
        state.consecutive_stall_seconds += elapsed_chunk_sec
        state.total_silent_seconds += elapsed_chunk_sec

        if (
            state.consecutive_stall_seconds >= TIER2_STALL_SECONDS
            and not state.tier2_fired
        ):
            trigger_tier = 2
            state.tier2_fired = True
            state.tier1_fired = True
            state.active_hint_tier = 2
            state.hints_issued += 1
            state.hint_stall_seconds = state.consecutive_stall_seconds
        elif (
            state.consecutive_stall_seconds >= TIER1_STALL_SECONDS
            and not state.tier1_fired
        ):
            trigger_tier = 1
            state.tier1_fired = True
            state.active_hint_tier = 1
            state.hints_issued += 1
            state.hint_stall_seconds = state.consecutive_stall_seconds

    state.cadence_history.append(1.0 if is_speaking else 0.0)
    if len(state.cadence_history) > _MAX_HISTORY:
        del state.cadence_history[:-_MAX_HISTORY]

    return {
        "is_speaking": is_speaking,
        "stall_seconds": state.consecutive_stall_seconds,
        "trigger_tier": trigger_tier,
        "rebound": rebound,
    }


def get_session_laya_metrics(session_id: int, cleanup: bool = True) -> dict:
    state = _LAYAS.get(int(session_id))

    if state is None or not state.cadence_history:
        if cleanup:
            _LAYAS.pop(int(session_id), None)
        return {
            "available": False,
            "rebound_agility_score": 0.0,
            "cadence_stability": 0.0,
            "hints_issued": 0,
            "rebound_success_count": 0,
            "average_rebound_latency_sec": 0.0,
            "speech_ratio": 0.0,
            "total_speech_seconds": 0.0,
            "total_silent_seconds": 0.0,
        }

    history = np.asarray(state.cadence_history, dtype=np.float64)
    speech_ratio = float(history.mean()) if history.size else 0.0
    deviation = float(history.std()) if history.size else 0.0

    if speech_ratio <= 0.0:
        cadence_stability = 0.0
    else:
        cadence_stability = float(
            np.clip(
                100.0 * (1.0 - min(1.0, deviation / max(speech_ratio, 0.15))),
                0.0,
                100.0,
            )
        )

    if state.hints_issued == 0:
        rebound_agility = 100.0
        average_latency = 0.0
    else:
        success_rate = state.rebound_success_count / float(state.hints_issued)
        average_latency = (
            float(np.mean(state.rebound_latencies))
            if state.rebound_latencies
            else 0.0
        )
        rebound_agility = float(
            np.clip(
                success_rate * 100.0 - min(25.0, average_latency * 5.0),
                0.0,
                100.0,
            )
        )

    result = {
        "available": True,
        "rebound_agility_score": round(rebound_agility, 2),
        "cadence_stability": round(cadence_stability, 2),
        "hints_issued": state.hints_issued,
        "rebound_success_count": state.rebound_success_count,
        "average_rebound_latency_sec": round(average_latency, 2),
        "speech_ratio": round(speech_ratio, 3),
        "total_speech_seconds": round(state.total_speech_seconds, 2),
        "total_silent_seconds": round(state.total_silent_seconds, 2),
    }

    if cleanup:
        _LAYAS.pop(int(session_id), None)

    return result
