"""SOP (Standard Operating Procedure) authority matrix.

Defines which organisational role can approve a refund or replacement up to
a given amount.  This is intentionally separate from policy.py so the
authority rules can be versioned and audited independently of the return/refund
eligibility rules.

Rules (all amounts in cents, USD):

  Tier 1 – Support Agent        auto-approved  $0 – $25.00
  Tier 2 – Senior Agent         up to $100.00  (requires Senior Agent or above)
  Tier 3 – Team Supervisor      up to $250.00  (requires Supervisor or above)
  Tier 4 – Operations Manager   up to $750.00  (requires Ops Manager or above)
  Tier 5 – Director / Finance   above $750.00  (always requires Director sign-off)

Replacements follow the same tiers based on item replacement value.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class AuthorityLevel(IntEnum):
    """Numeric authority levels — higher beats lower."""
    SUPPORT_AGENT = 1
    SENIOR_AGENT = 2
    SUPERVISOR = 3
    OPS_MANAGER = 4
    DIRECTOR = 5


# Human-readable names for display
AUTHORITY_LABELS: dict[AuthorityLevel, str] = {
    AuthorityLevel.SUPPORT_AGENT: "Support Agent",
    AuthorityLevel.SENIOR_AGENT: "Senior Support Agent",
    AuthorityLevel.SUPERVISOR: "Team Supervisor",
    AuthorityLevel.OPS_MANAGER: "Operations Manager",
    AuthorityLevel.DIRECTOR: "Director / Finance",
}

# SOP tiers: (max_amount_cents_inclusive, required_authority_level)
# Ordered ascending.  Anything above the last threshold routes to DIRECTOR.
_TIERS: list[tuple[int, AuthorityLevel]] = [
    (2_500,   AuthorityLevel.SUPPORT_AGENT),    # $0 – $25     auto-approve
    (10_000,  AuthorityLevel.SENIOR_AGENT),     # $25 – $100   Senior Agent
    (25_000,  AuthorityLevel.SUPERVISOR),       # $100 – $250  Supervisor
    (75_000,  AuthorityLevel.OPS_MANAGER),      # $250 – $750  Ops Manager
]
_DIRECTOR_THRESHOLD = 75_000                    # anything above → Director


@dataclass(frozen=True)
class SopVerdict:
    amount_cents: int
    required_level: AuthorityLevel
    required_label: str
    auto_approve: bool          # True only for Support Agent tier
    tier_number: int            # 1-5
    max_cents_for_tier: int     # upper bound (inclusive) for this tier, 0 = unlimited


def evaluate_authority(amount_cents: int) -> SopVerdict:
    """Return the SOP verdict for a given refund/replacement amount."""
    if amount_cents <= 0:
        raise ValueError("amount_cents must be positive")

    for tier_num, (limit, level) in enumerate(_TIERS, start=1):
        if amount_cents <= limit:
            return SopVerdict(
                amount_cents=amount_cents,
                required_level=level,
                required_label=AUTHORITY_LABELS[level],
                auto_approve=(level == AuthorityLevel.SUPPORT_AGENT),
                tier_number=tier_num,
                max_cents_for_tier=limit,
            )

    # Above all tiers → Director
    return SopVerdict(
        amount_cents=amount_cents,
        required_level=AuthorityLevel.DIRECTOR,
        required_label=AUTHORITY_LABELS[AuthorityLevel.DIRECTOR],
        auto_approve=False,
        tier_number=5,
        max_cents_for_tier=0,  # 0 = no upper bound
    )


def can_approve(actor_level: AuthorityLevel, amount_cents: int) -> bool:
    """Return True if actor_level is sufficient to approve amount_cents."""
    verdict = evaluate_authority(amount_cents)
    return actor_level >= verdict.required_level


def sop_tiers_summary() -> list[dict]:
    """Return a machine-readable description of all tiers for the UI."""
    rows = []
    prev = 0
    for tier_num, (limit, level) in enumerate(_TIERS, start=1):
        rows.append({
            "tier": tier_num,
            "role": AUTHORITY_LABELS[level],
            "level": level.value,
            "from_cents": prev + 1,
            "to_cents": limit,
            "from_display": f"${prev/100:.2f}",
            "to_display": f"${limit/100:.2f}",
            "auto_approve": (level == AuthorityLevel.SUPPORT_AGENT),
        })
        prev = limit
    rows.append({
        "tier": 5,
        "role": AUTHORITY_LABELS[AuthorityLevel.DIRECTOR],
        "level": AuthorityLevel.DIRECTOR.value,
        "from_cents": prev + 1,
        "to_cents": None,
        "from_display": f"${prev/100:.2f}",
        "to_display": "unlimited",
        "auto_approve": False,
    })
    return rows
