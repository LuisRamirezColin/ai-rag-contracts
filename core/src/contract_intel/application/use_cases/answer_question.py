from collections.abc import Sequence
from dataclasses import replace

from contract_intel.application.ports.outbound.answer_generator import AnswerGenerator
from contract_intel.application.ports.outbound.embedder import Embedder
from contract_intel.application.ports.outbound.usage_tracker import UsageTracker
from contract_intel.application.ports.outbound.vector_search import VectorSearch
from contract_intel.domain.answer import Answer, Citation
from contract_intel.domain.chunk import ScoredChunk
from contract_intel.domain.clause_type import ClauseType
from contract_intel.domain.usage import TokenPricing, UsageRecord

ANSWER_QUESTION_OPERATION = "answer_question"
NO_INFORMATION_ANSWER = "No relevant information was found in the indexed contracts."
MIN_TOP_K = 1


class AnswerQuestionUseCase:
    """Retrieve the chunks most similar to a question and answer from them only."""

    def __init__(
        self,
        embedder: Embedder,
        search: VectorSearch,
        generator: AnswerGenerator,
        usage_tracker: UsageTracker,
        pricing: TokenPricing,
        top_k: int,
    ) -> None:
        if top_k < MIN_TOP_K:
            raise ValueError(f"top_k must be >= {MIN_TOP_K}")
        self._embedder = embedder
        self._search = search
        self._generator = generator
        self._usage_tracker = usage_tracker
        self._pricing = pricing
        self._top_k = top_k

    async def execute(
        self,
        question: str,
        clause_types: frozenset[ClauseType] = frozenset(),
    ) -> Answer:
        """Answer ``question``, optionally restricted to ``clause_types``.

        Raises:
            AnswerRefusedError: If the model declines to answer.
            ProviderRateLimitedError: If a provider rejects a call for limits.
            ProviderUnavailableError: If a provider cannot be reached or fails.
        """
        query = await self._embedder.embed_query(question)
        context = await self._search.search(query, self._top_k, clause_types)
        if not context:
            return Answer(question=question, text=NO_INFORMATION_ANSWER)
        generated = await self._generator.generate(question, context)
        await self._usage_tracker.record(
            UsageRecord(
                operation=ANSWER_QUESTION_OPERATION,
                model=generated.model,
                input_tokens=generated.input_tokens,
                output_tokens=generated.output_tokens,
                cost_usd=self._pricing.cost_usd(
                    generated.input_tokens, generated.output_tokens
                ),
            )
        )
        answer = generated.answer
        grounded = tuple(c for c in answer.citations if _is_grounded(c, context))
        return replace(answer, citations=grounded)


def _is_grounded(citation: Citation, context: Sequence[ScoredChunk]) -> bool:
    return any(
        item.chunk.document_id == citation.document_id
        and item.chunk.pages.first <= citation.pages.first
        and citation.pages.last <= item.chunk.pages.last
        for item in context
    )
