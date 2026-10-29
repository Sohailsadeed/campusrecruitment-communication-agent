"""Speech emotion recognition using the audEERING MSP-Podcast wav2vec2 model."""

import json
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Optional, Union

import numpy as np

from config import settings

logger = logging.getLogger(__name__)

MODEL_ID = "audeering/wav2vec2-large-robust-12-ft-emotion-msp-dim"
TARGET_SAMPLE_RATE = 16000

_EMOTION_MODEL = None
_EMOTION_PROCESSOR = None


def _neutral_result() -> dict:
    return {
        "summary": {
            "confidence_score": 50.0,
            "nervousness_score": 50.0,
            "composure_score": 60.0,
            "delivery_style": "Neutral",
            "peak_nervous_second": None,
        },
        "dimensions": {"arousal": 0.5, "valence": 0.5, "dominance": 0.5},
        "timeline": [],
    }


def _load_model():
    global _EMOTION_MODEL, _EMOTION_PROCESSOR
    if _EMOTION_MODEL is not None and _EMOTION_PROCESSOR is not None:
        return _EMOTION_MODEL, _EMOTION_PROCESSOR

    from transformers import AutoFeatureExtractor, AutoModelForAudioClassification

    processor = AutoFeatureExtractor.from_pretrained(MODEL_ID, trust_remote_code=True)
    model = AutoModelForAudioClassification.from_pretrained(
        MODEL_ID, trust_remote_code=True
    )
    model.to("cpu")
    model.eval()

    _EMOTION_MODEL = model
    _EMOTION_PROCESSOR = processor
    return model, processor


def _resample(waveform: np.ndarray, sr: int, target_sr: int) -> np.ndarray:
    if sr == target_sr or waveform.size == 0:
        return waveform.astype(np.float32, copy=False)

    try:
        import librosa

        return librosa.resample(
            waveform.astype(np.float32), orig_sr=sr, target_sr=target_sr
        ).astype(np.float32, copy=False)
    except Exception:
        pass

    try:
        import torch
        import torchaudio.functional as AF

        tensor = torch.from_numpy(waveform.astype(np.float32))
        return AF.resample(tensor, sr, target_sr).numpy().astype(np.float32)
    except Exception:
        pass

    duration = waveform.shape[0] / float(sr)
    target_len = max(1, int(round(duration * target_sr)))
    src_times = np.linspace(0.0, duration, num=waveform.shape[0], endpoint=False)
    dst_times = np.linspace(0.0, duration, num=target_len, endpoint=False)
    return np.interp(dst_times, src_times, waveform).astype(np.float32)


def _to_mono(waveform: np.ndarray) -> np.ndarray:
    if waveform.ndim > 1:
        if waveform.shape[0] <= 8 and waveform.shape[0] < waveform.shape[1]:
            waveform = waveform.mean(axis=0)
        else:
            waveform = waveform.mean(axis=1)
    return np.asarray(waveform, dtype=np.float32).reshape(-1)


def _load_audio(audio_path: Union[str, Path], target_sr: int = TARGET_SAMPLE_RATE) -> np.ndarray:
    path = str(audio_path)

    try:
        import librosa

        waveform, _ = librosa.load(path, sr=target_sr, mono=True)
        return np.asarray(waveform, dtype=np.float32).reshape(-1)
    except Exception:
        pass

    try:
        import soundfile as sf

        data, sr = sf.read(path, always_2d=False)
        return _resample(_to_mono(np.asarray(data)), int(sr), target_sr)
    except Exception:
        pass

    try:
        import torchaudio

        waveform, sr = torchaudio.load(path)
        mono = _to_mono(waveform.numpy())
        return _resample(mono, int(sr), target_sr)
    except Exception:
        pass

    try:
        import av

        container = av.open(path)
        stream = container.streams.audio[0]
        resampler = av.AudioResampler(format="flt", layout="mono", rate=target_sr)
        frames: List[np.ndarray] = []
        for frame in container.decode(stream):
            for resampled in resampler.resample(frame):
                frames.append(resampled.to_ndarray().reshape(-1))
        container.close()
        if frames:
            return np.concatenate(frames).astype(np.float32, copy=False)
    except Exception:
        pass

    raise RuntimeError(f"Unable to decode audio file: {path}")


