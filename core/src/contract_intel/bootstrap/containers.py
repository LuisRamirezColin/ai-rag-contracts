"""Composition root: the only place that knows concrete adapters.

Two entry containers mirror the two RAG layers:

* ``WriterContainer`` for the pipelines (ingest, extract, embed, write index).
* ``ReaderContainer`` for the API; it deliberately exposes no index writer.

Every outbound port is a ``Selector`` between its in-memory fake and its real
adapter, keyed by ``settings.use_fakes``. Ports whose real adapter does not
exist yet raise ``RealAdaptersUnavailableError`` when resolved, never when the
container is built, so implemented real adapters are usable today.
"""

from typing import NoReturn

from dependency_injector import containers, providers
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from contract_intel.adapters.outbound.cuad.cuad_document_source import (
    CuadDocumentSource,
)
from contract_intel.adapters.outbound.in_memory.answer_generator import (
    InMemoryAnswerGenerator,
)
from contract_intel.adapters.outbound.in_memory.clause_extractor import (
    InMemoryClauseExtractor,
)
from contract_intel.adapters.outbound.in_memory.contract_repository import (
    InMemoryContractRepository,
)
from contract_intel.adapters.outbound.in_memory.document_repository import (
    InMemoryDocumentRepository,
)
from contract_intel.adapters.outbound.in_memory.document_source import (
    InMemoryDocumentSource,
)
from contract_intel.adapters.outbound.in_memory.document_storage import (
    InMemoryDocumentStorage,
)
from contract_intel.adapters.outbound.in_memory.embedder import InMemoryEmbedder
from contract_intel.adapters.outbound.in_memory.text_extractor import (
    InMemoryTextExtractor,
)
from contract_intel.adapters.outbound.in_memory.usage_tracker import (
    InMemoryUsageTracker,
)
from contract_intel.adapters.outbound.in_memory.vector_index import (
    InMemoryVectorIndexWriter,
    InMemoryVectorSearch,
    InMemoryVectorStore,
)
from contract_intel.adapters.outbound.pdf.pypdf_text_extractor import (
    PypdfTextExtractor,
)
from contract_intel.adapters.outbound.persistence.document_repository import (
    SqlAlchemyDocumentRepository,
)
from contract_intel.adapters.outbound.s3.s3_document_storage import (
    S3DocumentStorage,
    S3Location,
)
from contract_intel.application.use_cases.discover_documents import (
    DiscoverDocumentsUseCase,
)
from contract_intel.application.use_cases.ingest_document import (
    IngestDocumentUseCase,
)
from contract_intel.bootstrap.settings import AppSettings

FAKE = "fake"
REAL = "real"


class RealAdaptersUnavailableError(RuntimeError):
    """Raised when a port without a real adapter is resolved in real mode."""

    def __init__(self, port_name: str) -> None:
        super().__init__(
            f"No real adapter for port '{port_name}' yet; "
            "set CONTRACT_INTEL_USE_FAKES=true"
        )


def adapter_mode(settings: AppSettings) -> str:
    """Return which branch of every port selector to use."""
    return FAKE if settings.use_fakes else REAL


def _unavailable(port_name: str) -> NoReturn:
    raise RealAdaptersUnavailableError(port_name)


def _not_implemented(port_name: str) -> providers.Provider:  # type: ignore[type-arg]
    return providers.Callable(_unavailable, port_name)


def _writer_engine(settings: AppSettings) -> AsyncEngine:
    # NullPool: each Dagster materialization runs its own event loop, and pooled
    # asyncpg connections cannot outlive the loop that opened them.
    return create_async_engine(settings.database.url, poolclass=NullPool)


def _s3_location(settings: AppSettings) -> S3Location:
    storage = settings.storage
    return S3Location(
        bucket=storage.bucket,
        region=storage.region,
        endpoint_url=storage.endpoint_url,
        access_key_id=_reveal(storage.access_key_id),
        secret_access_key=_reveal(storage.secret_access_key),
    )


