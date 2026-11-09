from contract_intel.adapters.outbound.in_memory.answer_generator import (
    NO_CONTEXT_ANSWER,
    InMemoryAnswerGenerator,
)
from contract_intel.adapters.outbound.in_memory.document_storage import (
    InMemoryDocumentStorage,
)
from contract_intel.adapters.outbound.in_memory.embedder import InMemoryEmbedder
from contract_intel.adapters.outbound.in_memory.text_extractor import (
    InMemoryTextExtractor,
)
from contract_intel.adapters.outbound.in_memory.vector_index import (
    InMemoryVectorIndexWriter,
    InMemoryVectorSearch,
    InMemoryVectorStore,
)
from contract_intel.domain.chunk import Chunk, EmbeddedChunk
from contract_intel.domain.clause_type import ClauseType
from contract_intel.domain.ids import ChunkId, DocumentId
from contract_intel.domain.page import PageRange

DOC_A = DocumentId("doc-a")
DOC_B = DocumentId("doc-b")


async def test_text_extractor_numbers_every_page():
    pages = await InMemoryTextExtractor().extract_pages(DOC_A, b"one\ftwo\fthree")
    assert [p.number for p in pages] == [1, 2, 3]
    assert [p.text for p in pages] == ["one", "two", "three"]


async def test_storage_reports_empty_files_as_missing():
    storage = InMemoryDocumentStorage()
    await storage.save(DOC_A, b"")
    assert not await storage.exists(DOC_A)
    await storage.save(DOC_A, b"%PDF")
    assert await storage.exists(DOC_A)


async def test_embedder_is_deterministic():
    embedder = InMemoryEmbedder(dimensions=4)
    batch = await embedder.embed_documents(["same", "same", "other"])
    first, second, other = batch.embeddings
    assert first == second
    assert await embedder.embed_query("same") == first
    assert batch.input_tokens > 0
    assert (embedder.document_calls, embedder.query_calls) == (1, 1)
    assert first != other
    assert first.dimensions == 4


async def _index(writer, embedder, chunk_id, document_id, text, clause_type):
    chunk = Chunk(
        id=ChunkId(chunk_id),
        document_id=document_id,
        text=text,
        pages=PageRange.single(1),
        clause_type=clause_type,
    )
    (embedding,) = (await embedder.embed_documents([text])).embeddings
    await writer.replace_document(document_id, [EmbeddedChunk(chunk, embedding)])


async def test_search_ranks_exact_match_first_and_filters_by_type():
    store = InMemoryVectorStore()
    writer, search, embedder = (
        InMemoryVectorIndexWriter(store),
        InMemoryVectorSearch(store),
        InMemoryEmbedder(),
    )
    await _index(
        writer, embedder, "c1", DOC_A, "governed by law", ClauseType.GOVERNING_LAW
    )
    await _index(
        writer, embedder, "c2", DOC_B, "may not compete", ClauseType.NON_COMPETE
    )

    query = await embedder.embed_query("may not compete")
    results = await search.search(query, limit=2)
    assert results[0].chunk.id == "c2"

    filtered = await search.search(
        query, limit=2, clause_types=frozenset({ClauseType.GOVERNING_LAW})
    )
    assert [r.chunk.id for r in filtered] == ["c1"]


async def test_writer_deletes_only_the_given_document():
    store = InMemoryVectorStore()
    writer, embedder = InMemoryVectorIndexWriter(store), InMemoryEmbedder()
    await _index(writer, embedder, "c1", DOC_A, "a", None)
    await _index(writer, embedder, "c2", DOC_B, "b", None)
    await writer.delete_document(DOC_A)
    assert set(store.entries) == {"c2"}


async def test_answer_generator_without_context():
    generated = await InMemoryAnswerGenerator().generate("Any MFN?", [])
    assert generated.answer.text == NO_CONTEXT_ANSWER
    assert generated.answer.citations == ()
    assert generated.model
