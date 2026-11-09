from dataclasses import dataclass

from contract_intel.domain.errors import NegativeQuantityError
from contract_intel.domain.ids import DocumentId
from contract_intel.domain.text import ensure_not_blank


def _ensure_not_negative(value: float, field_name: str) -> None:
    if value < 0:
        raise NegativeQuantityError(field_name, value)


@dataclass(frozen=True, slots=True)
class UsageRecord:
    """Token and cost accounting for one model invocation."""

    operation: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    document_id: DocumentId | None = None

    def __post_init__(self) -> None:
        ensure_not_blank(self.operation, "operation")
        ensure_not_blank(self.model, "model")
        _ensure_not_negative(self.input_tokens, "input_tokens")
        _ensure_not_negative(self.output_tokens, "output_tokens")
        _ensure_not_negative(self.cost_usd, "cost_usd")


TOKENS_PER_MILLION = 1_000_000


@dataclass(frozen=True, slots=True)
class TokenPricing:
    """List price of a model, in USD per million tokens."""

    input_per_million: float
    output_per_million: float = 0.0

    def __post_init__(self) -> None:
        _ensure_not_negative(self.input_per_million, "input_per_million")
        _ensure_not_negative(self.output_per_million, "output_per_million")

    def cost_usd(self, input_tokens: int, output_tokens: int = 0) -> float:
        """Return the estimated cost of a call that consumed these tokens."""
        return (
            input_tokens * self.input_per_million
            + output_tokens * self.output_per_million
        ) / TOKENS_PER_MILLION