def _dimension_order(model) -> List[str]:
    default = ["arousal", "valence", "dominance"]
    id2label = getattr(getattr(model, "config", None), "id2label", None) or {}
    if not id2label:
        return default

    order: List[str] = []
    for idx in range(3):
        label = id2label.get(idx, id2label.get(str(idx)))
        if label is None:
            return default
        order.append(str(label).strip().lower())

    if sorted(order) != sorted(default):
        return default
    return order


def _normalize_raw(raw: np.ndarray) -> np.ndarray:
    if raw.size == 0:
        return raw
    low = float(raw.min())
    high = float(raw.max())
    if low >= 0.0 and high <= 1.0:
        normalized = raw
    elif low >= -1.0 and high <= 1.0:
        normalized = (raw + 1.0) / 2.0
    else:
        normalized = 1.0 / (1.0 + np.exp(-raw))
    return np.clip(normalized, 0.0, 1.0)


def _metrics(arousal: float, valence: float, dominance: float) -> tuple:
    confidence = np.clip(
        (dominance * 0.5 + valence * 0.3 + (1.0 - abs(arousal - 0.5)) * 0.2) * 100,
        0,
        100,
    )
    nervousness = np.clip(
        (arousal * 0.5 + (1.0 - dominance) * 0.3 + (1.0 - valence) * 0.2) * 100,
        0,
        100,
    )
    composure = np.clip(100.0 - (nervousness * 0.8), 0, 100)
    return float(confidence), float(nervousness), float(composure)


def _delivery_style(confidence: float, nervousness: float, composure: float) -> str:
    if nervousness >= 60.0:
        return "Hesitant"
    if confidence >= 70.0 and nervousness < 40.0:
        return "Confident & Authoritative"
    if composure >= 70.0:
        return "Calm & Composed"
    if confidence >= 55.0:
        return "Steady & Measured"
    return "Tentative"


def analyze_speech_emotion(
    audio_path: Union[str, Path],
    chunk_duration_sec: float = 3.0,
    stride_sec: float = 1.5,
) -> dict:
    try:
        import torch

        waveform = _load_audio(audio_path)
        if waveform.size == 0:
            logger.warning("Emotion analysis received empty audio: %s", audio_path)
            return _neutral_result()

        model, processor = _load_model()
        order = _dimension_order(model)
        index = {name: order.index(name) for name in ("arousal", "valence", "dominance")}

        chunk_size = max(1, int(round(chunk_duration_sec * TARGET_SAMPLE_RATE)))
        stride_size = max(1, int(round(stride_sec * TARGET_SAMPLE_RATE)))

        windows: List[tuple] = []
        total = waveform.shape[0]
        start = 0
        while start < total:
            end = min(start + chunk_size, total)
            windows.append((start, end))
            if end >= total:
                break
            start += stride_size

        raw_vectors: List[np.ndarray] = []
        spans: List[tuple] = []
        for start, end in windows:
            chunk = waveform[start:end]
            if chunk.size < int(0.1 * TARGET_SAMPLE_RATE):
                continue
            inputs = processor(
                chunk, sampling_rate=TARGET_SAMPLE_RATE, return_tensors="pt"
            )
            with torch.no_grad():
                outputs = model(**inputs)
            logits = getattr(outputs, "logits", None)
            if logits is None:
                logits = outputs[0]
            vector = logits.detach().cpu().numpy().reshape(-1)[:3]
            if vector.size < 3:
                continue
            raw_vectors.append(
                np.array(
                    [
                        vector[index["arousal"]],
                        vector[index["valence"]],
                        vector[index["dominance"]],
                    ],
                    dtype=np.float32,
                )
            )
            spans.append((start / TARGET_SAMPLE_RATE, end / TARGET_SAMPLE_RATE))

        if not raw_vectors:
            logger.warning("Emotion analysis produced no windows for %s", audio_path)
            return _neutral_result()

        normalized = _normalize_raw(np.vstack(raw_vectors))
        timeline: List[dict] = []
        nervous_values: List[float] = []

        for (start_sec, end_sec), dims in zip(spans, normalized):
            arousal = float(dims[0])
            valence = float(dims[1])
            dominance = float(dims[2])
            confidence, nervousness, _ = _metrics(arousal, valence, dominance)
            nervous_values.append(nervousness)
            timeline.append(
                {
                    "start_sec": round(start_sec, 3),
                    "end_sec": round(end_sec, 3),
                    "confidence": round(confidence, 2),
                    "nervousness": round(nervousness, 2),
                    "arousal": round(arousal, 4),
                    "valence": round(valence, 4),
                    "dominance": round(dominance, 4),
                }
            )

        mean_dims = normalized.mean(axis=0)
        arousal = float(mean_dims[0])
        valence = float(mean_dims[1])
        dominance = float(mean_dims[2])
        confidence, nervousness, composure = _metrics(arousal, valence, dominance)

        peak_idx = int(np.argmax(nervous_values))
        peak_nervous_second: Optional[float] = timeline[peak_idx]["start_sec"]

        return {
            "summary": {
                "confidence_score": round(confidence, 2),
                "nervousness_score": round(nervousness, 2),
                "composure_score": round(composure, 2),
                "delivery_style": _delivery_style(confidence, nervousness, composure),
                "peak_nervous_second": peak_nervous_second,
            },
            "dimensions": {
                "arousal": round(arousal, 4),
                "valence": round(valence, 4),
                "dominance": round(dominance, 4),
            },
            "timeline": timeline,
        }
    except Exception as exc:
        logger.warning("Speech emotion analysis failed for %s: %s", audio_path, exc)
        return _neutral_result()


