"""Composition root of the API: read-only access to the vector index."""

from dependency_injector import containers, providers

from contract_intel.adapters.outbound.in_memory.answer_generator import (
    InMemoryAnswerGenerator,
)
from contract_intel.adapters.outbound.in_memory.vector_index import (
    InMemoryVectorSearch,
)
from contract_intel.bootstrap.core import CoreContainer, not_implemented
from contract_intel.bootstrap.settings import AppSettings


class ReaderContainer(containers.DeclarativeContainer):
    """Adapters used by the API; it deliberately exposes no index writer."""

    core = providers.Container(CoreContainer)
    vector_search = providers.Selector(
        core.mode,
        fake=providers.Singleton(InMemoryVectorSearch, store=core.vector_store),
        real=not_implemented("vector_search"),
    )
    answer_generator = providers.Selector(
        core.mode,
        fake=providers.Singleton(InMemoryAnswerGenerator),
        real=not_implemented("answer_generator"),
    )


def build_reader_container(settings: AppSettings | None = None) -> ReaderContainer:
    """Build the API's container; providers are lazy (no I/O here)."""
    container = ReaderContainer()
    container.core.settings.override(settings or AppSettings())
    return container
