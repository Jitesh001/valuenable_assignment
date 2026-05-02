"""
Pure-python validators and input model for the benefit illustration engine.

This module is deliberately framework-agnostic — no Django, no DRF imports.
That makes it trivial to unit-test, reuse from a worker, or call from a CLI.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import List


class ValidationError(Exception):
    """Raised when one or more business validations fail.

    `errors` carries a list of human-readable messages so the API layer
    can return them all at once instead of failing on the first.
    """

    def __init__(self, errors: List[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


@dataclass(frozen=True)
class PolicyInput:
    """All inputs required to produce an illustration.

    Frozen + dataclass so the value object is hashable and comparable —
    handy for caching computed illustrations by input signature.
    """

    dob: date
    quote_date: date           # the "as of" date used for ACB age
    gender: str                # "M" / "F" / "O"
    premium: Decimal           # annual modal premium in INR
    premium_frequency: str     # "annual" | "semi" | "quarterly" | "monthly"
    premium_term: int          # PPT — years premiums are paid
    policy_term: int           # PT  — years policy runs
    sum_assured: Decimal
    rider_codes: tuple[str, ...] = ()


# --- Age Completed Birthday (ACB) -------------------------------------------------

def age_acb(dob: date, as_of: date) -> int:
    """Age Completed Birthday: integer years fully elapsed since DOB.

    Birthday hasn't occurred yet this year? subtract 1.
    Same calendar day as DOB? the year still counts as completed.
    """
    if as_of < dob:
        raise ValueError("Quote date cannot be earlier than DOB")
    years = as_of.year - dob.year
    # If birthday hasn't happened yet this year, decrement.
    if (as_of.month, as_of.day) < (dob.month, dob.day):
        years -= 1
    return years


# --- The five business validations from the Inputs sheet -------------------------

AGE_MIN, AGE_MAX = 23, 56
PREMIUM_MIN, PREMIUM_MAX = Decimal("10000"), Decimal("50000")
PT_MIN, PT_MAX = 5, 10           # premium term
POLICY_TERM_MIN, POLICY_TERM_MAX = 10, 20
SA_MIN_FLOOR = Decimal("500000")  # ₹5,00,000


def validate_inputs(inp: PolicyInput) -> int:
    """Run all 5 validations from the spec, return ACB age on success.

    Collects ALL errors (so the user sees every problem at once) and
    raises a single ValidationError carrying the list.
    """
    errors: List[str] = []

    age = age_acb(inp.dob, inp.quote_date)
    if not (AGE_MIN <= age <= AGE_MAX):
        errors.append(
            f"Age at entry must be between {AGE_MIN} and {AGE_MAX} (got {age})."
        )

    if not (PREMIUM_MIN <= inp.premium <= PREMIUM_MAX):
        errors.append(
            f"Annual premium must be between ₹{PREMIUM_MIN:,.0f} and ₹{PREMIUM_MAX:,.0f}."
        )

    if not (PT_MIN <= inp.premium_term <= PT_MAX):
        errors.append(
            f"Premium payment term must be between {PT_MIN} and {PT_MAX} years."
        )

    if not (POLICY_TERM_MIN <= inp.policy_term <= POLICY_TERM_MAX):
        errors.append(
            f"Policy term must be between {POLICY_TERM_MIN} and {POLICY_TERM_MAX} years."
        )

    if inp.policy_term <= inp.premium_term:
        errors.append("Policy term must be strictly greater than premium term.")

    sa_floor = max(Decimal("10") * inp.premium, SA_MIN_FLOOR)
    if inp.sum_assured < sa_floor:
        errors.append(
            f"Sum assured must be at least ₹{sa_floor:,.0f} "
            f"(max of 10× premium and ₹{SA_MIN_FLOOR:,.0f})."
        )

    if errors:
        raise ValidationError(errors)
    return age