def _reveal(secret: SecretStr | None) -> str | None:
    return None if secret is None else secret.get_secret_value()


class CoreContainer(containers.DeclarativeContainer):
    """Adapters shared by both the writer and the reader side."""

    settings = providers.Dependency(instance_of=AppSettings)
    mode = providers.Callable(adapter_mode, settings)
    vector_store = providers.Singleton(InMemoryVectorStore)
    embedder = providers.Selector(
        mode,
        fake=providers.Singleton(InMemoryEmbedder),
        real=_not_implemented("embedder"),
    )
    contract_repository = providers.Selector(
        mode,
        fake=providers.Singleton(InMemoryContractRepository),
        real=_not_implemented("contract_repository"),
    )
    usage_tracker = providers.Selector(
        mode,
        fake=providers.Singleton(InMemoryUsageTracker),
        real=_not_implemented("usage_tracker"),
    )


class WriterContainer(containers.DeclarativeContainer):
    """Adapters and use cases of the pipelines, sole writer of the vector index."""

    core = providers.Container(CoreContainer)
    database_engine = providers.Singleton(_writer_engine, core.settings)
    session_factory = providers.Singleton(async_sessionmaker, database_engine)

    document_source = providers.Selector(
        core.mode,
        fake=providers.Singleton(InMemoryDocumentSource),
        real=providers.Singleton(
            CuadDocumentSource, core.settings.provided.ingestion.cuad_dir
        ),
    )
    document_storage = providers.Selector(
        core.mode,
        fake=providers.Singleton(InMemoryDocumentStorage),
        real=providers.Singleton(
            S3DocumentStorage, providers.Callable(_s3_location, core.settings)
        ),
    )
    text_extractor = providers.Selector(
        core.mode,
        fake=providers.Singleton(InMemoryTextExtractor),
        real=providers.Singleton(PypdfTextExtractor),
    )
    document_repository = providers.Selector(
        core.mode,
        fake=providers.Singleton(InMemoryDocumentRepository),
        real=providers.Singleton(SqlAlchemyDocumentRepository, session_factory),
    )
    clause_extractor = providers.Selector(
        core.mode,
        fake=providers.Singleton(InMemoryClauseExtractor),
        real=_not_implemented("clause_extractor"),
    )
    vector_index_writer = providers.Selector(
        core.mode,
        fake=providers.Singleton(InMemoryVectorIndexWriter, store=core.vector_store),
        real=_not_implemented("vector_index_writer"),
    )

    discover_documents = providers.Factory(
        DiscoverDocumentsUseCase,
        source=document_source,
        repository=document_repository,
        max_documents=core.settings.provided.ingestion.max_documents,
    )
    ingest_document = providers.Factory(
        IngestDocumentUseCase,
        source=document_source,
        storage=document_storage,
        extractor=text_extractor,
        repository=document_repository,
    )


class ReaderContainer(containers.DeclarativeContainer):
    """Adapters used by the API: read-only access to the vector index."""

    core = providers.Container(CoreContainer)
    vector_search = providers.Selector(
        core.mode,
        fake=providers.Singleton(InMemoryVectorSearch, store=core.vector_store),
        real=_not_implemented("vector_search"),
    )
    answer_generator = providers.Selector(
        core.mode,
        fake=providers.Singleton(InMemoryAnswerGenerator),
        real=_not_implemented("answer_generator"),
    )


def build_writer_container(settings: AppSettings | None = None) -> WriterContainer:
    """Build the pipelines' container; providers are lazy (no I/O here)."""
    container = WriterContainer()
    container.core.settings.override(settings or AppSettings())
    return container


def build_reader_container(settings: AppSettings | None = None) -> ReaderContainer:
    """Build the API's container; providers are lazy (no I/O here)."""
    container = ReaderContainer()
    container.core.settings.override(settings or AppSettings())
    return container
