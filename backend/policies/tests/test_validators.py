"""
Unit tests for the pure-python validators + ACB age helper.

These tests deliberately avoid Django so they can run as `python -m pytest`
in any environment (including the bulk-processing worker image).
"""

from datetime import date
from decimal import Decimal

import pytest

from policies.domain.validators import (
    PolicyInput,
    ValidationError,
    age_acb,
    validate_inputs,
)


def _input(**overrides) -> PolicyInput:
    base = dict(
        dob=date(1990, 6, 15),
        quote_date=date(2024, 6, 15),  # exactly 34th birthday
        gender="M",
        premium=Decimal("20000"),
        premium_frequency="annual",
        premium_term=7,
        policy_term=15,
        sum_assured=Decimal("500000"),
    )
    base.update(overrides)
    return PolicyInput(**base)


# --- age_acb ----------------------------------------------------------------

class TestAgeACB:
    def test_birthday_today_counts_as_completed(self):
        assert age_acb(date(1990, 6, 15), date(2024, 6, 15)) == 34

    def test_day_before_birthday(self):
        assert age_acb(date(1990, 6, 15), date(2024, 6, 14)) == 33

    def test_day_after_birthday(self):
        assert age_acb(date(1990, 6, 15), date(2024, 6, 16)) == 34

    def test_leap_day_dob(self):
        # Born Feb 29 — on Feb 28 of a non-leap year, birthday hasn't happened.
        assert age_acb(date(2000, 2, 29), date(2024, 2, 28)) == 23
        assert age_acb(date(2000, 2, 29), date(2024, 3, 1)) == 24

    def test_quote_before_dob_raises(self):
        with pytest.raises(ValueError):
            age_acb(date(2000, 1, 1), date(1999, 12, 31))


# --- validate_inputs --------------------------------------------------------

class TestValidations:
    def test_happy_path_returns_age(self):
        assert validate_inputs(_input()) == 34

    def test_age_below_floor(self):
        with pytest.raises(ValidationError) as exc:
            validate_inputs(_input(dob=date(2010, 1, 1), quote_date=date(2024, 1, 1)))
        assert any("Age" in m for m in exc.value.errors)

    def test_age_above_ceiling(self):
        with pytest.raises(ValidationError) as exc:
            validate_inputs(_input(dob=date(1960, 1, 1), quote_date=date(2024, 1, 1)))
        assert any("Age" in m for m in exc.value.errors)

    def test_premium_below_floor(self):
        with pytest.raises(ValidationError) as exc:
            validate_inputs(_input(premium=Decimal("5000"), sum_assured=Decimal("500000")))
        assert any("premium" in m.lower() for m in exc.value.errors)

    def test_premium_above_ceiling(self):
        with pytest.raises(ValidationError) as exc:
            validate_inputs(_input(premium=Decimal("60000"), sum_assured=Decimal("600000")))
        assert any("premium" in m.lower() for m in exc.value.errors)

    def test_premium_term_out_of_range(self):
        with pytest.raises(ValidationError):
            validate_inputs(_input(premium_term=4, policy_term=12))
        with pytest.raises(ValidationError):
            validate_inputs(_input(premium_term=11, policy_term=15))

    def test_policy_term_out_of_range(self):
        with pytest.raises(ValidationError):
            validate_inputs(_input(policy_term=9, premium_term=5))
        with pytest.raises(ValidationError):
            validate_inputs(_input(policy_term=21, premium_term=8))

    def test_policy_term_must_exceed_premium_term(self):
        with pytest.raises(ValidationError) as exc:
            validate_inputs(_input(premium_term=10, policy_term=10))
        assert any("greater" in m for m in exc.value.errors)

    def test_sum_assured_floor_500k(self):
        with pytest.raises(ValidationError) as exc:
            validate_inputs(_input(premium=Decimal("10000"), sum_assured=Decimal("400000")))
        assert any("Sum assured" in m for m in exc.value.errors)

    def test_sum_assured_floor_10x_premium(self):
        # premium 50k → 10× = 5,00,000; SA 4,00,000 must fail because floor=max(5L,5L)=5L,
        # use a clearer case where 10× dominates: premium 60k blocked already, so test 50k OK.
        # Use SA below 10× premium.
        with pytest.raises(ValidationError):
            validate_inputs(_input(premium=Decimal("50000"), sum_assured=Decimal("499999")))

    def test_collects_all_errors_at_once(self):
        with pytest.raises(ValidationError) as exc:
            validate_inputs(
                _input(
                    dob=date(2010, 1, 1),
                    quote_date=date(2024, 1, 1),
                    premium=Decimal("5000"),
                    premium_term=2,
                    policy_term=3,
                    sum_assured=Decimal("100000"),
                )
            )
        assert len(exc.value.errors) >= 4
