"""Architecture rules are executable: the import contracts must hold.

The negative tests copy the real source tree into a temporary directory, inject
one violation, and assert that ``lint-imports`` (run against the project's own
contracts) reports it as broken.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SOURCE_ROOTS = ("core/src", "pipelines/src", "rag_api/src")


def _lint_imports(cwd: Path, pythonpath: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONPATH": pythonpath}
    lint_imports = Path(sys.executable).with_name("lint-imports")
    return subprocess.run(  # noqa: S603 - fixed executable, no user input
        [str(lint_imports), "--config", str(cwd / "pyproject.toml"), "--no-cache"],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_import_contracts_are_kept():
    result = _lint_imports(REPO_ROOT, os.pathsep.join(SOURCE_ROOTS))
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.fixture
def source_copy(tmp_path: Path) -> Path:
    for root in SOURCE_ROOTS:
        shutil.copytree(REPO_ROOT / root, tmp_path / root)
    shutil.copy(REPO_ROOT / "pyproject.toml", tmp_path / "pyproject.toml")
    return tmp_path


def _inject(source_copy: Path, relative_module: str, statement: str) -> None:
    module = source_copy / relative_module
    module.write_text(f"{statement}\n{module.read_text()}")


@pytest.mark.parametrize(
    ("relative_module", "statement", "broken_contract"),
    [
        (
            "core/src/contract_intel/domain/page.py",
            "import sqlalchemy  # noqa",
            "Domain is framework-free",
        ),
        (
            "core/src/contract_intel/domain/page.py",
            "import openai  # noqa",
            "Domain is framework-free",
        ),
        (
            "core/src/contract_intel/application/ports/outbound/embedder.py",
            "import contract_intel.adapters.outbound.in_memory.embedder  # noqa",
            "Core layers",
        ),
        (
            "rag_api/src/contract_intel_api/health.py",
            "import contract_intel.adapters.outbound.in_memory.vector_index  # noqa",
            "Inbound adapters reach outbound adapters only through",
        ),
        (
            "rag_api/src/contract_intel_api/health.py",
            "import contract_intel.application.ports.outbound.vector_index_writer"
            "  # noqa",
            "API is read-only on the vector index",
        ),
        (
            "pipelines/src/contract_intel_pipelines/definitions.py",
            "import contract.abilities  # noqa",
            "Legacy reference code is never imported",
        ),
    ],
)
def test_violation_is_reported(
    source_copy, relative_module, statement, broken_contract
):
    _inject(source_copy, relative_module, statement)
    pythonpath = os.pathsep.join(str(source_copy / root) for root in SOURCE_ROOTS)

    result = _lint_imports(source_copy, pythonpath)

    assert result.returncode != 0
    broken_lines = [line for line in result.stdout.splitlines() if "BROKEN" in line]
    assert any(broken_contract in line for line in broken_lines), result.stdout
