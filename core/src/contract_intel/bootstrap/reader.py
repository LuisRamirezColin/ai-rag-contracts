"""Composition root of the API: read-only access to the vector index."""

from dependency_injector import containers, providers

from contract_intel.adapters.outbound.anthropic.anthropic_answer_generator import (
    AnthropicAnswerGenerator,
    AnthropicConfig,
)
from contract_intel.adapters.outbound.in_memory.answer_generator import (
    InMemoryAnswerGenerator,
)
from contract_intel.adapters.outbound.in_memory.vector_index import (
    InMemoryVectorSearch,
)
from contract_intel.adapters.outbound.persistence.vector_search import PgVectorSearch
from contract_intel.application.use_cases.answer_question import (
    AnswerQuestionUseCase,
)
from contract_intel.bootstrap.core import CoreContainer
from contract_intel.bootstrap.settings import AppSettings
from contract_intel.domain.usage import TokenPricing


def _anthropic_config(settings: AppSettings) -> AnthropicConfig:
    llm = settings.llm
    return AnthropicConfig(
        api_key=llm.api_key.get_secret_value() or None,
        model=llm.chat_model,
        effort=llm.effort,
        max_tokens=llm.max_tokens,
        fallbacks=llm.fallbacks,
    )


def _chat_pricing(settings: AppSettings) -> TokenPricing:
    return TokenPricing(
        input_per_million=settings.llm.input_price_per_million,
        output_per_million=settings.llm.output_price_per_million,
    )


class ReaderContainer(containers.DeclarativeContainer):
    """Adapters and use cases of the API; it deliberately exposes no index writer."""

    core = providers.Container(CoreContainer)
    vector_search = providers.Selector(
        core.mode,
        fake=providers.Singleton(InMemoryVectorSearch, store=core.vector_store),
        real=providers.Singleton(PgVectorSearch, core.session_factory),
    )
    answer_generator = providers.Selector(
        core.mode,
        fake=providers.Singleton(InMemoryAnswerGenerator),
        real=providers.Singleton(
            AnthropicAnswerGenerator,
            providers.Callable(_anthropic_config, core.settings),
        ),
    )
    answer_question = providers.Factory(
        AnswerQuestionUseCase,
        embedder=core.embedder,
        search=vector_search,
        generator=answer_generator,
        usage_tracker=core.usage_tracker,
        pricing=providers.Callable(_chat_pricing, core.settings),
        top_k=core.settings.provided.retrieval.top_k,
    )


def build_reader_container(settings: AppSettings | None = None) -> ReaderContainer:
    """Build the API's container; providers are lazy (no I/O here)."""
    container = ReaderContainer()
    container.core.settings.override(settings or AppSettings())
    return container
