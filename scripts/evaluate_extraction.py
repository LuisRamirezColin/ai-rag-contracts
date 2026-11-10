"""Print how the stored clauses compare with CUAD's lawyer labels.

Usage: ``uv run python scripts/evaluate_extraction.py`` (needs the database with
extracted clauses and ``data/cuad``; it never calls the extraction model).
"""

import asyncio
import sys

from contract_intel.bootstrap.writer import WriterContainer, build_writer_container
from contract_intel.domain.evaluation import to_markdown


async def render_report(container: WriterContainer) -> str:
    """Run the evaluation use case and render it as Markdown."""
    report = await container.evaluate_clause_extraction().execute()
    return to_markdown(report)


async def _main() -> None:
    container = build_writer_container()
    try:
        print(await render_report(container))
    finally:
        await container.core.database_engine().dispose()


def main() -> int:
    """Entry point for the command line."""
    asyncio.run(_main())
    return 0


if __name__ == "__main__":
    sys.exit(main())
