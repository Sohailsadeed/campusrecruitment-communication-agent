"""Tier-2 Socratic nudge generation via a local Ollama model."""

import asyncio
import logging
from typing import Optional

from app.services.laya import get_tier1_hint
from config import settings

logger = logging.getLogger(__name__)

PRIMARY_MODEL = "qwen2.5:1.5b"
LLM_TIMEOUT_SECONDS = 1.5
MAX_WORDS = 15


def _build_prompt(question: str, partial_transcript: str) -> str:
    articulated = (partial_transcript or "").strip() or "Nothing yet"
    problem = (question or "").strip() or "A guesstimate / market sizing problem"
    return (
        "You are a top consulting case interviewer.\n"
        "The candidate is stuck solving this guesstimate problem:\n"
        f"Problem: {problem}\n"
        f"Candidate articulated so far: {articulated}\n"
        "Give ONE short, direct Socratic hint (under 15 words) to help them "
        "take the next step. Do not solve it.\n"
        "Hint:"
    )


def _extract_content(response) -> Optional[str]:
    if response is None:
        return None

    message = getattr(response, "message", None)
    if message is None and isinstance(response, dict):
        message = response.get("message")

    content = getattr(message, "content", None)
    if content is None and isinstance(message, dict):
        content = message.get("content")
    if content is None and isinstance(response, dict):
        content = response.get("response")
    return str(content) if content is not None else None


def _clean_hint(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    cleaned = " ".join(str(text).strip().split())
    if cleaned.lower().startswith("hint:"):
        cleaned = cleaned[5:].strip()
    if not cleaned:
        return None
    words = cleaned.split()
    if len(words) > MAX_WORDS:
        cleaned = " ".join(words[:MAX_WORDS])
    return cleaned


async def _generate_with_httpx(model: str, prompt: str) -> Optional[str]:
    import httpx

    url = f"{settings.ollama_base_url.rstrip('/')}/api/chat"
    async with httpx.AsyncClient(timeout=LLM_TIMEOUT_SECONDS) as client:
        response = await client.post(
            url,
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "options": {"temperature": 0.3, "num_predict": 25},
            },
        )
        response.raise_for_status()
        return _clean_hint(_extract_content(response.json()))


async def _generate_with_model(model: str, prompt: str) -> Optional[str]:
    try:
        from ollama import AsyncClient
    except ImportError:
        return await asyncio.wait_for(
            _generate_with_httpx(model, prompt), timeout=LLM_TIMEOUT_SECONDS
        )

    client = AsyncClient(host=settings.ollama_base_url)
    response = await asyncio.wait_for(
        client.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.3, "num_predict": 25},
        ),
        timeout=LLM_TIMEOUT_SECONDS,
    )
    return _clean_hint(_extract_content(response))


async def generate_tier2_nudge(
    question: str, partial_transcript: str, category: str = "Market Sizing"
) -> str:
    prompt = _build_prompt(question, partial_transcript)

    models = [PRIMARY_MODEL]
    fallback_model = getattr(settings, "ollama_model", None)
    if fallback_model and fallback_model != PRIMARY_MODEL:
        models.append(fallback_model)

    for model in models:
        try:
            hint = await _generate_with_model(model, prompt)
            if hint:
                return hint
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Tier-2 nudge model %s failed: %s", model, exc)

    return get_tier1_hint(category)
