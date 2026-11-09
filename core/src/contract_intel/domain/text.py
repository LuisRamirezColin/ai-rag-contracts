from contract_intel.domain.errors import BlankTextError


def ensure_not_blank(value: str, field_name: str) -> None:
    """Reject empty or whitespace-only text.

    Raises:
        BlankTextError: If ``value`` has no visible characters.
    """
    if not value.strip():
        raise BlankTextError(field_name)
