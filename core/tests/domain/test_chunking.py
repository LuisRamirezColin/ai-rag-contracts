import pytest

from contract_intel.domain.chunking import ChunkingPolicy, chunk_id_for, chunk_pages
from contract_intel.domain.errors import InvalidChunkingError
from contract_intel.domain.ids import DocumentId
from contract_intel.domain.page import Page, PageRange

DOC = DocumentId("doc-1")
POLICY = ChunkingPolicy(max_chars=200, overlap_chars=40)


def _pages(*texts: str) -> tuple[Page, ...]:
    return tuple(
        Page(document_id=DOC, number=n, text=t) for n, t in enumerate(texts, start=1)
    )


def _words(start: int, count: int) -> str:
    return " ".join(f"w{i:04d}" for i in range(start, start + count))


def test_short_document_is_one_chunk_covering_pages_with_text():
    chunks = chunk_pages(DOC, _pages("Recitals.", "", "Governing law."), POLICY)

    assert len(chunks) == 1
    assert chunks[0].pages == PageRange(first=1, last=3)
    assert "Recitals." in chunks[0].text
    assert "Governing law." in chunks[0].text


def test_long_document_respects_size_overlap_and_coverage():
    source = _words(0, 300)

    chunks = chunk_pages(DOC, _pages(source), POLICY)

    assert len(chunks) > 3
    assert all(len(c.text) <= POLICY.max_chars for c in chunks)
    for previous, current in zip(chunks, chunks[1:], strict=False):
        assert current.text.split()[0] in previous.text
    covered = {word for c in chunks for word in c.text.split()}
    assert covered == set(source.split())


def test_chunk_crossing_a_page_break_covers_both_pages():
    chunks = chunk_pages(DOC, _pages(_words(0, 20), _words(20, 20)), POLICY)

    assert any(c.pages == PageRange(first=1, last=2) for c in chunks)


def test_blank_pages_produce_no_empty_chunks():
    pages = _pages("", "   ", _words(0, 100), "\n", _words(100, 100), "")

    chunks = chunk_pages(DOC, pages, POLICY)

    assert chunks
    assert all(c.text.strip() for c in chunks)
    assert all(c.pages.first >= 3 and c.pages.last <= 5 for c in chunks)


def test_document_without_text_has_no_chunks():
    assert chunk_pages(DOC, _pages("", " "), POLICY) == ()


def test_ids_are_deterministic_and_ordered():
    pages = _pages(_words(0, 200))

    first = chunk_pages(DOC, pages, POLICY)
    again = chunk_pages(DOC, pages, POLICY)

    assert [c.id for c in first] == [c.id for c in again]
    assert first[0].id == chunk_id_for(DOC, 0) == "doc-1:0000"
    assert first[1].id == "doc-1:0001"


def test_text_without_spaces_is_cut_at_max_chars():
    chunks = chunk_pages(DOC, _pages("x" * 450), POLICY)

    assert [len(c.text) for c in chunks][0] == POLICY.max_chars
    assert all(len(c.text) <= POLICY.max_chars for c in chunks)


@pytest.mark.parametrize(("max_chars", "overlap"), [(0, 0), (100, 100), (100, -1)])
def test_invalid_policy_is_rejected(max_chars, overlap):
    with pytest.raises(InvalidChunkingError):
        ChunkingPolicy(max_chars=max_chars, overlap_chars=overlap)
