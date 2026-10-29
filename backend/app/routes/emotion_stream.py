"""Live emotion streaming WebSocket endpoint."""

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.emotion import analyze_audio_chunk, buffer_emotion_point

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Emotion Stream"])

_CHUNK_SECONDS = 1.5


@router.websocket("/ws/session/{session_id}/emotion")
async def emotion_websocket(websocket: WebSocket, session_id: int) -> None:
    await websocket.accept()
    elapsed = 0.0

    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break

            payload = message.get("bytes")
            if payload is None:
                text = (message.get("text") or "").strip().lower()
                if text in {"close", "stop", "end"}:
                    break
                continue

            try:
                result = await asyncio.to_thread(analyze_audio_chunk, payload)
            except Exception as exc:
                logger.warning("Live emotion analysis failed for session %s: %s", session_id, exc)
                result = {}

            summary = result.get("summary") or {}
            dimensions = result.get("dimensions") or {}

            confidence = float(summary.get("confidence_score", 50.0) or 50.0)
            nervousness = float(summary.get("nervousness_score", 50.0) or 50.0)
            composure = float(summary.get("composure_score", 60.0) or 60.0)
            delivery_style = summary.get("delivery_style") or "Neutral"

            start_sec = round(elapsed, 2)
            end_sec = round(elapsed + _CHUNK_SECONDS, 2)
            elapsed = end_sec

            point = {
                "start_sec": start_sec,
                "end_sec": end_sec,
                "confidence": round(confidence, 2),
                "nervousness": round(nervousness, 2),
                "composure": round(composure, 2),
                "arousal": dimensions.get("arousal"),
                "valence": dimensions.get("valence"),
                "dominance": dimensions.get("dominance"),
                "weight": _CHUNK_SECONDS,
            }

            try:
                await asyncio.to_thread(buffer_emotion_point, session_id, point)
            except Exception as exc:
                logger.warning(
                    "Failed to buffer emotion point for session %s: %s", session_id, exc
                )

            await websocket.send_json(
                {
                    "confidence": round(confidence, 2),
                    "nervousness": round(nervousness, 2),
                    "composure": round(composure, 2),
                    "delivery_style": delivery_style,
                    "start_sec": start_sec,
                    "end_sec": end_sec,
                }
            )
    except WebSocketDisconnect:
        logger.info("Emotion WebSocket disconnected for session %s", session_id)
    except Exception as exc:
        logger.warning("Emotion WebSocket error for session %s: %s", session_id, exc)
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
