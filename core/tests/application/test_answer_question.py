import pytest

from contract_intel.adapters.outbound.in_memory.answer_generator import (
    IN_MEMORY_CHAT_MODEL,
    InMemoryAnswerGenerator,
)
from contract_intel.adapters.outbound.in_memory.embedder import InMemoryEmbedder
from contract_intel.adapters.outbound.in_memory.usage_tracker import (
    InMemoryUsageTracker,
)
from contract_intel.adapters.outbound.in_memory.vector_index import (
    InMemoryVectorIndexWriter,
    InMemoryVectorSearch,
    InMemoryVectorStore,
)
from contract_intel.application.ports.inbound.answer_question import AnswerQuestion
from contract_intel.application.use_cases.answer_question import (
    ANSWER_QUESTION_OPERATION,
    NO_INFORMATION_ANSWER,
    AnswerQuestionUseCase,
)
from contract_intel.domain.answer import Answer, Citation, GeneratedAnswer
from contract_intel.domain.chunk import Chunk, EmbeddedChunk
from contract_intel.domain.clause_type import ClauseType
from contract_intel.domain.errors import ProviderRateLimitedError
from contract_intel.domain.ids import ChunkId, DocumentId
from contract_intel.domain.page import PageRange
from contract_intel.domain.usage import TokenPricing

DOC_A = DocumentId("doc-a")
DOC_B = DocumentId("doc-b")
PRICING = TokenPricing(input_per_million=2.0, output_per_million=10.0)
QUESTION = "Which law governs the agreement?"


class SpyGenerator(InMemoryAnswerGenerator):
    def __init__(self):
        self.calls: list[int] = []

    async def generate(self, question, context):
        self.calls.append(len(context))
        return await super().generate(question, context)


class ForeignCitationGenerator(InMemoryAnswerGenerator):
    async def generate(self, question, context):
        generated = await super().generate(question, context)
        foreign = Citation(DocumentId("elsewhere"), PageRange.single(1), "made up")
        answer = Answer(
            question, generated.answer.text, (*generated.answer.citations, foreign)
        )
        return GeneratedAnswer(answer, generated.model, 10, 5)


class RateLimitedEmbedder(InMemoryEmbedder):
    async def embed_query(self, text):
        raise ProviderRateLimitedError("voyage", "3 RPM")


@pytest.fixture
def embedder():
    return InMemoryEmbedder()


@pytest.fixture
def store():
    return InMemoryVectorStore()


@pytest.fixture
def tracker():
    return InMemoryUsageTracker()


async def _index(store, embedder, document_id, ordinal, text, clause_type=None):
    chunk = Chunk(
        ChunkId(f"{document_id}:{ordinal:04d}"),
        document_id,
        text,
        PageRange(ordinal + 1, ordinal + 2),
        clause_type,
    )
    existing = [e for e in store.entries.values() if e.chunk.document_id == document_id]
    (vector,) = (await embedder.embed_documents([text])).embeddings
    await InMemoryVectorIndexWriter(store).replace_document(
        document_id, [*existing, EmbeddedChunk(chunk, vector)]
    )


def _use_case(embedder, store, tracker, generator=None, top_k=8):
    return AnswerQuestionUseCase(
        embedder,
        InMemoryVectorSearch(store),
        generator or InMemoryAnswerGenerator(),
        tracker,
        PRICING,
        top_k,
    )


def test_satisfies_inbound_port(embedder, store, tracker):
    assert isinstance(_use_case(embedder, store, tracker), AnswerQuestion)


async def test_answers_with_citations_from_the_context(embedder, store, tracker):
    await _index(store, embedder, DOC_A, 0, QUESTION)
    await _index(store, embedder, DOC_B, 0, "Termination for convenience")

    answer = await _use_case(embedder, store, tracker).execute(QUESTION)

    assert answer.text == QUESTION
    assert {c.document_id for c in answer.citations} == {DOC_A, DOC_B}
    assert answer.citations[0].pages == PageRange(1, 2)


async def test_empty_index_answers_no_information_without_the_model(
    embedder, store, tracker
):
    generator = SpyGenerator()

    answer = await _use_case(embedder, store, tracker, generator).execute(QUESTION)

    assert answer.text == NO_INFORMATION_ANSWER
    assert answer.citations == ()
    assert generator.calls == []
    assert tracker.records == []


async def test_clause_types_filter_the_context(embedder, store, tracker):
    await _index(store, embedder, DOC_A, 0, "law", ClauseType.GOVERNING_LAW)
    await _index(store, embedder, DOC_B, 0, "compete", ClauseType.NON_COMPETE)

    answer = await _use_case(embedder, store, tracker).execute(
        QUESTION, frozenset({ClauseType.NON_COMPETE})
    )

    assert [c.document_id for c in answer.citations] == [DOC_B]


async def test_top_k_limits_the_context(embedder, store, tracker):
    for ordinal in range(5):
        await _index(store, embedder, DOC_A, ordinal, f"clause {ordinal}")
    generator = SpyGenerator()

    await _use_case(embedder, store, tracker, generator, top_k=3).execute(QUESTION)

    assert generator.calls == [3]


async def test_usage_is_recorded_with_cost(embedder, store, tracker):
    await _index(store, embedder, DOC_A, 0, "Governed by the laws of New York.")

    await _use_case(embedder, store, tracker).execute(QUESTION)

    (usage,) = tracker.records
    assert usage.operation == ANSWER_QUESTION_OPERATION
    assert usage.model == IN_MEMORY_CHAT_MODEL
    assert usage.cost_usd == pytest.approx(
        PRICING.cost_usd(usage.input_tokens, usage.output_tokens)
    )


async def test_citations_outside_the_context_are_dropped(embedder, store, tracker):
    await _index(store, embedder, DOC_A, 0, "Governed by the laws of New York.")
    use_case = _use_case(embedder, store, tracker, ForeignCitationGenerator())

    answer = await use_case.execute(QUESTION)

    assert [c.document_id for c in answer.citations] == [DOC_A]


async def test_provider_errors_propagate_without_usage(store, tracker):
    use_case = _use_case(RateLimitedEmbedder(), store, tracker)

    with pytest.raises(ProviderRateLimitedError):
        await use_case.execute(QUESTION)

    assert tracker.records == []


def test_rejects_non_positive_top_k(embedder, store, tracker):
    with pytest.raises(ValueError, match="top_k"):
        _use_case(embedder, store, tracker, top_k=0)
