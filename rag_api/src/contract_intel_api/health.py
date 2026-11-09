from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Liveness probe payload."""

    status: Literal["ok"] = "ok"


@router.get("/health")
async def health() -> HealthResponse:
    """Report that the API process is up."""
    return HealthResponse()
