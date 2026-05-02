"""
Application service: glues API DTOs ↔ domain ↔ repository.

Views should stay thin — they delegate to this layer. The benefit is that
the same service is reusable from a Celery worker doing bulk processing
(see project_details.md → Scalability) without dragging request/response
objects into business logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .domain import IllustrationCalculator, PolicyInput, ValidationError
from .models import PolicyQuote
from .repositories import PolicyQuoteRepository, PolicyTypeRepository, RiderRepository


@dataclass
class IllustrationCommand:
    user_id: int
    policy_type_code: str
    domain_input: PolicyInput
    idempotency_key: Optional[str] = None
    persist: bool = True


class PolicyTypeNotFound(Exception):
    pass


class IllustrationService:
    def __init__(self, calculator: Optional[IllustrationCalculator] = None):
        self.calculator = calculator or IllustrationCalculator()

    def illustrate(self, cmd: IllustrationCommand) -> PolicyQuote | dict:
        # Idempotency short-circuit: if we've seen this request, replay.
        existing = PolicyQuoteRepository.find_idempotent(cmd.user_id, cmd.idempotency_key)
        if existing is not None:
            return existing

        policy_type = PolicyTypeRepository.get_by_code(cmd.policy_type_code)
        if policy_type is None:
            raise PolicyTypeNotFound(cmd.policy_type_code)

        # Run the engine — this raises ValidationError on bad input.
        result = self.calculator.run(cmd.domain_input)

        if not cmd.persist:
            return {
                "policy_type": policy_type.code,
                "result": result.as_dict(),
            }

        riders = list(RiderRepository.by_codes(cmd.domain_input.rider_codes))

        quote = PolicyQuoteRepository.create(
            user_id=cmd.user_id,
            policy_type=policy_type,
            riders=riders,
            age_at_entry=result.age_at_entry,
            gender=cmd.domain_input.gender,
            premium=cmd.domain_input.premium,
            premium_frequency=cmd.domain_input.premium_frequency,
            premium_term=cmd.domain_input.premium_term,
            policy_term=cmd.domain_input.policy_term,
            sum_assured=cmd.domain_input.sum_assured,
            idempotency_key=cmd.idempotency_key,
            result=result.as_dict(),
        )
        return quote


__all__ = [
    "IllustrationCommand",
    "IllustrationService",
    "PolicyTypeNotFound",
    "ValidationError",
]
