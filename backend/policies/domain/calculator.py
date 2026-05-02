"""
Benefit illustration calculation engine.

Design notes
------------
* Pure Python, no Django/DRF imports — drop-in for workers, CLIs, or tests.
* Deterministic: same input ⇒ exactly the same output. All money is `Decimal`.
* IRDAI-style two-scenario projection (lower/higher) so the structure mirrors
  what a real insurer's illustration sheet contains. The exact factor tables
  below are illustrative — in production they'd be loaded from a versioned
  PolicyVersion / ProductConfig table so calculation logic can evolve without
  schema-breaking changes.
* The single public entry point is `IllustrationCalculator.run(inp) -> IllustrationResult`.

What's modelled per policy year
-------------------------------
- Annualized premium (and cumulative premium paid)
- Death benefit                     = max(SA, 10× annual premium, 105% of cumulative premium)
- Guaranteed Surrender Value (GSV)  = GSV factor × cumulative premium  (+ cash value of vested bonus × GSV bonus factor)
- Reversionary bonus (per scenario) = bonus rate × SA × years bonus has accrued
- Special Surrender Value (SSV)     = max(GSV, accrued bonus PV proxy)  — illustrative
- Maturity benefit (final year)     = SA + accrued bonus + terminal bonus
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import List, Mapping, Tuple

from .validators import PolicyInput, validate_inputs


# --- Configuration tables --------------------------------------------------------
#
# In a real product these would be versioned and loaded from the DB so we can
# A/B different assumption sets and keep historical illustrations reproducible.

# IRDAI mandates two illustrative scenarios. Names kept generic.
SCENARIO_LOWER = "lower"
SCENARIO_HIGHER = "higher"

# Reversionary bonus per ₹1000 of SA per year, by scenario.
BONUS_PER_1000_SA: Mapping[str, Decimal] = {
    SCENARIO_LOWER: Decimal("30"),    # ~3.0% of SA
    SCENARIO_HIGHER: Decimal("55"),   # ~5.5% of SA
}

# Terminal / loyalty bonus on maturity, as a % of SA.
TERMINAL_BONUS_PCT: Mapping[str, Decimal] = {
    SCENARIO_LOWER: Decimal("0.05"),    # 5% of SA
    SCENARIO_HIGHER: Decimal("0.12"),   # 12% of SA
}

# Investment-return assumptions used as the headline rate on the illustration.
# Per IRDAI norms these are typically 4% and 8% gross.
ASSUMED_GROSS_RETURN: Mapping[str, Decimal] = {
    SCENARIO_LOWER: Decimal("0.04"),
    SCENARIO_HIGHER: Decimal("0.08"),
}

# Guaranteed Surrender Value factors as % of cumulative premium paid by policy year.
# These follow IRDAI minimum GSV percentages (illustrative, simplified).
GSV_FACTORS: Tuple[Decimal, ...] = (
    Decimal("0.00"),  # year 1
    Decimal("0.30"),  # year 2
    Decimal("0.35"),  # year 3
    Decimal("0.50"),  # year 4
    Decimal("0.50"),  # year 5
    Decimal("0.50"),  # year 6
    Decimal("0.55"),  # year 7
    Decimal("0.60"),  # year 8
    Decimal("0.65"),  # year 9
    Decimal("0.70"),  # year 10
    Decimal("0.75"),  # year 11
    Decimal("0.80"),  # year 12
    Decimal("0.85"),  # year 13
    Decimal("0.88"),  # year 14
    Decimal("0.90"),  # year 15+
)

# Surrender value of vested bonus = GSV bonus factor × accrued bonus.
# Steps up roughly with policy year.
def _gsv_bonus_factor(policy_year: int, policy_term: int) -> Decimal:
    progress = Decimal(policy_year) / Decimal(policy_term)
    if progress <= Decimal("0.25"):
        return Decimal("0.15")
    if progress <= Decimal("0.50"):
        return Decimal("0.20")
    if progress <= Decimal("0.75"):
        return Decimal("0.30")
    return Decimal("0.50")


def _gsv_factor(policy_year: int) -> Decimal:
    idx = min(policy_year - 1, len(GSV_FACTORS) - 1)
    return GSV_FACTORS[idx]


def _round_money(value: Decimal) -> Decimal:
    """Round to nearest rupee, banker-safe HALF_UP — what insurers print."""
    return value.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


# --- Output types ---------------------------------------------------------------


@dataclass(frozen=True)
class IllustrationRow:
    policy_year: int
    age: int
    annualized_premium: Decimal
    cumulative_premium: Decimal
    death_benefit: Decimal
    # Per-scenario projections.
    accrued_bonus_lower: Decimal
    accrued_bonus_higher: Decimal
    surrender_value_lower: Decimal
    surrender_value_higher: Decimal
    maturity_benefit_lower: Decimal
    maturity_benefit_higher: Decimal

    def as_dict(self) -> dict:
        return {
            "policy_year": self.policy_year,
            "age": self.age,
            "annualized_premium": str(self.annualized_premium),
            "cumulative_premium": str(self.cumulative_premium),
            "death_benefit": str(self.death_benefit),
            "accrued_bonus_lower": str(self.accrued_bonus_lower),
            "accrued_bonus_higher": str(self.accrued_bonus_higher),
            "surrender_value_lower": str(self.surrender_value_lower),
            "surrender_value_higher": str(self.surrender_value_higher),
            "maturity_benefit_lower": str(self.maturity_benefit_lower),
            "maturity_benefit_higher": str(self.maturity_benefit_higher),
        }


@dataclass(frozen=True)
class IllustrationResult:
    age_at_entry: int
    annualized_premium: Decimal
    sum_assured: Decimal
    policy_term: int
    premium_term: int
    rows: List[IllustrationRow] = field(default_factory=list)
    assumed_return_lower: Decimal = ASSUMED_GROSS_RETURN[SCENARIO_LOWER]
    assumed_return_higher: Decimal = ASSUMED_GROSS_RETURN[SCENARIO_HIGHER]

    def as_dict(self) -> dict:
        return {
            "age_at_entry": self.age_at_entry,
            "annualized_premium": str(self.annualized_premium),
            "sum_assured": str(self.sum_assured),
            "policy_term": self.policy_term,
            "premium_term": self.premium_term,
            "assumed_return_lower": str(self.assumed_return_lower),
            "assumed_return_higher": str(self.assumed_return_higher),
            "rows": [r.as_dict() for r in self.rows],
        }


# --- The engine -----------------------------------------------------------------


class IllustrationCalculator:
    """
    Orchestrates validation + per-year illustration generation.

    Stateless: a single instance is safe to share across threads / requests
    because it never mutates `self`. This makes it cheap to call from a
    worker handling millions of rows.
    """

    def run(self, inp: PolicyInput) -> IllustrationResult:
        age_at_entry = validate_inputs(inp)

        annual_premium = Decimal(inp.premium)
        sa = Decimal(inp.sum_assured)

        rows: List[IllustrationRow] = []
        cumulative_premium = Decimal("0")
        accrued_bonus = {SCENARIO_LOWER: Decimal("0"), SCENARIO_HIGHER: Decimal("0")}

        # Per-year bonus accrual: rate × SA / 1000.
        per_year_bonus = {
            scen: (BONUS_PER_1000_SA[scen] * sa) / Decimal("1000")
            for scen in (SCENARIO_LOWER, SCENARIO_HIGHER)
        }

        for year in range(1, inp.policy_term + 1):
            age = age_at_entry + year - 1

            # Premium is paid only during the premium term.
            paid_this_year = annual_premium if year <= inp.premium_term else Decimal("0")
            cumulative_premium += paid_this_year

            # Bonuses accrue every year the policy is in force.
            for scen in (SCENARIO_LOWER, SCENARIO_HIGHER):
                accrued_bonus[scen] += per_year_bonus[scen]

            # Death benefit: industry-standard floor.
            death_benefit = max(
                sa,
                Decimal("10") * annual_premium,
                Decimal("1.05") * cumulative_premium,
            )

            # Surrender values per scenario.
            gsv_prem = _gsv_factor(year) * cumulative_premium
            gsv_bonus_factor = _gsv_bonus_factor(year, inp.policy_term)

            sv = {}
            for scen in (SCENARIO_LOWER, SCENARIO_HIGHER):
                gsv_total = gsv_prem + gsv_bonus_factor * accrued_bonus[scen]
                # SSV proxy: at minimum the GSV; never below zero.
                sv[scen] = max(gsv_total, Decimal("0"))

            # Maturity benefit only crystallises in the final policy year.
            maturity = {SCENARIO_LOWER: Decimal("0"), SCENARIO_HIGHER: Decimal("0")}
            if year == inp.policy_term:
                for scen in (SCENARIO_LOWER, SCENARIO_HIGHER):
                    terminal = TERMINAL_BONUS_PCT[scen] * sa
                    maturity[scen] = sa + accrued_bonus[scen] + terminal

            rows.append(
                IllustrationRow(
                    policy_year=year,
                    age=age,
                    annualized_premium=_round_money(paid_this_year),
                    cumulative_premium=_round_money(cumulative_premium),
                    death_benefit=_round_money(death_benefit),
                    accrued_bonus_lower=_round_money(accrued_bonus[SCENARIO_LOWER]),
                    accrued_bonus_higher=_round_money(accrued_bonus[SCENARIO_HIGHER]),
                    surrender_value_lower=_round_money(sv[SCENARIO_LOWER]),
                    surrender_value_higher=_round_money(sv[SCENARIO_HIGHER]),
                    maturity_benefit_lower=_round_money(maturity[SCENARIO_LOWER]),
                    maturity_benefit_higher=_round_money(maturity[SCENARIO_HIGHER]),
                )
            )

        return IllustrationResult(
            age_at_entry=age_at_entry,
            annualized_premium=_round_money(annual_premium),
            sum_assured=_round_money(sa),
            policy_term=inp.policy_term,
            premium_term=inp.premium_term,
            rows=rows,
        )
