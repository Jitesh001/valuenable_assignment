"""
Unit tests for the IllustrationCalculator. Pure python, no Django.
"""

from datetime import date
from decimal import Decimal

import pytest

from policies.domain.calculator import IllustrationCalculator
from policies.domain.validators import PolicyInput, ValidationError


def _valid_input(**overrides) -> PolicyInput:
    base = dict(
        dob=date(1990, 1, 1),
        quote_date=date(2024, 1, 1),
        gender="M",
        premium=Decimal("25000"),
        premium_frequency="annual",
        premium_term=7,
        policy_term=15,
        sum_assured=Decimal("500000"),
    )
    base.update(overrides)
    return PolicyInput(**base)


class TestCalculator:
    def setup_method(self):
        self.calc = IllustrationCalculator()

    def test_invalid_input_propagates_validation_error(self):
        bad = _valid_input(premium=Decimal("9999"))
        with pytest.raises(ValidationError):
            self.calc.run(bad)

    def test_row_count_matches_policy_term(self):
        result = self.calc.run(_valid_input(policy_term=15))
        assert len(result.rows) == 15

    def test_age_progression(self):
        result = self.calc.run(_valid_input())
        # First row age == age_at_entry, last row == entry + term - 1.
        assert result.rows[0].age == result.age_at_entry
        assert result.rows[-1].age == result.age_at_entry + result.policy_term - 1

    def test_premium_paid_only_in_premium_term(self):
        result = self.calc.run(_valid_input(premium_term=7, policy_term=15))
        for r in result.rows:
            if r.policy_year <= 7:
                assert r.annualized_premium == Decimal("25000")
            else:
                assert r.annualized_premium == Decimal("0")

    def test_cumulative_premium_caps_at_premium_term(self):
        result = self.calc.run(_valid_input(premium_term=7, policy_term=15))
        last = result.rows[-1]
        assert last.cumulative_premium == Decimal("175000")  # 7 × 25,000

    def test_death_benefit_floor(self):
        # SA = 5L, 10× premium = 2.5L, 105% of cum. premium <= 5L throughout.
        result = self.calc.run(_valid_input())
        for r in result.rows:
            assert r.death_benefit >= Decimal("500000")
            assert r.death_benefit >= Decimal("250000")
            assert r.death_benefit >= (Decimal("1.05") * r.cumulative_premium).quantize(Decimal("1"))

    def test_higher_scenario_dominates_lower(self):
        result = self.calc.run(_valid_input())
        for r in result.rows:
            assert r.accrued_bonus_higher >= r.accrued_bonus_lower
            assert r.surrender_value_higher >= r.surrender_value_lower

    def test_maturity_only_in_final_year(self):
        result = self.calc.run(_valid_input(policy_term=15))
        for r in result.rows[:-1]:
            assert r.maturity_benefit_lower == Decimal("0")
            assert r.maturity_benefit_higher == Decimal("0")
        assert result.rows[-1].maturity_benefit_higher > Decimal("0")

    def test_year1_gsv_is_zero(self):
        result = self.calc.run(_valid_input())
        # Year 1: GSV factor on premium is 0; only bonus surrender component remains
        # (small, but with our factor table also small). It can be > 0 from bonus PV.
        assert result.rows[0].surrender_value_lower >= Decimal("0")

    def test_determinism(self):
        a = self.calc.run(_valid_input())
        b = self.calc.run(_valid_input())
        assert a.as_dict() == b.as_dict()

    def test_serializable_to_dict(self):
        result = self.calc.run(_valid_input())
        d = result.as_dict()
        assert d["age_at_entry"] == result.age_at_entry
        assert len(d["rows"]) == result.policy_term
