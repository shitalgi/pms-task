from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Palm Mind AI RAG API"
    environment: str = "development"
    log_level: str = "INFO"
    database_url: str = "sqlite:///./data/app.db"
    openai_api_key: str = ""
    openai_chat_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = Field(default=1536, gt=0)
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str | None = None
    qdrant_collection: str = "documents"
    redis_url: str = "redis://localhost:6379/0"
    chat_history_turns: int = Field(default=12, ge=1, le=100)
    chat_memory_ttl_seconds: int = Field(default=86400, ge=60)
    max_upload_size_mb: int = Field(default=20, ge=1)
    max_chunk_size: int = Field(default=1000, ge=100)
    chunk_overlap: int = Field(default=150, ge=0)

    @model_validator(mode="after")
    def validate_chunk_overlap(self) -> "Settings":
        if self.chunk_overlap >= self.max_chunk_size:
            raise ValueError("chunk_overlap must be smaller than max_chunk_size")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
