"""Provider selection for the HR evaluator: local by default, explicit to go remote.

These are resolver-level tests. Every client is a recorder -- no provider is contacted, no service
is started, and no database is opened. What is being held to account is a specific failure that
happened in real runs: a process launched from backend/ loaded the deployment's .env, found an
OpenRouter credential, and evaluated an answer against a remote endpoint while the operator believed
the run was local.
"""
from __future__ import annotations

import json
import logging
import sys
import types
from pathlib import Path

import pytest

import config
from app.services import llm_client
from app.services.guesstimate import evaluator as guesstimate_evaluator
from app.services.hr import evaluator
from app.services.technical import evaluator as technical_evaluator

CANARY = "sk-CANARY-NEVER-LOG-THIS-VALUE"
LOCAL_MODEL = "qwen3.5:4b"
LOCAL_URL = "http://127.0.0.1:11434"

# Every evaluator that was migrated onto the shared decision. Each keeps its own client cache, so
# each is checked to honour the same rule.
EVALUATORS = [("hr", evaluator), ("guesstimate", guesstimate_evaluator),
              ("technical", technical_evaluator)]


class Recorder:
    """Stands in for a langchain client; remembers how it was built, never connects."""

    built: list = []

    def __init__(self, **kwargs):
        type(self).built.append(kwargs)
        self.kwargs = kwargs
        for key, value in kwargs.items():
            setattr(self, key, value)


class OpenRouterRecorder(Recorder):
    pass


class OllamaRecorder(Recorder):
    pass


@pytest.fixture(autouse=True)
def clean_state(monkeypatch):
    """Reset every client cache and both recorder classes between tests."""
    for _, module in EVALUATORS:
        monkeypatch.setattr(module, "_llm", None, raising=False)
        monkeypatch.setattr(module, "_cached_signature", None, raising=False)
        monkeypatch.setattr(module, "_cached_key", None, raising=False)
    OpenRouterRecorder.built = []
    OllamaRecorder.built = []
    monkeypatch.setattr(llm_client, "ChatOpenAI", OpenRouterRecorder)
    fake_ollama_module = types.ModuleType("langchain_ollama")
    fake_ollama_module.ChatOllama = OllamaRecorder
    monkeypatch.setitem(sys.modules, "langchain_ollama", fake_ollama_module)
    yield


def configure(monkeypatch, provider="ollama", key="", ollama_url=LOCAL_URL, ollama_model=LOCAL_MODEL,
              chat_model="some/remote-model:free", openrouter_url="https://openrouter.ai/api/v1"):
    s = config.settings
    monkeypatch.setattr(s, "llm_provider", provider, raising=False)
    monkeypatch.setattr(s, "openrouter_api_key", key, raising=False)
    monkeypatch.setattr(s, "ollama_base_url", ollama_url, raising=False)
    monkeypatch.setattr(s, "ollama_model", ollama_model, raising=False)
    monkeypatch.setattr(s, "chat_model", chat_model, raising=False)
    monkeypatch.setattr(s, "openrouter_base_url", openrouter_url, raising=False)
    return s


# ---------------------------------------------------------------- environment resolution ----

def test_env_file_is_anchored_to_the_backend_not_the_working_directory(tmp_path, monkeypatch):
    """A decoy .env in the cwd must not be read, whichever directory the process runs from."""
    decoy = tmp_path / ".env"
    decoy.write_text("APP_NAME=from-the-cwd\nLLM_PROVIDER=openrouter\n", encoding="utf-8")
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("APP_NAME", raising=False)

    built = {}
    for here in (tmp_path, Path(config.__file__).resolve().parent):
        monkeypatch.chdir(here)
        built[str(here)] = config.Settings()

    for where, settings in built.items():
        assert settings.app_name != "from-the-cwd", f"the decoy .env leaked into the run from {where}"
    first, second = built.values()
    assert (first.llm_provider, first.openrouter_api_key) == (second.llm_provider,
                                                             second.openrouter_api_key), \
        "identical code produced different configuration depending on the working directory"


def test_the_resolved_env_file_is_an_absolute_path_inside_the_backend():
    assert config.ENV_FILE.is_absolute()
    assert config.ENV_FILE.name == ".env"
    assert config.ENV_FILE.parent == Path(config.__file__).resolve().parent


