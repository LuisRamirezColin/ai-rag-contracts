"""Composition root, shared part: settings, database engine and shared adapters.

The composition root is split by process so each one only loads what it wires:
``bootstrap.writer`` for the pipelines and ``bootstrap.reader`` for the API, both
built on the ``CoreContainer`` defined here. The API never imports the writer
module, so the index write port is unreachable from it (import contracts).

Every outbound port is a ``Selector`` between its in-memory fake and its real
adapter, keyed by ``settings.use_fakes``; providers are lazy, so building a
container performs no I/O.
"""

from dependency_injector import containers, providers
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from contract_intel.adapters.outbound.in_memory.contract_repository import (
    InMemoryContractRepository,
)
from contract_intel.adapters.outbound.in_memory.embedder import InMemoryEmbedder
from contract_intel.adapters.outbound.in_memory.usage_tracker import (
    InMemoryUsageTracker,
)
from contract_intel.adapters.outbound.in_memory.vector_index import (
    InMemoryVectorStore,
)
from contract_intel.adapters.outbound.persistence.contract_repository import (
    SqlAlchemyContractRepository,
)
from contract_intel.adapters.outbound.persistence.usage_tracker import (
    SqlAlchemyUsageTracker,
)
from contract_intel.adapters.outbound.voyage.voyage_embedder import (
    VoyageConfig,
    VoyageEmbedder,
)
from contract_intel.bootstrap.settings import AppSettings

FAKE = "fake"
REAL = "real"


def adapter_mode(settings: AppSettings) -> str:
    """Return which branch of every port selector to use."""
    return FAKE if settings.use_fakes else REAL


def _engine(settings: AppSettings, null_pool: bool) -> AsyncEngine:
    # The writer uses NullPool: each Dagster materialization runs its own event
    # loop, and pooled asyncpg connections cannot outlive the loop that opened them.
    if null_pool:
        return create_async_engine(settings.database.url, poolclass=NullPool)
    return create_async_engine(
        settings.database.url, pool_size=settings.database.pool_size
    )


def _voyage_config(settings: AppSettings) -> VoyageConfig:
    embeddings = settings.embeddings
    return VoyageConfig(
        api_key=embeddings.api_key.get_secret_value(),
        model=embeddings.model,
        dimensions=embeddings.dimensions,
        max_retries=embeddings.max_retries,
    )


class CoreContainer(containers.DeclarativeContainer):
    """Adapters shared by both the writer and the reader side."""

    settings = providers.Dependency(instance_of=AppSettings)
    use_null_pool = providers.Object(False)
    mode = providers.Callable(adapter_mode, settings)
    database_engine = providers.Singleton(_engine, settings, use_null_pool)
    session_factory = providers.Singleton(async_sessionmaker, database_engine)
    vector_store = providers.Singleton(InMemoryVectorStore)
    embedder = providers.Selector(
        mode,
        fake=providers.Singleton(
            InMemoryEmbedder, settings.provided.embeddings.dimensions
        ),
        real=providers.Singleton(
            VoyageEmbedder, providers.Callable(_voyage_config, settings)
        ),
    )
    contract_repository = providers.Selector(
        mode,
        fake=providers.Singleton(InMemoryContractRepository),
        real=providers.Singleton(SqlAlchemyContractRepository, session_factory),
    )
    usage_tracker = providers.Selector(
        mode,
        fake=providers.Singleton(InMemoryUsageTracker),
        real=providers.Singleton(SqlAlchemyUsageTracker, session_factory),
    )
