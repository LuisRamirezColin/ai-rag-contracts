import ast
import asyncio
import csv
from collections.abc import Mapping
from pathlib import Path

from contract_intel.domain.clause_type import ClauseType
from contract_intel.domain.evaluation import ExpertLabels

FILENAME_COLUMN = "Filename"
COLUMN_BY_TYPE = {
    ClauseType.GOVERNING_LAW: "Governing Law",
    ClauseType.TERMINATION_FOR_CONVENIENCE: "Termination For Convenience",
    ClauseType.CAP_ON_LIABILITY: "Cap On Liability",
    ClauseType.RENEWAL_TERM: "Renewal Term",
    ClauseType.EXCLUSIVITY: "Exclusivity",
    ClauseType.MOST_FAVORED_NATION: "Most Favored Nation",
    ClauseType.NON_COMPETE: "Non-Compete",
    ClauseType.IP_OWNERSHIP_ASSIGNMENT: "Ip Ownership Assignment",
    ClauseType.PRICE_RESTRICTIONS: "Price Restrictions",
    ClauseType.VOLUME_RESTRICTION: "Volume Restriction",
}


class CuadGroundTruth:
    """Lawyer labels from CUAD's ``master_clauses.csv``, keyed by PDF stem.

    Each clause column holds a Python-literal list of verbatim excerpts; an
    empty list means the clause is absent from the contract.
    """

    def __init__(self, labels_path: Path) -> None:
        self._labels_path = labels_path

    async def labels(self) -> Mapping[str, ExpertLabels]:
        """Return the expert labels of every contract in the file."""
        return await asyncio.to_thread(self._read)

    def _read(self) -> dict[str, ExpertLabels]:
        with self._labels_path.open(encoding="utf-8", newline="") as file:
            rows = list(csv.DictReader(file))
        labels: dict[str, ExpertLabels] = {}
        for row in rows:
            title = Path(row[FILENAME_COLUMN]).stem
            excerpts = {
                clause_type: _excerpts(row.get(column, ""))
                for clause_type, column in COLUMN_BY_TYPE.items()
            }
            labels[title] = ExpertLabels(
                document_title=title,
                excerpts_by_type={t: e for t, e in excerpts.items() if e},
            )
        return labels


def _excerpts(cell: str) -> tuple[str, ...]:
    try:
        value = ast.literal_eval(cell) if cell.strip() else []
    except (ValueError, SyntaxError):
        return ()
    if not isinstance(value, list):
        return ()
    return tuple(str(item).strip() for item in value if str(item).strip())