def test_local_settings_are_the_default_when_nothing_overrides_them(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    settings = config.Settings(_env_file=None)
    target = settings.resolve_llm_target()
    assert target["provider"] == "ollama"
    assert target["model"] == LOCAL_MODEL
    assert target["base_url"] == LOCAL_URL


def test_the_deployed_env_file_with_an_openrouter_key_still_selects_ollama(monkeypatch):
    """Whatever the deployment .env holds (never edited here), LLM_PROVIDER alone decides."""
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    settings = config.Settings()
    target = settings.resolve_llm_target()
    assert target["provider"] == "ollama", "a credential alone must never select a provider"
    assert target["base_url"] == settings.ollama_base_url
    assert settings.provider_diagnostics()["openrouter_key_configured"] == bool(
        settings.openrouter_api_key.strip())


def test_a_dotenv_carrying_a_key_selects_ollama_without_the_explicit_provider(tmp_path, monkeypatch):
    """The deployment shape that used to route answers remotely: a key present, no provider set."""
    env = tmp_path / ".env"
    env.write_text(f"OPENROUTER_API_KEY={CANARY}\nOLLAMA_MODEL={LOCAL_MODEL}\n", encoding="utf-8")
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    settings = config.Settings(_env_file=env)
    assert settings.openrouter_api_key == CANARY
    target = settings.resolve_llm_target()
    assert target["provider"] == "ollama"
    assert target["model"] == LOCAL_MODEL
    assert settings.provider_diagnostics()["openrouter_key_configured"] is True


def test_a_dotenv_selects_openrouter_only_when_it_says_so(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text(f"LLM_PROVIDER=openrouter\nOPENROUTER_API_KEY={CANARY}\n", encoding="utf-8")
    monkeypatch.delenv("LLM_PROVIDER", raising=False)

    target = config.Settings(_env_file=env).resolve_llm_target()
    assert target["provider"] == "openrouter"
    assert target["credential_present"] is True


def test_an_unrecognised_provider_is_refused_at_configuration_time(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    with pytest.raises(ValueError, match="LLM_PROVIDER"):
        config.Settings(_env_file=None)


# ------------------------------------------------------------------------ provider choice ----

def test_explicit_ollama_wins_over_a_present_openrouter_credential(monkeypatch):
    settings = configure(monkeypatch, provider="ollama", key=CANARY)
    client = evaluator._get_llm()
    assert isinstance(client, OllamaRecorder)
    assert OpenRouterRecorder.built == [], "a credential must not be able to route the answer away"
    assert client.kwargs["base_url"] == LOCAL_URL
    assert client.kwargs["model"] == LOCAL_MODEL
    assert settings.llm_provider == "ollama"


def test_a_missing_openrouter_credential_does_not_switch_the_provider(monkeypatch):
    configure(monkeypatch, provider="ollama", key="")
    assert isinstance(evaluator._get_llm(), OllamaRecorder)
    assert OpenRouterRecorder.built == []


def test_openrouter_is_built_only_when_it_is_the_configured_provider(monkeypatch):
    configure(monkeypatch, provider="openrouter", key=CANARY, chat_model="some/remote-model:free")
    client = evaluator._get_llm()
    assert isinstance(client, OpenRouterRecorder)
    assert OllamaRecorder.built == []
    assert client.kwargs["model"] == "some/remote-model:free"
    assert client.kwargs["base_url"] == "https://openrouter.ai/api/v1"


def test_configured_openrouter_without_a_credential_raises_instead_of_substituting(monkeypatch):
    configure(monkeypatch, provider="openrouter", key="")
    with pytest.raises(RuntimeError, match="LLM_PROVIDER"):
        evaluator._get_llm()
    assert OllamaRecorder.built == [], "must not quietly run locally and let the caller assume remote"
    assert OpenRouterRecorder.built == []
    assert evaluator._llm is None


def test_unavailable_ollama_integration_raises_instead_of_reaching_openrouter(monkeypatch):
    """Both import paths missing (the package absent, and community no longer exporting it)."""
    configure(monkeypatch, provider="ollama", key=CANARY)
    monkeypatch.setitem(sys.modules, "langchain_ollama", None)
    monkeypatch.setitem(sys.modules, "langchain_community", None)
    monkeypatch.setitem(sys.modules, "langchain_community.chat_models", None)
    with pytest.raises(ImportError, match="langchain-ollama"):
        evaluator._get_llm()
    assert OpenRouterRecorder.built == [], "an unusable local model must not mean a remote call"


def test_the_cached_client_is_rebuilt_when_the_provider_changes(monkeypatch):
    configure(monkeypatch, provider="ollama", key="")
    assert isinstance(evaluator._get_llm(), OllamaRecorder)
    configure(monkeypatch, provider="openrouter", key=CANARY)
    assert isinstance(evaluator._get_llm(), OpenRouterRecorder)
    assert len(OllamaRecorder.built) == 1


# --------------------------------------------------------------------------- diagnostics ----

def test_diagnostics_name_the_endpoint_and_model_but_never_the_credential(monkeypatch):
    settings = configure(monkeypatch, provider="ollama", key=CANARY)
    rendered = json.dumps(settings.provider_diagnostics(), sort_keys=True)
    assert CANARY not in rendered
    assert '"provider": "ollama"' in rendered
    assert LOCAL_URL in rendered and LOCAL_MODEL in rendered
    assert settings.provider_diagnostics()["openrouter_key_configured"] is True


def test_the_provider_decision_is_logged_without_the_secret(monkeypatch, caplog):
    configure(monkeypatch, provider="openrouter", key=CANARY, chat_model="some/remote-model:free")
    with caplog.at_level(logging.INFO, logger="app.services.llm_client"):
        evaluator._get_llm()
    text = caplog.text
    assert CANARY not in text
    assert "some/remote-model:free" in text


def test_the_client_is_built_from_configuration_alone_with_no_network_use(monkeypatch):
    """Constructing the real local client must not contact anything; it is a value object."""
    monkeypatch.delitem(sys.modules, "langchain_ollama")
    configure(monkeypatch, provider="ollama", key="")
    client = evaluator._get_llm()
    assert type(client).__module__ == "langchain_ollama.chat_models"
    assert str(client.base_url) == LOCAL_URL


# ------------------------------------------------------------------- chain wiring intact ----

def stub_client(monkeypatch, module, handler):
    """Give a module a cached stand-in client whose configuration signature still matches."""
    from langchain_core.runnables import RunnableLambda

    monkeypatch.setattr(module, "_llm", RunnableLambda(handler), raising=False)
    monkeypatch.setattr(module, "_cached_signature", llm_client.cache_signature(), raising=False)


def test_the_hr_evaluator_has_only_one_provider_mechanism_left():
    """The bug was two dotenv readers disagreeing with the settings object, in three modules."""
    import inspect

    for name, module in EVALUATORS:
        source = inspect.getsource(module)
        assert "dotenv" not in source, f"{name} still resolves configuration a second time"
        assert "upload_dir.parent" not in source, f"{name} derives a path from the uploads directory"
        assert "startswith(\"sk-\")" not in source, f"{name} still treats a credential as a selector"
        assert "chat_models import ChatOllama" not in source, \
            f"{name} still imports the Ollama client from the retired location"
    assert hasattr(llm_client, "build_chat_client"), "the shared builder must be the client factory"


def test_an_answer_still_flows_through_prompt_client_and_parser(monkeypatch):
    """The resolver change must not disturb scoring: a stand-in client answers, the chain runs.

    Nothing here contacts a provider -- the client is a RunnableLambda, so a green result means the
    prompt, the client slot and the parser are still wired the way they were.
    """
    from langchain_core.messages import AIMessage
    scored = {
        "overall_score": 88,
        "personal_ownership_score": 91,
        "ownership_critique": "Owned the rollback end to end.",
        "specificity_score": 84,
        "specificity_critique": "Gave the 12% to 0% figure.",
        "relevance_score": 90,
        "relevance_critique": "Answered the outage question asked.",
        "coaching_feedback": "Add the root cause next time.",
        "ideal_star_script": "When the deploy broke checkout, I reproduced it in staging.",
        "star_structure": {
            "situation": {"present": True, "summary": "Checkout failing after a deploy."},
            "task": {"present": True, "summary": "Restore checkout."},
            "action": {"present": True, "summary": "Rolled back behind a flag."},
            "result": {"present": True, "summary": "Failures 12% to 0%."},
            "completeness_score": 86,
            "structure_critique": "Complete STAR.",
        },
    }
    seen: list = []

    def fake_client(payload):
        seen.append(payload)
        return AIMessage(content=json.dumps(dict(scored)))

    configure(monkeypatch, provider="ollama", key="")
    stub_client(monkeypatch, evaluator, fake_client)

    import asyncio
    result = asyncio.run(evaluator.evaluate_hr_answer(
        role="Backend Engineer", company="Acme", track="Ownership",
        question="Tell me about a time you handled a production outage.",
        candidate_answer="Our checkout failed after a pricing deploy, so I rolled it back and "
                         "wrote the runbook."))
    assert result["evaluator_basis"] == "model"
    assert result["overall_score"] == 88
    assert OpenRouterRecorder.built == [] and OllamaRecorder.built == []
    assert len(seen) == 1, "the prompt should reach the client exactly once"


def test_the_report_contract_fields_are_unchanged(monkeypatch):
    from langchain_core.messages import AIMessage

    def fake_report(payload):
        return AIMessage(content=json.dumps(report_payload))

    report_payload = {
        "total_score": 85, "avg_ownership_score": 87, "avg_star_completeness": 82,
        "avg_specificity_score": 84, "strengths": ["Quantified impact."],
        "weaknesses": ["Name the root cause."], "executive_summary": "Strong ownership shown.",
    }
    configure(monkeypatch, provider="ollama", key="")
    stub_client(monkeypatch, evaluator, fake_report)

    import asyncio
    report = asyncio.run(evaluator.generate_hr_report(
        role="Backend Engineer", company="Acme",
        questions_asked=[{"text": "Q", "answer": "A", "track": "Ownership",
                          "evaluation": {"overall_score": 85, "personal_ownership_score": 87,
                                         "star_structure": {"completeness_score": 82},
                                         "specificity_score": 84, "evaluator_basis": "model"}}]))
    assert report["report_basis"] == "model"
    assert report["total_score"] == 85
    assert report["answers_not_model_scored"] == 0
    assert OpenRouterRecorder.built == []


# ------------------------------------------------- the same rule in every migrated module ----

@pytest.mark.parametrize("name,module", EVALUATORS)
def test_local_is_the_default_everywhere(name, module, monkeypatch):
    configure(monkeypatch, provider="ollama", key=CANARY)
    assert isinstance(module._get_llm(), OllamaRecorder), name
    assert OpenRouterRecorder.built == [], name


@pytest.mark.parametrize("name,module", EVALUATORS)
def test_openrouter_is_built_everywhere_only_when_configured(name, module, monkeypatch):
    configure(monkeypatch, provider="openrouter", key=CANARY)
    assert isinstance(module._get_llm(), OpenRouterRecorder), name
    assert OllamaRecorder.built == [], name


@pytest.mark.parametrize("name,module", EVALUATORS)
def test_a_missing_credential_raises_everywhere_instead_of_substituting(name, module, monkeypatch):
    configure(monkeypatch, provider="openrouter", key="")
    with pytest.raises(RuntimeError, match="LLM_PROVIDER"):
        module._get_llm()
    assert OllamaRecorder.built == [] and OpenRouterRecorder.built == []


@pytest.mark.parametrize("name,module", EVALUATORS)
def test_a_broken_local_integration_never_becomes_a_remote_call(name, module, monkeypatch):
    configure(monkeypatch, provider="ollama", key=CANARY)
    monkeypatch.setitem(sys.modules, "langchain_ollama", None)
    monkeypatch.setitem(sys.modules, "langchain_community", None)
    monkeypatch.setitem(sys.modules, "langchain_community.chat_models", None)
    with pytest.raises(ImportError, match="langchain-ollama"):
        module._get_llm()
    assert OpenRouterRecorder.built == []


@pytest.mark.parametrize("name,module", EVALUATORS)
def test_each_module_keeps_its_own_client_parameters(name, module, monkeypatch):
    """Migration must not silently change temperature or answer budget per round."""
    configure(monkeypatch, provider="ollama", key="")
    module._get_llm()
    ollama_kwargs = OllamaRecorder.built[-1]
    assert ollama_kwargs["temperature"] == module.CLIENT_TEMPERATURE
    assert ollama_kwargs["model"] == LOCAL_MODEL

    configure(monkeypatch, provider="openrouter", key=CANARY)
    module._get_llm()
    remote_kwargs = OpenRouterRecorder.built[-1]
    assert remote_kwargs["temperature"] == module.CLIENT_TEMPERATURE
    assert remote_kwargs["max_tokens"] == module.CLIENT_MAX_TOKENS
    assert remote_kwargs["api_key"] == CANARY
    if ollama_kwargs["temperature"] == 0.6:
        assert remote_kwargs["max_tokens"] == 2500
    else:
        assert remote_kwargs["max_tokens"] == 2048


# ---------------------------------------------------------------- technical memory service ----

def test_memory_uses_the_local_endpoint_and_a_placeholder_credential_by_default(monkeypatch):
    from app.services.technical import memory

    configure(monkeypatch, provider="ollama", key=CANARY)
    llm_config = memory._llm_config()
    assert llm_config["config"]["openai_base_url"] == LOCAL_URL + "/v1"
    assert llm_config["config"]["model"] == LOCAL_MODEL
    assert llm_config["config"]["api_key"] == "sk-dummy-local", "the deployment key must stay unused"


def test_memory_reaches_openrouter_only_when_the_provider_says_so(monkeypatch):
    from app.services.technical import memory

    configure(monkeypatch, provider="openrouter", key=CANARY)
    llm_config = memory._llm_config()
    assert llm_config["config"]["openai_base_url"] == "https://openrouter.ai/api/v1"
    assert llm_config["config"]["api_key"] == CANARY

    configure(monkeypatch, provider="openrouter", key="")
    with pytest.raises(RuntimeError, match="LLM_PROVIDER"):
        memory._llm_config()
