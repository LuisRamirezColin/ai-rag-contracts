"""FastAPI entry point: the reader side of the RAG.

Routes obtain use cases from the reader container stored in ``app.state``;
they never import outbound adapters directly.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from contract_intel.bootstrap.reader import ReaderContainer, build_reader_container
from contract_intel_api.ask import router as ask_router
from contract_intel_api.health import router as health_router

API_TITLE = "Contract Intelligence API"


def create_app(container: ReaderContainer | None = None) -> FastAPI:
    """Build the API application wired to ``container``."""
    reader = container or build_reader_container()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        # Creating the engine opens no connection, so disposing it is always safe.
        await reader.core.database_engine().dispose()

    app = FastAPI(title=API_TITLE, lifespan=lifespan)
    app.state.container = reader
    app.include_router(health_router)
    app.include_router(ask_router)
    return app


app = create_app()