_LOCAL_BUFFERS: Dict[int, List[dict]] = {}
_REDIS_CLIENT = None
_REDIS_AVAILABLE: Optional[bool] = None
_REDIS_LAST_CHECK = 0.0
_REDIS_RECHECK_SECONDS = 30.0
_BUFFER_TTL_SECONDS = 3600
_MAX_LOCAL_POINTS = 5000


def _buffer_key(session_id: int) -> str:
    return f"emotion:session:{int(session_id)}"


def _mark_redis_down(exc: Optional[Exception] = None) -> None:
    global _REDIS_CLIENT, _REDIS_AVAILABLE, _REDIS_LAST_CHECK
    if _REDIS_AVAILABLE is not False:
        logger.info("Emotion Redis buffer unavailable, using in-memory fallback: %s", exc)
    _REDIS_CLIENT = None
    _REDIS_AVAILABLE = False
    _REDIS_LAST_CHECK = time.monotonic()


def _get_redis():
    global _REDIS_CLIENT, _REDIS_AVAILABLE, _REDIS_LAST_CHECK

    now = time.monotonic()
    if _REDIS_AVAILABLE is True and _REDIS_CLIENT is not None:
        return _REDIS_CLIENT
    if _REDIS_AVAILABLE is False and (now - _REDIS_LAST_CHECK) < _REDIS_RECHECK_SECONDS:
        return None

    _REDIS_LAST_CHECK = now
    try:
        import redis

        redis_url = getattr(settings, "redis_url", None) or "redis://localhost:6379/0"
        client = redis.Redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=0.5,
            socket_timeout=0.5,
        )
        client.ping()
        _REDIS_CLIENT = client
        _REDIS_AVAILABLE = True
        return client
    except Exception as exc:
        _mark_redis_down(exc)
        return None


def buffer_emotion_point(session_id: int, point: dict) -> None:
    key = _buffer_key(session_id)
    client = _get_redis()
    if client is not None:
        try:
            pipe = client.pipeline()
            pipe.rpush(key, json.dumps(point))
            pipe.expire(key, _BUFFER_TTL_SECONDS)
            pipe.execute()
            return
        except Exception as exc:
            _mark_redis_down(exc)

    buffer = _LOCAL_BUFFERS.setdefault(int(session_id), [])
    buffer.append(point)
    if len(buffer) > _MAX_LOCAL_POINTS:
        del buffer[:-_MAX_LOCAL_POINTS]


def _drain_points(session_id: int) -> List[dict]:
    points: List[dict] = []
    key = _buffer_key(session_id)
    client = _get_redis()
    if client is not None:
        try:
            pipe = client.pipeline()
            pipe.lrange(key, 0, -1)
            pipe.delete(key)
            raw_points, _ = pipe.execute()
            for raw in raw_points or []:
                try:
                    points.append(json.loads(raw))
                except Exception:
                    continue
        except Exception as exc:
            _mark_redis_down(exc)

    points.extend(_LOCAL_BUFFERS.pop(int(session_id), []))
    return points


