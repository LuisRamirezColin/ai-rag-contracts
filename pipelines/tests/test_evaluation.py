from dagster import materialize

from contract_intel.adapters.outbound.in_memory.ground_truth_source import (
    InMemoryGroundTruthSource,
)
from contract_intel.bootstrap.settings import AppSettings
from contract_intel.bootstrap.writer import build_writer_container
from contract_intel.domain.clause_type import ClauseType
from contract_intel.domain.evaluation import ExpertLabels
from contract_intel_pipelines.definitions import CONTAINER_RESOURCE_KEY
from contract_intel_pipelines.evaluation import extraction_evaluation


def test_evaluation_asset_publishes_a_markdown_report():
    container = build_writer_container(AppSettings(_env_file=None, use_fakes=True))
    container.ground_truth_source.override(
        InMemoryGroundTruthSource(
            {"X": ExpertLabels("X", {ClauseType.GOVERNING_LAW: ("laws of Texas",)})}
        )
    )

    result = materialize(
        [extraction_evaluation], resources={CONTAINER_RESOURCE_KEY: container}
    )

    assert result.success
    (materialization,) = result.asset_materializations_for_node("extraction_evaluation")
    assert "| Clause type |" in str(materialization.metadata["report"].value)
    assert materialization.metadata["evaluated_documents"].value == 0
