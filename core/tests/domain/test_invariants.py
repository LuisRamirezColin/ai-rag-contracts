from dataclasses import FrozenInstanceError

import pytest

from contract_intel.domain.answer import Answer, Citation
from contract_intel.domain.chunk import Chunk, Embedding
from contract_intel.domain.clause import Clause
from contract_intel.domain.clause_type import ClauseType
from contract_intel.domain.contract import Contract
from contract_intel.domain.document import Document, DocumentType
from contract_intel.domain.errors import (
    BlankTextError,
    EmptyEmbeddingError,
    InvalidPageNumberError,
    InvalidPageRangeError,
    NegativeQuantityError,
)
from contract_intel.domain.ids import ChunkId, ClauseId, ContractId, DocumentId
from contract_intel.domain.page import Page, PageRange
from contract_intel.domain.usage import UsageRecord

DOC = DocumentId("doc-1")


class TestPage:
    def test_accepts_first_page_and_empty_text(self):
        page = Page(document_id=DOC, number=1, text="")
        assert page.number == 1

    def test_rejects_page_zero(self):
        with pytest.raises(InvalidPageNumberError):
            Page(document_id=DOC, number=0, text="x")

    def test_is_immutable(self):
        page = Page(document_id=DOC, number=1, text="x")
        with pytest.raises(FrozenInstanceError):
            page.number = 2  # type: ignore[misc]


class TestPageRange:
    def test_single_page_range(self):
        assert PageRange.single(3) == PageRange(first=3, last=3)

    def test_rejects_range_starting_before_first_page(self):
        with pytest.raises(InvalidPageNumberError):
            PageRange(first=0, last=2)

    def test_rejects_inverted_range(self):
        with pytest.raises(InvalidPageRangeError):
            PageRange(first=5, last=4)


class TestDocument:
    def test_valid_document(self):
        doc = Document(
            id=DOC,
            contract_id=ContractId("c-1"),
            title="Supply Agreement",
            document_type=DocumentType.MASTER_SERVICE_AGREEMENT,
        )
        assert doc.document_type is DocumentType.MASTER_SERVICE_AGREEMENT

    def test_rejects_blank_title(self):
        with pytest.raises(BlankTextError):
            Document(
                id=DOC,
                contract_id=ContractId("c-1"),
                title="  ",
                document_type=DocumentType.OTHER,
            )


def _clause(
    clause_type: ClauseType, text: str = "Governed by the laws of X."
) -> Clause:
    return Clause(
        id=ClauseId(f"cl-{clause_type}"),
        document_id=DOC,
        clause_type=clause_type,
        text=text,
        pages=PageRange.single(1),
    )


class TestClause:
    def test_rejects_blank_text(self):
        with pytest.raises(BlankTextError):
            _clause(ClauseType.GOVERNING_LAW, text="")


class TestContract:
    def test_filters_clauses_by_type(self):
        governing = _clause(ClauseType.GOVERNING_LAW)
        contract = Contract(
            id=ContractId("c-1"),
            title="Supply Agreement",
            document_ids=(DOC,),
            clauses=(governing, _clause(ClauseType.NON_COMPETE)),
        )
        assert contract.clauses_of_type(ClauseType.GOVERNING_LAW) == (governing,)

    def test_rejects_blank_title(self):
        with pytest.raises(BlankTextError):
            Contract(id=ContractId("c-1"), title="")


class TestChunkAndEmbedding:
    def test_rejects_blank_chunk_text(self):
        with pytest.raises(BlankTextError):
            Chunk(id=ChunkId("ch-1"), document_id=DOC, text=" ", pages=PageRange(1, 2))

    def test_embedding_reports_dimensions(self):
        assert Embedding(values=(0.1, 0.2, 0.3)).dimensions == 3

    def test_rejects_empty_embedding(self):
        with pytest.raises(EmptyEmbeddingError):
            Embedding(values=())


class TestAnswer:
    def test_valid_answer_with_citation(self):
        citation = Citation(document_id=DOC, pages=PageRange(2, 3), excerpt="term")
        answer = Answer(question="What term?", text="Two years.", citations=(citation,))
        assert answer.citations == (citation,)

    def test_rejects_blank_citation_excerpt(self):
        with pytest.raises(BlankTextError):
            Citation(document_id=DOC, pages=PageRange.single(1), excerpt="")

    def test_rejects_blank_question(self):
        with pytest.raises(BlankTextError):
            Answer(question="", text="Two years.")


class TestUsageRecord:
    def test_valid_record(self):
        record = UsageRecord("extract", "model-x", 10, 5, 0.001)
        assert record.input_tokens == 10

    @pytest.mark.parametrize(
        ("input_tokens", "output_tokens", "cost"),
        [(-1, 0, 0.0), (0, -1, 0.0), (0, 0, -0.5)],
    )
    def test_rejects_negative_quantities(self, input_tokens, output_tokens, cost):
        with pytest.raises(NegativeQuantityError):
            UsageRecord("extract", "model-x", input_tokens, output_tokens, cost)
