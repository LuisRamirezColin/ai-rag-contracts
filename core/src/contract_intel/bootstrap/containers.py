"""Composition root: the only place that knows concrete adapters.

Two entry containers mirror the two RAG layers:

* ``WriterContainer`` for the pipelines (ingest, extract, embed, write index).
* ``ReaderContainer`` for the API; it deliberately exposes no index writer.
"""

from dependency_injector import containers, providers

from contract_intel.adapters.outbound.in_memory.answer_generator import (
    InMemoryAnswerGenerator,
)
from contract_intel.adapters.outbound.in_memory.clause_extractor import (
    InMemoryClauseExtractor,
)
from contract_intel.adapters.outbound.in_memory.contract_repository import (
    InMemoryContractRepository,
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
from contract_intel.bootstrap.settings import AppSettings


class RealAdaptersUnavailableError(RuntimeError):
    """Raised when real adapters are requested before they are implemented."""

    def __init__(self) -> None:
        super().__init__(
            "Real adapters are not available yet; set CONTRACT_INTEL_USE_FAKES=true"
        )


class CoreContainer(containers.DeclarativeContainer):
    """Adapters shared by both the writer and the reader side."""

    settings = providers.Dependency(instance_of=AppSettings)
    vector_store = providers.Singleton(InMemoryVectorStore)
    embedder = providers.Singleton(InMemoryEmbedder)
    contract_repository = providers.Singleton(InMemoryContractRepository)
    usage_tracker = providers.Singleton(InMemoryUsageTracker)


class WriterContainer(containers.DeclarativeContainer):
    """Adapters used by the pipelines, the sole writer of the vector index."""

    core = providers.Container(CoreContainer)
    document_source = providers.Singleton(InMemoryDocumentSource)
    document_storage = providers.Singleton(InMemoryDocumentStorage)
    text_extractor = providers.Singleton(InMemoryTextExtractor)
    clause_extractor = providers.Singleton(InMemoryClauseExtractor)
    vector_index_writer = providers.Singleton(
        InMemoryVectorIndexWriter, store=core.vector_store
    )


class ReaderContainer(containers.DeclarativeContainer):
    """Adapters used by the API: read-only access to the vector index."""

    core = providers.Container(CoreContainer)
    vector_search = providers.Singleton(InMemoryVectorSearch, store=core.vector_store)
    answer_generator = providers.Singleton(InMemoryAnswerGenerator)


def _resolve_settings(settings: AppSettings | None) -> AppSettings:
    resolved = settings or AppSettings()
    if not resolved.use_fakes:
        raise RealAdaptersUnavailableError
    return resolved


def build_writer_container(settings: AppSettings | None = None) -> WriterContainer:
    """Build the pipelines' container; providers are lazy (no I/O here)."""
    container = WriterContainer()
    container.core.settings.override(_resolve_settings(settings))
    return container


def build_reader_container(settings: AppSettings | None = None) -> ReaderContainer:
    """Build the API's container; providers are lazy (no I/O here)."""
    container = ReaderContainer()
    container.core.settings.override(_resolve_settings(settings))
    return container
