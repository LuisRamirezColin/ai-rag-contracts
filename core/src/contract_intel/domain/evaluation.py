"""Compare extracted clauses with expert labels, per clause type."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from contract_intel.domain.clause import Clause
from contract_intel.domain.clause_rules import normalize_whitespace
from contract_intel.domain.clause_type import ClauseType

EVALUATED_TYPES = tuple(t for t in ClauseType if t is not ClauseType.OTHER)
PERCENT = 100


@dataclass(frozen=True, slots=True)
class ExpertLabels:
    """Expert excerpts per clause type for one document (empty = type absent)."""

    document_title: str
    excerpts_by_type: Mapping[ClauseType, tuple[str, ...]] = field(default_factory=dict)

    def excerpts(self, clause_type: ClauseType) -> tuple[str, ...]:
        """Return the expert excerpts for ``clause_type``."""
        return self.excerpts_by_type.get(clause_type, ())


@dataclass(frozen=True, slots=True)
class TypeMetrics:
    """Presence-detection counts and scores; ``clause_type`` is None for totals."""

    clause_type: ClauseType | None
    true_positives: int
    false_positives: int
    false_negatives: int
    evidence_matches: int

    @property
    def precision(self) -> float | None:
        """TP / (TP + FP), undefined without predicted positives."""
        return _ratio(self.true_positives, self.true_positives + self.false_positives)

    @property
    def recall(self) -> float | None:
        """TP / (TP + FN), undefined without real positives."""
        return _ratio(self.true_positives, self.true_positives + self.false_negatives)

    @property
    def f1(self) -> float | None:
        """Harmonic mean of precision and recall, undefined if either is."""
        precision, recall = self.precision, self.recall
        if precision is None or recall is None:
            return None
        if precision + recall == 0:
            return 0.0
        return 2 * precision * recall / (precision + recall)

    @property
    def evidence_match_rate(self) -> float | None:
        """Share of true positives whose text overlaps an expert excerpt."""
        return _ratio(self.evidence_matches, self.true_positives)


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    """Per-type metrics, micro-averaged totals and the evaluation scope."""

    types: tuple[TypeMetrics, ...]
    totals: TypeMetrics
    evaluated_documents: tuple[str, ...]
    excluded_documents: tuple[str, ...]


def evaluate(
    predictions_by_title: Mapping[str, Sequence[Clause]],
    labels_by_title: Mapping[str, ExpertLabels],
) -> EvaluationReport:
    """Evaluate the processed documents that have expert labels."""
    evaluated = tuple(sorted(t for t in predictions_by_title if t in labels_by_title))
    excluded = tuple(
        sorted(t for t in predictions_by_title if t not in labels_by_title)
    )
    types = tuple(
        _metrics_for(clause_type, evaluated, predictions_by_title, labels_by_title)
        for clause_type in EVALUATED_TYPES
    )
    totals = TypeMetrics(
        clause_type=None,
        true_positives=sum(m.true_positives for m in types),
        false_positives=sum(m.false_positives for m in types),
        false_negatives=sum(m.false_negatives for m in types),
        evidence_matches=sum(m.evidence_matches for m in types),
    )
    return EvaluationReport(types, totals, evaluated, excluded)


def to_markdown(report: EvaluationReport) -> str:
    """Render the report as a Markdown table plus its scope."""
    header = (
        "| Clause type | TP | FP | FN | Precision | Recall | F1 | Evidence match |\n"
        "|---|---|---|---|---|---|---|---|"
    )
    rows = [
        _row(m.clause_type.value if m.clause_type else "**total**", m)
        for m in report.types
    ]
    rows.append(_row("**total (micro)**", report.totals))
    scope = (
        f"\n\nEvaluated documents: {len(report.evaluated_documents)}"
        f"; excluded (no expert labels): {len(report.excluded_documents)}"
    )
    if report.excluded_documents:
        scope += "\n\nExcluded: " + ", ".join(report.excluded_documents)
    return "\n".join([header, *rows]) + scope


def _metrics_for(
    clause_type: ClauseType,
    titles: Sequence[str],
    predictions_by_title: Mapping[str, Sequence[Clause]],
    labels_by_title: Mapping[str, ExpertLabels],
) -> TypeMetrics:
    tp = fp = fn = evidence = 0
    for title in titles:
        predicted = [
            c for c in predictions_by_title[title] if c.clause_type is clause_type
        ]
        excerpts = labels_by_title[title].excerpts(clause_type)
        if predicted and excerpts:
            tp += 1
            evidence += int(_evidence_matches(predicted, excerpts))
        elif predicted:
            fp += 1
        elif excerpts:
            fn += 1
    return TypeMetrics(clause_type, tp, fp, fn, evidence)


def _evidence_matches(predicted: Sequence[Clause], excerpts: Sequence[str]) -> bool:
    for clause in predicted:
        text = _comparable(clause.text)
        for excerpt in excerpts:
            reference = _comparable(excerpt)
            if reference and (reference in text or text in reference):
                return True
    return False


def _comparable(text: str) -> str:
    return normalize_whitespace(text).lower()


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _row(label: str, metrics: TypeMetrics) -> str:
    cells = [
        label,
        str(metrics.true_positives),
        str(metrics.false_positives),
        str(metrics.false_negatives),
        _percent(metrics.precision),
        _percent(metrics.recall),
        _percent(metrics.f1),
        _percent(metrics.evidence_match_rate),
    ]
    return "| " + " | ".join(cells) + " |"


def _percent(value: float | None) -> str:
    return "n/a" if value is None else f"{value * PERCENT:.0f}%"
