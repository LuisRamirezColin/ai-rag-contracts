import pytest

from contract_intel.domain.clause import ClauseExtraction
from contract_intel.domain.clause_rules import (
    MIN_SHARED_CHARS,
    ClauseCandidate,
    consolidate,
    is_literal,
    to_clauses,
)
from contract_intel.domain.clause_type import ClauseType
from contract_intel.domain.errors import (
    AnswerRefusedError,
    ModelRefusedError,
    NegativeQuantityError,
)
from contract_intel.domain.ids import DocumentId
from contract_intel.domain.page import Page, PageRange

DOC = DocumentId("doc-1")
LAW = ClauseType.GOVERNING_LAW
CAP = ClauseType.CAP_ON_LIABILITY
PAGES = (
    Page(DOC, 1, "Recitals. The parties agree as follows."),
    Page(DOC, 2, "12. Governing Law. This Agreement shall be governed by\nthe laws of"),
    Page(DOC, 3, "the State of Delaware. 13. Notices. All notices in writing."),
)


def candidate(text, first, last=None, clause_type=LAW):
    return ClauseCandidate(clause_type, text, PageRange(first, last or first))


class TestIsLiteral:
    def test_literal_text_with_different_whitespace(self):
        text = "This Agreement shall be governed by the laws of the State of Delaware."
        assert is_literal(candidate(text, 2, 3), PAGES)

    def test_paraphrase_is_rejected(self):
        assert not is_literal(
            candidate("Delaware law governs this contract.", 2, 3), PAGES
        )

    def test_text_outside_claimed_pages_is_rejected(self):
        assert not is_literal(candidate("All notices in writing.", 2), PAGES)

    def test_pages_beyond_the_document_are_rejected(self):
        assert not is_literal(candidate("Recitals.", 1, 9), PAGES)


class TestConsolidate:
    def test_contained_candidates_are_merged_with_page_union(self):
        short = candidate("governed by the laws of the State of Delaware", 3)
        long = candidate(
            "This Agreement shall be governed by the laws of the State of Delaware.",
            2,
            3,
        )

        (merged,) = consolidate([short, long])

        assert merged.text == long.text
        assert merged.pages == PageRange(2, 3)

    def test_partially_overlapping_candidates_are_merged(self):
        shared = "x" * MIN_SHARED_CHARS
        first = candidate(f"start {shared}", 2)
        second = candidate(f"{shared} end of clause", 3)

        assert len(consolidate([first, second])) == 1

    def test_different_types_are_never_merged(self):
        text = "Neither party shall be liable beyond the fees paid."
        result = consolidate([candidate(text, 2), candidate(text, 2, clause_type=CAP)])
        assert {c.clause_type for c in result} == {LAW, CAP}

    def test_unrelated_candidates_stay_apart(self):
        result = consolidate(
            [
                candidate("Governed by Delaware law.", 2),
                candidate("Governed by New York law.", 5),
            ]
        )
        assert len(result) == 2


def test_clause_ids_are_deterministic_per_type():
    clauses = to_clauses(
        DOC,
        [
            candidate("Second law clause.", 5),
            candidate("First  law\nclause.", 2),
            candidate("Cap.", 3, clause_type=CAP),
        ],
    )

    assert [c.id for c in clauses] == [
        "doc-1:governing_law:000",
        "doc-1:cap_on_liability:000",
        "doc-1:governing_law:001",
    ]
    assert clauses[0].text == "First law clause."


def test_clause_extraction_rejects_negative_tokens():
    with pytest.raises(NegativeQuantityError):
        ClauseExtraction((), "m", -1, 0)


def test_answer_refusals_are_model_refusals():
    assert issubclass(AnswerRefusedError, ModelRefusedError)
    assert ModelRefusedError("cyber").category == "cyber"
