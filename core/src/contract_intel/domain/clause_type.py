from enum import StrEnum


class ClauseType(StrEnum):
    """Clause categories extracted from contracts (subset of the CUAD taxonomy)."""

    GOVERNING_LAW = "governing_law"
    TERMINATION_FOR_CONVENIENCE = "termination_for_convenience"
    CAP_ON_LIABILITY = "cap_on_liability"
    RENEWAL_TERM = "renewal_term"
    EXCLUSIVITY = "exclusivity"
    MOST_FAVORED_NATION = "most_favored_nation"
    NON_COMPETE = "non_compete"
    IP_OWNERSHIP_ASSIGNMENT = "ip_ownership_assignment"
    PRICE_RESTRICTIONS = "price_restrictions"
    VOLUME_RESTRICTION = "volume_restriction"
    OTHER = "other"
