from contract_intel.domain.chunk import Chunk
from contract_intel.domain.chunk_labels import label_chunks
from contract_intel.domain.clause import Clause
from contract_intel.domain.clause_type import ClauseType
from contract_intel.domain.ids import ChunkId, ClauseId, DocumentId
from contract_intel.domain.page import PageRange

DOC = DocumentId("doc-1")
LAW_TEXT = "This Agreement shall be governed by the laws of the State of Delaware."
CAP_TEXT = "In no event shall either party's liability exceed the fees paid hereunder."


def chunk(ordinal, text, pages=(1, 1)):
    return Chunk(ChunkId(f"doc-1:{ordinal:04d}"), DOC, text, PageRange(*pages))


def clause(clause_type, text, pages=(1, 1), document_id=DOC):
    return Clause(
        ClauseId(f"{document_id}:{clause_type}:000"),
        document_id,
        clause_type,
        text,
        PageRange(*pages),
    )


LAW = clause(ClauseType.GOVERNING_LAW, LAW_TEXT, (2, 2))
CAP = clause(ClauseType.CAP_ON_LIABILITY, CAP_TEXT, (2, 3))


def test_no_clauses_no_labels():
    (labeled,) = label_chunks([chunk(0, LAW_TEXT, (2, 2))], [])
    assert labeled.clause_types == frozenset()


def test_one_clause_one_type():
    (labeled,) = label_chunks([chunk(0, f"Intro. {LAW_TEXT} More.", (2, 2))], [LAW])
    assert labeled.clause_types == {ClauseType.GOVERNING_LAW}


def test_chunk_with_two_clauses_gets_both_types():
    (labeled,) = label_chunks([chunk(0, f"{LAW_TEXT}\n{CAP_TEXT}", (2, 3))], [LAW, CAP])
    assert labeled.clause_types == {
        ClauseType.GOVERNING_LAW,
        ClauseType.CAP_ON_LIABILITY,
    }


def test_clause_crossing_two_chunks_labels_both():
    long_cap = clause(
        ClauseType.CAP_ON_LIABILITY, f"{CAP_TEXT} {CAP_TEXT.upper()}", (2, 3)
    )
    first = chunk(0, f"Preamble text. {CAP_TEXT}", (2, 2))
    second = chunk(1, f"{CAP_TEXT.upper()} Next section.", (3, 3))

    labeled = label_chunks([first, second], [long_cap])

    assert all(c.clause_types == {ClauseType.CAP_ON_LIABILITY} for c in labeled)


def test_overlapping_pages_without_shared_text_get_no_label():
    (labeled,) = label_chunks([chunk(0, "Unrelated notice provisions.", (2, 2))], [LAW])
    assert labeled.clause_types == frozenset()


def test_shared_text_on_other_pages_gets_no_label():
    (labeled,) = label_chunks([chunk(0, LAW_TEXT, (7, 7))], [LAW])
    assert labeled.clause_types == frozenset()


def test_clauses_of_other_documents_are_ignored():
    other = clause(ClauseType.GOVERNING_LAW, LAW_TEXT, (2, 2), DocumentId("doc-2"))
    (labeled,) = label_chunks([chunk(0, LAW_TEXT, (2, 2))], [other])
    assert labeled.clause_types == frozenset()
