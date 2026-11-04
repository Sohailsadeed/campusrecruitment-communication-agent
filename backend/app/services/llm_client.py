"""Turn configuration into a chat client, in one place.

Each evaluator used to decide this for itself: read a second copy of .env, test whether an OpenRouter
credential happened to exist, and build whichever client that implied. A present credential then
routed a candidate's answer to a remote endpoint during what was believed to be a local run. The
decision now lives in `Settings.resolve_llm_target()` and this module is the only place that turns
that decision into a client, so no service can select a provider by inspecting secrets again.
"""
import logging
from typing import Optional

from langchain_openai import ChatOpenAI

from config import settings

logger = logging.getLogger(__name__)

# Never a credential, a prompt or an exception body: this string is what a caller sees when it
# refused to run, and it is also safe to write to a log.
MISSING_CREDENTIAL = (
    "LLM_PROVIDER is set to 'openrouter' but no OpenRouter credential is configured. Refusing to "
    "run: set the API key or choose LLM_PROVIDER=ollama. No other provider is substituted.")


def cache_signature() -> tuple:
    """Identity of the client configuration, without the credential itself.

    Held by each service instead of a raw key, so a module global never carries a secret and a
    changed provider, model or endpoint still rebuilds the client.
    """
    target = settings.resolve_llm_target()
    return (target["provider"], target["model"], target["base_url"], target["credential_present"])


def build_local_client(base_url: str, model: str, temperature: float):
    """The Ollama client.

    langchain-community 0.4 stopped exporting ChatOllama when the integration moved to the
    standalone langchain-ollama package; prefer the package that carries it, and if the deployment
    has neither, name the missing dependency instead of leaving an answer scored by a fallback as if
    a model had read it.
    """
    try:
        from langchain_ollama import ChatOllama
    except ImportError:
        try:
            from langchain_community.chat_models import ChatOllama
        except ImportError as exc:
            raise ImportError(
                "local Ollama evaluation needs the 'langchain-ollama' package "
                "(langchain-community no longer exports ChatOllama)"
            ) from exc
    return ChatOllama(base_url=base_url, model=model, temperature=temperature)


def build_chat_client(caller: str, temperature: float, max_tokens: Optional[int] = None):
    """Build the client for the configured provider only -- never for an available credential.

    An Ollama server that is down, or an integration that is not installed, raises here or leaves
    the calling evaluator to its documented fallback. Neither outcome quietly sends the answer to
    OpenRouter.
    """
    target = settings.resolve_llm_target()

    if target["provider"] == "openrouter":
        if not target["credential_present"]:
            raise RuntimeError(MISSING_CREDENTIAL)
        logger.info("%s using OpenRouter model %s at %s", caller, target["model"], target["base_url"])
        kwargs = {"model": target["model"], "api_key": settings.openrouter_api_key,
                  "base_url": target["base_url"], "temperature": temperature}
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        return ChatOpenAI(**kwargs)

    logger.info("%s using local Ollama model %s at %s", caller, target["model"], target["base_url"])
    return build_local_client(target["base_url"], target["model"], temperature)
