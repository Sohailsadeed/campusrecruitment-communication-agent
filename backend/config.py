"""Application configuration using pydantic-settings."""
from pathlib import Path
from typing import List

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR = BASE_DIR / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)
# Kokoro weights live here by convention, never in this repository and never fetched by the app.
KOKORO_DIR = BASE_DIR / "models" / "kokoro"

# Anchored to this file, not to the process working directory: a relative ".env" made the settings
# a running process saw depend on where it happened to be launched from, so a harness started in
# backend/ picked up the deployment's OpenRouter key and evaluated answers against a remote model.
ENV_FILE = BASE_DIR / ".env"

# The only providers that can be selected, and the setting that chooses between them. Presence of a
# credential is deliberately NOT a selector -- see resolve_llm_target().
LLM_PROVIDERS = ("ollama", "openrouter")

# The same rule for the coach's voice: TTS_PROVIDER chooses, and nothing else does. `kokoro` speaks
# locally from weights on disk; `edge` is the remote neural voice the app has always used.
TTS_PROVIDERS = ("kokoro", "edge")

# Kokoro's English G2P is per-accent ('a' American, 'b' British) and the voice pack has to match.
KOKORO_LANG_CODES = ("a", "b")
KOKORO_DEVICES = ("", "cpu", "cuda")


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # App
    app_name: str = "SpeakFlow API"
    app_version: str = "0.1.0"
    debug: bool = False
    logs_dir: Path = LOGS_DIR

    # Database
    database_url: str = f"sqlite:///{BASE_DIR / 'speakflow.db'}"

    # Security — must be set via SECRET_KEY env var; no insecure default
    secret_key: str = "CHANGE_ME_SET_SECRET_KEY_ENV_VAR_IN_PRODUCTION"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7  # 7 days

    # CORS
    cors_origins: List[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    # File uploads
    upload_dir: Path = UPLOAD_DIR
    max_upload_size_mb: int = 200

    # Ollama / LLM
    # The default provider is local: development and validation must not reach a paid API just
    # because a credential is present in the file.
    llm_provider: str = "ollama"
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3.5:4b"
    llm_timeout_seconds: int = 60

    # Whisper
    whisper_model_name: str = "base"

    # Text-to-speech — the coach's spoken voice (see app/services/tts.py).
    # Kokoro is primary because it answers out loud on this machine: a candidate's words never cross
    # a network to be spoken back. Edge TTS stays as the fallback because Kokoro needs both a runtime
    # in the venv and weights on disk, and the round should still speak when either is missing.
    tts_provider: str = "kokoro"
    tts_fallback_enabled: bool = True
    tts_fallback_provider: str = "edge"
    tts_edge_voice: str = "en-US-ChristopherNeural"
    # Paths, not repo lookups: the app reads whatever is already in these files and never fetches a
    # weight. See docs/tts-kokoro.md for how the files get there.
    tts_kokoro_model_path: Path = KOKORO_DIR / "kokoro-v1_0.pth"
    tts_kokoro_config_path: Path = KOKORO_DIR / "config.json"
    tts_kokoro_voices_dir: Path = KOKORO_DIR / "voices"
    tts_kokoro_repo_id: str = "hexgrad/Kokoro-82M"
    tts_kokoro_lang_code: str = "a"
    tts_kokoro_voice: str = "af_heart"
    tts_kokoro_speed: float = Field(default=1.0, ge=0.5, le=2.0)
    # Empty means let the runtime choose; "cpu" is the deterministic answer for a development box.
    tts_kokoro_device: str = ""

    # Technical Round (OpenRouter Nemotron / Ollama fallback, Redis, ChromaDB)
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    chat_model: str = "nvidia/nemotron-3-ultra-550b-a55b:free"
    redis_url: str = "redis://localhost:6379"
    chroma_host: str = "localhost"
    chroma_port: int = 8100
    resume_upload_dir: Path = UPLOAD_DIR / "resumes"

    # LiveKit — self-hosted WebRTC SFU (V1: browser microphone into a per-session HR room).
    # The key pair is read from the environment only, with no default: a half-configured
    # server must refuse to mint tokens rather than sign them with a placeholder value
    # anyone who has read this file could forge. LIVEKIT_API_SECRET never reaches a client.
    livekit_api_key: str = ""
    livekit_api_secret: str = ""
    # The URL the *browser* dials, returned by the token endpoint so the frontend never
    # hardcodes a host. ws:// for local development, wss:// behind a TLS proxy in a
    # deployment — the application holds no localhost assumption.
    livekit_url: str = ""
    livekit_token_ttl_minutes: int = Field(default=15, ge=1, le=1440)
    livekit_room_prefix: str = "speakflow"

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("llm_provider")
    @classmethod
    def _normalise_provider(cls, value: str) -> str:
        normalised = value.strip().lower()
        if normalised not in LLM_PROVIDERS:
            raise ValueError(
                f"LLM_PROVIDER must be one of {', '.join(LLM_PROVIDERS)}, got {value!r}")
        return normalised

    @field_validator("tts_provider", "tts_fallback_provider")
    @classmethod
    def _normalise_tts_provider(cls, value: str) -> str:
        normalised = value.strip().lower()
        if normalised not in TTS_PROVIDERS:
            raise ValueError(
                f"TTS provider must be one of {', '.join(TTS_PROVIDERS)}, got {value!r}")
        return normalised

    @field_validator("tts_kokoro_lang_code")
    @classmethod
    def _normalise_kokoro_lang_code(cls, value: str) -> str:
        normalised = value.strip().lower()
        if normalised not in KOKORO_LANG_CODES:
            raise ValueError(
                f"TTS_KOKORO_LANG_CODE must be one of {', '.join(KOKORO_LANG_CODES)}, got {value!r}")
        return normalised

    @field_validator("tts_kokoro_device")
    @classmethod
    def _normalise_kokoro_device(cls, value: str) -> str:
        normalised = value.strip().lower()
        if normalised not in KOKORO_DEVICES:
            raise ValueError(
                f"TTS_KOKORO_DEVICE must be one of {', '.join(KOKORO_DEVICES)}, got {value!r}")
        return normalised

    @model_validator(mode="after")
    def _check_tts_fallback(self) -> "Settings":
        """A fallback that names the provider it would fall back from is no fallback at all."""
        if self.tts_fallback_enabled and self.tts_fallback_provider == self.tts_provider:
            raise ValueError(
                "TTS_FALLBACK_PROVIDER must differ from TTS_PROVIDER, or "
                "TTS_FALLBACK_ENABLED must be false")
        return self

    def resolve_llm_target(self) -> dict:
        """Decide which provider an LLM-backed service must use, from configuration alone.

        A credential is never a selector: an OpenRouter key sitting in the deployment's .env leaves
        the local provider chosen, and a missing key does not move anything to OpenRouter either.
        Reports the presence of a credential rather than its value, so callers can refuse to run
        without ever handling the secret.
        """
        if self.llm_provider == "openrouter":
            return {
                "provider": "openrouter",
                "model": self.chat_model,
                "base_url": self.openrouter_base_url,
                "credential_present": bool(self.openrouter_api_key.strip()),
            }
        return {
            "provider": "ollama",
            "model": self.ollama_model,
            "base_url": self.ollama_base_url,
            "credential_present": True,
        }

    def provider_diagnostics(self) -> dict:
        """What an operator can be shown before running anything: endpoint and model, no secrets."""
        return {**self.resolve_llm_target(),
                "env_file": str(ENV_FILE),
                "openrouter_key_configured": bool(self.openrouter_api_key.strip())}


settings = Settings()
