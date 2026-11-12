from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "InfoFlow AI"
    app_version: str = "1.0.0"
    environment: Literal["development", "production", "test"] = "development"
    debug: bool = False
    api_prefix: str = "/api"
    cors_origins: str = "*"

    secret_key: str = "change-me-in-production-please-use-a-long-random-string"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7

    database_url: str = f"sqlite:///{(BASE_DIR / 'data' / 'infoflow.db').as_posix()}"
    auto_create_tables: bool = True

    data_dir: Path = BASE_DIR / "data"
    upload_dir: Path | None = None
    chroma_path: Path | None = None
    vector_backend: Literal["auto", "local", "chroma"] = "auto"
    chroma_collection: str = "infoflow_chunks"

    use_celery: bool = False
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str | None = None
    celery_result_backend: str | None = None

    ai_provider: Literal["auto", "openrouter", "ollama", "openai", "none"] = "auto"
    ai_base_url: str | None = None
    ai_api_key: str | None = None
    ai_model: str = "openai/gpt-4o-mini"
    ai_timeout_seconds: float = 60.0
    ai_max_input_chars: int = 14000

    openrouter_api_key: str | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "openai/gpt-4o-mini"

    ollama_base_url: str = "http://localhost:11434/v1"
    ollama_model: str = "llama3.1"

    embedding_provider: Literal["auto", "local", "sentence", "ollama", "hash"] = "auto"
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    embedding_dim: int = 384
    ollama_embedding_model: str = "nomic-embed-text"

    ingestion_timeout_seconds: float = 30.0
    jina_api_key: str | None = None
    jina_reader_url: str = "https://r.jina.ai"
    max_content_chars: int = 300_000
    max_upload_mb: int = 25
    allow_private_urls: bool = False

    chunk_size: int = 1000
    chunk_overlap: int = 150
    max_chunks_per_item: int = 120

    search_candidate_limit: int = 40
    rrf_k: int = 60

    search_semantic_min_score: float = 0.3

    search_semantic_relative_cutoff: float = 0.65

    search_hash_min_score: float = 0.12

    telegram_bot_token: str | None = None
    telegram_auto_provision: bool = True

    transcription_base_url: str = "https://api.openai.com/v1"
    transcription_api_key: str | None = None
    transcription_model: str = "whisper-1"

    @field_validator("secret_key")
    @classmethod
    def _warn_short_secret(cls, value: str) -> str:
        if len(value) < 16:
            raise ValueError("SECRET_KEY должен содержать минимум 16 символов")
        return value

    @model_validator(mode="after")
    def _derive_paths(self) -> "Settings":
        if self.upload_dir is None:
            self.upload_dir = self.data_dir / "uploads"
        if self.chroma_path is None:
            self.chroma_path = self.data_dir / "chroma"
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        raw = self.cors_origins.strip()
        if raw == "*":
            return ["*"]
        return [origin.strip() for origin in raw.split(",") if origin.strip()]

    @property
    def vector_dir(self) -> Path:
        return self.data_dir / "vectors"

    @property
    def effective_ai_provider(self) -> str:
        provider = self.ai_provider
        if provider == "none":
            return "none"
        if provider == "auto":
            if self.openrouter_api_key:
                return "openrouter"
            if self.ai_base_url and self.ai_api_key:
                return "openai"
            return "heuristic"
        if provider == "openrouter" and not self.openrouter_api_key:
            return "heuristic"
        if provider == "openai" and not (self.ai_base_url and self.ai_api_key):
            return "heuristic"
        return provider

@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

def ensure_directories(settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    for path in (settings.data_dir, settings.upload_dir, settings.chroma_path, settings.vector_dir):
        if path is not None:
            Path(path).mkdir(parents=True, exist_ok=True)
    if settings.database_url.startswith("sqlite:///"):
        db_path = Path(settings.database_url.removeprefix("sqlite:///"))
        db_path.parent.mkdir(parents=True, exist_ok=True)

def reset_settings_cache() -> None:
    get_settings.cache_clear()