def _summarize_points(points: List[dict]) -> dict:
    timeline: List[dict] = []
    total_weight = 0.0
    confidence_sum = 0.0
    nervousness_sum = 0.0
    composure_sum = 0.0
    dimension_names = ("arousal", "valence", "dominance")
    dimension_sums = {name: 0.0 for name in dimension_names}
    dimension_weight = 0.0

    for point in points:
        try:
            weight = float(point.get("weight", 1.0))
        except (TypeError, ValueError):
            weight = 1.0
        if weight <= 0:
            weight = 1.0

        try:
            confidence = float(point.get("confidence", point.get("confidence_score", 50.0)))
        except (TypeError, ValueError):
            confidence = 50.0
        try:
            nervousness = float(
                point.get("nervousness", point.get("nervousness_score", 50.0))
            )
        except (TypeError, ValueError):
            nervousness = 50.0
        composure_raw = point.get("composure", point.get("composure_score"))
        try:
            composure = (
                float(composure_raw)
                if composure_raw is not None
                else 100.0 - nervousness * 0.8
            )
        except (TypeError, ValueError):
            composure = 100.0 - nervousness * 0.8

        confidence = float(np.clip(confidence, 0.0, 100.0))
        nervousness = float(np.clip(nervousness, 0.0, 100.0))
        composure = float(np.clip(composure, 0.0, 100.0))

        total_weight += weight
        confidence_sum += confidence * weight
        nervousness_sum += nervousness * weight
        composure_sum += composure * weight

        start_sec = point.get("start_sec", point.get("t_sec"))
        end_sec = point.get("end_sec")
        timeline_point = {
            "start_sec": start_sec,
            "end_sec": end_sec,
            "confidence": round(confidence, 2),
            "nervousness": round(nervousness, 2),
            "composure": round(composure, 2),
        }
        has_dimensions = False
        for name in dimension_names:
            value = point.get(name)
            if value is None:
                continue
            try:
                dimension_sums[name] += float(value) * weight
                has_dimensions = True
            except (TypeError, ValueError):
                continue
        if has_dimensions:
            dimension_weight += weight
        for name in dimension_names:
            if point.get(name) is not None:
                timeline_point[name] = point.get(name)
        timeline.append(timeline_point)

    if total_weight <= 0:
        return _neutral_result()

    confidence = confidence_sum / total_weight
    nervousness = nervousness_sum / total_weight
    composure = composure_sum / total_weight

    peak_nervous_second = None
    if timeline:
        peak_point = max(timeline, key=lambda item: item.get("nervousness", 0.0))
        peak_nervous_second = peak_point.get("start_sec")

    dimensions = {name: 0.5 for name in dimension_names}
    if dimension_weight > 0:
        for name in dimension_names:
            dimensions[name] = round(dimension_sums[name] / dimension_weight, 4)

    return {
        "summary": {
            "confidence_score": round(confidence, 2),
            "nervousness_score": round(nervousness, 2),
            "composure_score": round(composure, 2),
            "delivery_style": _delivery_style(confidence, nervousness, composure),
            "peak_nervous_second": peak_nervous_second,
        },
        "dimensions": dimensions,
        "timeline": timeline,
    }


def get_session_emotion_summary(session_id: int, fallback: Optional[dict] = None) -> dict:
    try:
        points = _drain_points(session_id)
    except Exception as exc:
        logger.warning("Failed to read emotion buffer for session %s: %s", session_id, exc)
        points = []

    if not points:
        if isinstance(fallback, dict) and fallback.get("summary"):
            return fallback
        return _neutral_result()

    try:
        return _summarize_points(points)
    except Exception as exc:
        logger.warning("Failed to summarize emotion points for session %s: %s", session_id, exc)
        if isinstance(fallback, dict) and fallback.get("summary"):
            return fallback
        return _neutral_result()


def analyze_audio_chunk(audio_bytes: bytes) -> dict:
    if not audio_bytes:
        return _neutral_result()

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            suffix=".webm", delete=False, dir=tempfile.gettempdir()
        ) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name
        return analyze_speech_emotion(
            tmp_path, chunk_duration_sec=1.5, stride_sec=1.5
        )
    except Exception as exc:
        logger.warning("Live emotion chunk analysis failed: %s", exc)
        return _neutral_result()
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

