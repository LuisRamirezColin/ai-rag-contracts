from pydantic import BaseModel, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_PREFIX = "CONTRACT_INTEL_"


class DatabaseSettings(BaseModel):
    """Postgres connection settings."""

    url: str = "postgresql+asyncpg://contract_intel:contract_intel@localhost:5432/contract_intel"
    pool_size: int = 5


class StorageSettings(BaseModel):
    """S3-compatible object storage settings."""

    bucket: str = "contracts"
    endpoint_url: str | None = None
    region: str = "us-east-1"


class LlmSettings(BaseModel):
    """LLM provider settings."""

    api_key: SecretStr = SecretStr("")
    chat_model: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-3-small"


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
