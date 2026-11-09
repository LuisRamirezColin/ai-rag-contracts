from pathlib import Path
from typing import Literal, Self

from pydantic import (
    BaseModel,
    NonNegativeInt,
    PositiveFloat,
    PositiveInt,
    SecretStr,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_PREFIX = "CONTRACT_INTEL_"
DEFAULT_CUAD_DIR = Path("data/cuad/CUAD_v1/full_contract_pdf")
DEFAULT_MAX_DOCUMENTS = 5
DEFAULT_EMBEDDING_MODEL = "voyage-law-2"
DEFAULT_EMBEDDING_DIMENSIONS = 1024
DEFAULT_EMBEDDING_PRICE_PER_MILLION_TOKENS = 0.12
DEFAULT_EMBEDDING_MAX_RETRIES = 3
DEFAULT_CHUNK_MAX_CHARS = 2000
DEFAULT_CHUNK_OVERLAP_CHARS = 200
DEFAULT_CHAT_MODEL = "claude-sonnet-5-5"
DEFAULT_ANSWER_MAX_TOKENS = 16000
DEFAULT_CHAT_INPUT_PRICE_PER_MILLION = 2.0
DEFAULT_CHAT_OUTPUT_PRICE_PER_MILLION = 10.0
DEFAULT_TOP_K = 8

Effort = Literal["low", "medium", "high", "xhigh", "max"]
DEFAULT_EFFORT: Effort = "medium"


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
    """Claude settings for answer generation.

    An empty ``api_key`` lets the Anthropic SDK resolve its default credentials.
    """

    api_key: SecretStr = SecretStr("")
    chat_model: str = DEFAULT_CHAT_MODEL
    effort: Effort = DEFAULT_EFFORT
    max_tokens: PositiveInt = DEFAULT_ANSWER_MAX_TOKENS
    input_price_per_million: PositiveFloat = DEFAULT_CHAT_INPUT_PRICE_PER_MILLION
    output_price_per_million: PositiveFloat = DEFAULT_CHAT_OUTPUT_PRICE_PER_MILLION
    fallbacks: bool = False


class RetrievalSettings(BaseModel):
    """How many chunks are retrieved as context for each question."""

    top_k: PositiveInt = DEFAULT_TOP_K


class IngestionSettings(BaseModel):
    """Where contracts come from and how many of them the demo ingests."""

    cuad_dir: Path = DEFAULT_CUAD_DIR
    max_documents: PositiveInt = DEFAULT_MAX_DOCUMENTS


class EmbeddingsSettings(BaseModel):
    """Embedding model used to index chunks and encode queries."""

    api_key: SecretStr = SecretStr("")
    model: str = DEFAULT_EMBEDDING_MODEL
    dimensions: PositiveInt = DEFAULT_EMBEDDING_DIMENSIONS
    price_per_million_tokens: PositiveFloat = DEFAULT_EMBEDDING_PRICE_PER_MILLION_TOKENS
    max_retries: NonNegativeInt = DEFAULT_EMBEDDING_MAX_RETRIES


class ChunkingSettings(BaseModel):
    """Size of the text windows that become retrievable chunks."""

    max_chars: PositiveInt = DEFAULT_CHUNK_MAX_CHARS
    overlap_chars: NonNegativeInt = DEFAULT_CHUNK_OVERLAP_CHARS

    @model_validator(mode="after")
    def _overlap_smaller_than_window(self) -> Self:
        if self.overlap_chars >= self.max_chars:
            raise ValueError("overlap_chars must be smaller than max_chars")
        return self


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
    embeddings: EmbeddingsSettings = EmbeddingsSettings()
    chunking: ChunkingSettings = ChunkingSettings()
    retrieval: RetrievalSettings = RetrievalSettings()
