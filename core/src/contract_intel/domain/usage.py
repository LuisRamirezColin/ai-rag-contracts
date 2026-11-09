from dataclasses import dataclass

from contract_intel.domain.errors import NegativeQuantityError
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

    def __post_init__(self) -> None:
        ensure_not_blank(self.operation, "operation")
        ensure_not_blank(self.model, "model")
        _ensure_not_negative(self.input_tokens, "input_tokens")
        _ensure_not_negative(self.output_tokens, "output_tokens")
        _ensure_not_negative(self.cost_usd, "cost_usd")
