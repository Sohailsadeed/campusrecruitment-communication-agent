"""Cross-session memory using Mem0 with ChromaDB and the configured LLM provider."""
import logging
from typing import List, Optional

from app.services import llm_client
from config import settings

logger = logging.getLogger(__name__)

_memory = None


def _llm_config() -> dict:
    """The Mem0 chat model, from the same provider decision every other evaluator uses.

    Mem0 speaks to both providers over the OpenAI-compatible surface, so only the endpoint, model and
    credential differ. Local by default: a present OpenRouter credential must not make cross-session
    memory a remote call. The placeholder for the local endpoint is not a secret -- Ollama ignores it.
    """
    target = settings.resolve_llm_target()
    if target["provider"] == "openrouter":
        if not target["credential_present"]:
            raise RuntimeError(llm_client.MISSING_CREDENTIAL)
        return {"provider": "openai",
                "config": {"model": target["model"], "api_key": settings.openrouter_api_key,
                           "openai_base_url": target["base_url"]}}
    return {"provider": "openai",
            "config": {"model": target["model"], "api_key": "sk-dummy-local",
                       "openai_base_url": f"{target['base_url'].rstrip('/')}/v1"}}


def _get_memory():
    """Initialize Mem0 with the configured LLM provider and local HuggingFace embeddings."""
    global _memory
    if _memory is None:
        try:
            from mem0 import Memory

            config = {
                "llm": _llm_config(),
                "embedder": {
                    "provider": "huggingface",
                    "config": {
                        "model": "sentence-transformers/all-MiniLM-L6-v2",
                    },
                },
                "vector_store": {
                    "provider": "chroma",
                    "config": {
                        "collection_name": "mem0_memories",
                        "host": settings.chroma_host,
                        "port": settings.chroma_port,
                    },
                },
            }
            _memory = Memory.from_config(config)
            logger.info("Mem0 memory service initialized with ChromaDB at %s:%s", settings.chroma_host, settings.chroma_port)
        except Exception as exc:
            logger.warning("Mem0 initialization failed (%s). Memory tracking will operate in fallback mode.", exc)
            _memory = None
    return _memory


async def store_performance(user_id: int | str, session_data: dict) -> None:
    """Store interview performance and identified weak areas in Mem0."""
    mem = _get_memory()
    if not mem:
        return

    try:
        role = session_data.get("role", "Software Engineer")
        total_score = session_data.get("total_score", "N/A")
        strengths = ", ".join(session_data.get("strengths", []))
        weaknesses = ", ".join(session_data.get("weaknesses", []))

        summary = (
            f"Technical Interview for {role}: "
            f"Score {total_score}/100. "
            f"Demonstrated Strengths: {strengths}. "
            f"Identified Weak Areas to probe next time: {weaknesses}."
        )
        mem.add(summary, user_id=str(user_id))
        logger.info("Stored Mem0 performance trace for candidate %s", user_id)
    except Exception as exc:
        logger.warning("Failed to store Mem0 trace for user %s: %s", user_id, exc)


async def get_user_history(user_id: int | str) -> List[dict]:
    """Retrieve candidate's past interview memory traces to focus on weak areas."""
    mem = _get_memory()
    if not mem:
        return []

    try:
        memories = mem.get_all(filters={"user_id": str(user_id)})
        return memories.get("results", []) if isinstance(memories, dict) else (memories or [])
    except Exception as exc:
        logger.warning("Failed to retrieve Mem0 history for user %s: %s", user_id, exc)
        return []
