"""Application configuration and environment settings."""

from pathlib import Path
from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for E.D.I.T.H. Brain Core."""

    model_config = SettingsConfigDict(
        env_prefix="EDITH_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "E.D.I.T.H. Brain Core"
    app_version: str = "0.1.0"
    environment: str = "development"

    # Base Paths
    base_dir: Path = Field(default_factory=lambda: Path("D:/edith-brain-core"))
    database_path: Path = Field(
        default_factory=lambda: Path("D:/edith-brain-core/data/db/brain_core.db")
    )
    storage_raw_dir: Path = Field(
        default_factory=lambda: Path("D:/edith-brain-core/data/storage/raw")
    )
    storage_extracted_dir: Path = Field(
        default_factory=lambda: Path("D:/edith-brain-core/data/storage/extracted")
    )

    # Document upload boundaries (B0 default: 10 MB)
    max_file_size_bytes: int = 10 * 1024 * 1024

    # SQLite Concurrency Controls
    sqlite_busy_timeout_ms: int = 5000

    # API Server Defaults (Local-first)
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    auth_enabled: bool = True
    local_auth_secret: str | None = None
    local_token_path: Path = Field(
        default_factory=lambda: Path("D:/edith-brain-core/data/.edith_token")
    )

    # Retrieval & Embedding Configuration
    embedding_provider: str = "deterministic"  # "deterministic" or "fastembed"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dimensions: int = 384
    default_retrieval_mode: str = "hybrid"  # "hybrid", "keyword", "semantic"
    retrieval_top_k: int = 5
    rrf_k_parameter: int = 60  # Standard Reciprocal Rank Fusion constant

    def ensure_directories(self) -> None:
        """Ensure all required local data and storage directories exist."""
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.storage_raw_dir.mkdir(parents=True, exist_ok=True)
        self.storage_extracted_dir.mkdir(parents=True, exist_ok=True)


@lru_cache()
def get_settings() -> Settings:
    """Provide cached settings instance."""
    settings = Settings()
    settings.ensure_directories()
    return settings
