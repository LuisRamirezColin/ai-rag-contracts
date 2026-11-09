"""Composition root of the pipelines: the only writer of the vector index."""

from dependency_injector import containers, providers
from pydantic import SecretStr

from contract_intel.adapters.outbound.cuad.cuad_document_source import (
    CuadDocumentSource,
)
from contract_intel.adapters.outbound.in_memory.clause_extractor import (
    InMemoryClauseExtractor,
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
from contract_intel.adapters.outbound.in_memory.text_extractor import (
    InMemoryTextExtractor,
)
from contract_intel.adapters.outbound.in_memory.vector_index import (
    InMemoryVectorIndexWriter,
)
from contract_intel.adapters.outbound.pdf.pypdf_text_extractor import (
    PypdfTextExtractor,
)
from contract_intel.adapters.outbound.persistence.document_repository import (
    SqlAlchemyDocumentRepository,
)
from contract_intel.adapters.outbound.persistence.vector_index_writer import (
    PgVectorIndexWriter,
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
from contract_intel.application.use_cases.vectorize_document import (
    VectorizeDocumentUseCase,
)
from contract_intel.bootstrap.core import CoreContainer, not_implemented
from contract_intel.bootstrap.settings import AppSettings
from contract_intel.domain.chunking import ChunkingPolicy
from contract_intel.domain.usage import TokenPricing


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


def _chunking_policy(settings: AppSettings) -> ChunkingPolicy:
    return ChunkingPolicy(
        max_chars=settings.chunking.max_chars,
        overlap_chars=settings.chunking.overlap_chars,
    )


def _embedding_pricing(settings: AppSettings) -> TokenPricing:
    return TokenPricing(input_per_million=settings.embeddings.price_per_million_tokens)


class WriterContainer(containers.DeclarativeContainer):
    """Adapters and use cases of the pipelines, sole writer of the vector index."""

    core = providers.Container(CoreContainer, use_null_pool=providers.Object(True))

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
        real=providers.Singleton(SqlAlchemyDocumentRepository, core.session_factory),
    )
    clause_extractor = providers.Selector(
        core.mode,
        fake=providers.Singleton(InMemoryClauseExtractor),
        real=not_implemented("clause_extractor"),
    )
    vector_index_writer = providers.Selector(
        core.mode,
        fake=providers.Singleton(
            InMemoryVectorIndexWriter,
            store=core.vector_store,
            dimensions=core.settings.provided.embeddings.dimensions,
        ),
        real=providers.Singleton(
            PgVectorIndexWriter,
            core.session_factory,
            core.settings.provided.embeddings.model,
        ),
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
    vectorize_document = providers.Factory(
        VectorizeDocumentUseCase,
        repository=document_repository,
        embedder=core.embedder,
        writer=vector_index_writer,
        usage_tracker=core.usage_tracker,
        policy=providers.Callable(_chunking_policy, core.settings),
        pricing=providers.Callable(_embedding_pricing, core.settings),
    )


def build_writer_container(settings: AppSettings | None = None) -> WriterContainer:
    """Build the pipelines' container; providers are lazy (no I/O here)."""
    container = WriterContainer()
    container.core.settings.override(settings or AppSettings())
    return container
