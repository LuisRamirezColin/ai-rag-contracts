"""On-demand evaluation of the stored clauses against the expert labels."""

import asyncio

from dagster import MaterializeResult, MetadataValue, ResourceParam, asset

from contract_intel.bootstrap.writer import WriterContainer
from contract_intel.domain.evaluation import EvaluationReport, to_markdown


@asset
def extraction_evaluation(
    container: ResourceParam[WriterContainer],
) -> MaterializeResult:  # type: ignore[type-arg]
    """Precision, recall and F1 per clause type versus CUAD's lawyer labels."""
    report: EvaluationReport = asyncio.run(
        container.evaluate_clause_extraction().execute()
    )
    totals = report.totals
    return MaterializeResult(
        metadata={
            "report": MetadataValue.md(to_markdown(report)),
            "evaluated_documents": len(report.evaluated_documents),
            "micro_precision": totals.precision if totals.precision is not None else -1,
            "micro_recall": totals.recall if totals.recall is not None else -1,
        }
    )
