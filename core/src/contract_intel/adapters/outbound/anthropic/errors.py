"""Translate Anthropic SDK failures into domain errors, shared by its adapters."""

from collections.abc import Iterator
from contextlib import contextmanager

from anthropic import APIConnectionError, InternalServerError, RateLimitError

from contract_intel.domain.errors import (
    ModelRefusedError,
    ProviderRateLimitedError,
    ProviderUnavailableError,
)

PROVIDER = "anthropic"
REFUSAL_STOP_REASON = "refusal"


@contextmanager
def anthropic_errors() -> Iterator[None]:
    """Re-raise rate limits and outages as domain errors; let others through."""
    try:
        yield
    except RateLimitError as error:
        raise ProviderRateLimitedError(PROVIDER, str(error)) from error
    except (APIConnectionError, InternalServerError) as error:
        raise ProviderUnavailableError(PROVIDER, str(error)) from error


def ensure_not_refused(
    stop_reason: str | None, stop_details: object, error: type[ModelRefusedError]
) -> None:
    """Raise ``error`` with the refusal category when the model declined."""
    if stop_reason == REFUSAL_STOP_REASON:
        raise error(getattr(stop_details, "category", None))
