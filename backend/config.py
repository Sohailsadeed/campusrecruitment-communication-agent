"""Application configuration using pydantic-settings."""
from pathlib import Path
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # App
    app_name: str = "SpeakFlow API"
    app_version: str = "0.1.0"
    debug: bool = False

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
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3.5:4b"
    llm_timeout_seconds: int = 60

    # Whisper
    whisper_model_name: str = "base"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()
