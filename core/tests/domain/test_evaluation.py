import pytest

from contract_intel.domain.clause import Clause
from contract_intel.domain.clause_type import ClauseType
from contract_intel.domain.evaluation import (
    EVALUATED_TYPES,
    ExpertLabels,
    evaluate,
    to_markdown,
)
from contract_intel.domain.ids import ClauseId, DocumentId
from contract_intel.domain.page import PageRange

LAW = ClauseType.GOVERNING_LAW
CAP = ClauseType.CAP_ON_LIABILITY
MFN = ClauseType.MOST_FAVORED_NATION


def clause(title, clause_type, text):
    return Clause(
        ClauseId(f"{title}:{clause_type}:000"),
        DocumentId(title),
        clause_type,
        text,
        PageRange(1, 1),
    )


LABELS = {
    "a": ExpertLabels(
        "a",
        {
            LAW: ("governed by the laws of the State of Delaware",),
            CAP: ("liability shall not exceed fees",),
        },
    ),
    "b": ExpertLabels("b", {LAW: ("laws of New York",)}),
}
PREDICTIONS = {
    "a": [
        clause(
            "a",
            LAW,
            "This Agreement shall be GOVERNED BY  the laws of the State of Delaware.",
        )
    ],
    "b": [clause("b", LAW, "Totally different text"), clause("b", CAP, "Cap of 1M")],
    "unlabeled": [clause("unlabeled", LAW, "x")],
}


def by_type(report, clause_type):
    return next(m for m in report.types if m.clause_type is clause_type)


def test_counts_tp_fp_fn_per_type():
    report = evaluate(PREDICTIONS, LABELS)

    law, cap = by_type(report, LAW), by_type(report, CAP)
    assert (law.true_positives, law.false_positives, law.false_negatives) == (2, 0, 0)
    assert (cap.true_positives, cap.false_positives, cap.false_negatives) == (0, 1, 1)
    assert cap.precision == 0.0
    assert cap.recall == 0.0
    assert cap.f1 == 0.0


def test_evidence_matching_ignores_case_and_whitespace():
    law = by_type(evaluate(PREDICTIONS, LABELS), LAW)

    assert law.evidence_matches == 1
    assert law.evidence_match_rate == pytest.approx(0.5)


def test_types_without_cases_are_undefined():
    mfn = by_type(evaluate(PREDICTIONS, LABELS), MFN)

    assert (mfn.precision, mfn.recall, mfn.f1, mfn.evidence_match_rate) == (
        None,
        None,
        None,
        None,
    )


def test_scope_lists_evaluated_and_excluded_documents():
    report = evaluate(PREDICTIONS, LABELS)

    assert report.evaluated_documents == ("a", "b")
    assert report.excluded_documents == ("unlabeled",)


def test_totals_are_micro_averaged_and_other_is_ignored():
    report = evaluate(PREDICTIONS, LABELS)

    assert ClauseType.OTHER not in EVALUATED_TYPES
    assert len(report.types) == len(EVALUATED_TYPES)
    assert (
        report.totals.true_positives,
        report.totals.false_positives,
        report.totals.false_negatives,
    ) == (2, 1, 1)
    assert report.totals.precision == pytest.approx(2 / 3)


def test_markdown_has_one_row_per_type_and_the_scope():
    markdown = to_markdown(evaluate(PREDICTIONS, LABELS))

    assert "| governing_law | 2 | 0 | 0 | 100% | 100% | 100% | 50% |" in markdown
    assert "n/a" in markdown
    assert "Evaluated documents: 2; excluded (no expert labels): 1" in markdown
    assert "Excluded: unlabeled" in markdown
