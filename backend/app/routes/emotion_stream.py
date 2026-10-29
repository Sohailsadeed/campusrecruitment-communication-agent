"""Live emotion streaming and Laya cadence coaching WebSocket endpoint."""

import asyncio
import json
import logging
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.database.engine import SessionLocal
from app.models.session import Session as SessionModel
from app.services.emotion import analyze_audio_chunk, buffer_emotion_point
from app.services.guesstimate.nudge_service import generate_tier2_nudge
from app.services.laya import get_tier1_hint, process_laya_chunk

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Emotion Stream"])

_CHUNK_SECONDS = 1.5


def _load_guesstimate_context(session_id: int):
    try:
        with SessionLocal() as db:
            session = db.get(SessionModel, session_id)
            if session is None or session.round_type != "guesstimate":
                return None, None
            case = getattr(session, "guesstimate_detail", None)
            if case is None:
                return "Market Sizing", ""
            return case.category or "Market Sizing", case.question or ""
    except Exception as exc:
        logger.warning(
            "Could not load guesstimate context for session %s: %s", session_id, exc
        )
        return None, None


@router.websocket("/ws/session/{session_id}/emotion")
async def emotion_websocket(websocket: WebSocket, session_id: int) -> None:
    await websocket.accept()
    elapsed = 0.0

    session_category, question_text = await asyncio.to_thread(
        _load_guesstimate_context, session_id
    )
    is_guesstimate = session_category is not None
    partial_transcript = ""

    tier2_task: Optional[asyncio.Task] = None
    hint_active = False
    send_lock = asyncio.Lock()

    async def send(payload: dict) -> None:
        async with send_lock:
            await websocket.send_json(payload)

    async def run_tier2() -> None:
        nonlocal hint_active
        try:
            nudge_text = await generate_tier2_nudge(
                question_text,
                partial_transcript,
                session_category or "Market Sizing",
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Tier-2 nudge failed for session %s: %s", session_id, exc)
            return

        message = (
            nudge_text
            if nudge_text.startswith("💡")
            else f"💡 Coach: {nudge_text}"
        )
        await send({"type": "coach_nudge", "tier": 2, "message": message})
        hint_active = True

    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break

            payload = message.get("bytes")
            if payload is None:
                text = (message.get("text") or "").strip()
                if text.lower() in {"close", "stop", "end"}:
                    break
                if not text:
                    continue
                try:
                    context = json.loads(text)
                except json.JSONDecodeError:
                    continue
                if isinstance(context, dict) and context.get("type") == "context":
                    if context.get("partial_transcript") is not None:
                        partial_transcript = str(context["partial_transcript"])
                    if context.get("question"):
                        question_text = str(context["question"])
                        is_guesstimate = True
                    if context.get("category"):
                        session_category = str(context["category"])
                        is_guesstimate = True
                continue

            if is_guesstimate:
                laya_result = await asyncio.to_thread(
                    process_laya_chunk, session_id, payload, _CHUNK_SECONDS
                )

                if laya_result.get("is_speaking"):
                    if tier2_task is not None and not tier2_task.done():
                        tier2_task.cancel()
                        tier2_task = None
                    if hint_active:
                        await send({"type": "clear_nudge"})
                        hint_active = False
                elif laya_result.get("trigger_tier") == 1:
                    await send(
                        {
                            "type": "coach_nudge",
                            "tier": 1,
                            "message": get_tier1_hint(
                                session_category or "Market Sizing"
                            ),
                        }
                    )
                    hint_active = True
                elif laya_result.get("trigger_tier") == 2:
                    if tier2_task is not None and not tier2_task.done():
                        tier2_task.cancel()
                    tier2_task = asyncio.create_task(run_tier2())

            try:
                result = await asyncio.to_thread(analyze_audio_chunk, payload)
            except Exception as exc:
                logger.warning(
                    "Live emotion analysis failed for session %s: %s",
                    session_id,
                    exc,
                )
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
                    "Failed to buffer emotion point for session %s: %s",
                    session_id,
                    exc,
                )

            await send(
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
        if tier2_task is not None and not tier2_task.done():
            tier2_task.cancel()
        try:
            await websocket.close()
        except Exception:
            pass
