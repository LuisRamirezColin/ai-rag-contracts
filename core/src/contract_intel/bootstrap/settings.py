from pathlib import Path

from pydantic import BaseModel, PositiveInt, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_PREFIX = "CONTRACT_INTEL_"
DEFAULT_CUAD_DIR = Path("data/cuad/CUAD_v1/full_contract_pdf")
DEFAULT_MAX_DOCUMENTS = 5


class DatabaseSettings(BaseModel):
    """Postgres connection settings."""

    url: str = "postgresql+asyncpg://contract_intel:contract_intel@localhost:5432/contract_intel"
    pool_size: int = 5


class StorageSettings(BaseModel):
    """S3-compatible object storage settings."""

    bucket: str = "contracts"
    endpoint_url: str | None = None
    region: str = "us-east-1"
    access_key_id: SecretStr | None = None
    secret_access_key: SecretStr | None = None


class LlmSettings(BaseModel):
    """LLM provider settings."""

    api_key: SecretStr = SecretStr("")
    chat_model: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-3-small"


class IngestionSettings(BaseModel):
    """Where contracts come from and how many of them the demo ingests."""

    cuad_dir: Path = DEFAULT_CUAD_DIR
    max_documents: PositiveInt = DEFAULT_MAX_DOCUMENTS


class AppSettings(BaseSettings):
    """Application settings loaded from ``CONTRACT_INTEL_*`` environment variables.

    Nested sections use ``__`` as delimiter, e.g. ``CONTRACT_INTEL_DATABASE__URL``.
    """

    model_config = SettingsConfigDict(
        env_prefix=ENV_PREFIX,
        env_nested_delimiter="__",
        env_file=".env",
        extra="ignore",
    )

    use_fakes: bool = True
    database: DatabaseSettings = DatabaseSettings()
    storage: StorageSettings = StorageSettings()
    llm: LlmSettings = LlmSettings()
    ingestion: IngestionSettings = IngestionSettings()
