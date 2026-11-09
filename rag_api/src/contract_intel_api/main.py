"""FastAPI entry point: the reader side of the RAG.

Routes obtain use cases from the reader container stored in ``app.state``;
they never import outbound adapters directly.
"""

from fastapi import FastAPI

from contract_intel.bootstrap.reader import ReaderContainer, build_reader_container
from contract_intel_api.health import router as health_router

API_TITLE = "Contract Intelligence API"


def create_app(container: ReaderContainer | None = None) -> FastAPI:
    """Build the API application wired to ``container``."""
    app = FastAPI(title=API_TITLE)
    app.state.container = container or build_reader_container()
    app.include_router(health_router)
    return app


app = create_app()
