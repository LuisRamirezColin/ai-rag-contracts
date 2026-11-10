import csv
from pathlib import Path

import pytest

from contract_intel.adapters.outbound.cuad.cuad_ground_truth import (
    COLUMN_BY_TYPE,
    CuadGroundTruth,
)
from contract_intel.adapters.outbound.in_memory.ground_truth_source import (
    InMemoryGroundTruthSource,
)
from contract_intel.application.ports.outbound.ground_truth_source import (
    GroundTruthSource,
)
from contract_intel.bootstrap.settings import AppSettings
from contract_intel.domain.clause_type import ClauseType
from contract_intel.domain.evaluation import ExpertLabels

LAW_EXCERPT = (
    'This Agreement shall be governed by the laws of "Delaware",\n'
    "without regard to conflicts."
)
TITLE_A, TITLE_B = "ALPHA-SERVICES AGREEMENT", "Beta_Co-Branding Agreement"
EXPECTED = {
    TITLE_A: ExpertLabels(TITLE_A, {ClauseType.GOVERNING_LAW: (LAW_EXCERPT,)}),
    TITLE_B: ExpertLabels(
        TITLE_B,
        {
            ClauseType.CAP_ON_LIABILITY: (
                "Liability is capped.",
                "No consequential damages.",
            )
        },
    ),
}


def _write_csv(path: Path) -> None:
    columns = ["Filename", *COLUMN_BY_TYPE.values(), "Governing Law-Answer"]
    rows = [
        {
            "Filename": f"{TITLE_A}.PDF",
            "Governing Law": repr([LAW_EXCERPT]),
            "Cap On Liability": "[]",
        },
        {
            "Filename": f"{TITLE_B}.pdf",
            "Cap On Liability": repr(
                ["Liability is capped.", "No consequential damages."]
            ),
        },
    ]
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "[]") for column in columns})


@pytest.fixture(params=["in_memory", "cuad"])
def source(request: pytest.FixtureRequest, tmp_path: Path) -> GroundTruthSource:
    if request.param == "cuad":
        path = tmp_path / "master_clauses.csv"
        _write_csv(path)
        return CuadGroundTruth(path)
    return InMemoryGroundTruthSource(EXPECTED)


async def test_labels_are_keyed_by_title_with_excerpts_per_type(source):
    assert await source.labels() == EXPECTED


async def test_absent_types_have_no_excerpts(source):
    labels = await source.labels()
    assert labels[TITLE_A].excerpts(ClauseType.CAP_ON_LIABILITY) == ()


class TestCuadSpecifics:
    async def test_malformed_cells_are_treated_as_absent(self, tmp_path):
        path = tmp_path / "labels.csv"
        with path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(["Filename", "Governing Law"])
            writer.writerow(["X.pdf", "not a python list ["])
        labels = await CuadGroundTruth(path).labels()
        assert labels["X"].excerpts(ClauseType.GOVERNING_LAW) == ()

    async def test_real_cuad_file_when_downloaded(self):
        path = AppSettings(_env_file=None).evaluation.labels_path
        if not path.is_file():
            pytest.skip("CUAD not downloaded")
        labels = await CuadGroundTruth(path).labels()

        assert len(labels) == 510
        ability = labels["ABILITYINC_06_15_2020-EX-4.25-SERVICES AGREEMENT"]
        assert "State of Israel" in ability.excerpts(ClauseType.GOVERNING_LAW)[0]
        mart = next(v for k, v in labels.items() if k.startswith("2ThemartComInc"))
        assert "California" in mart.excerpts(ClauseType.GOVERNING_LAW)[0]
