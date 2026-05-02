"""
Data-access layer.

Why a repository module instead of calling the ORM straight from views:
  * Keeps view code transport-only (request → DTO → domain → response).
  * Single chokepoint for query optimization (select_related, only-fields).
  * Unit-testable via stubs without spinning up Postgres.
"""

from __future__ import annotations

from typing import Iterable, Optional

from .models import PolicyQuote, PolicyType, Rider


class PolicyTypeRepository:
    @staticmethod
    def get_by_code(code: str) -> Optional[PolicyType]:
        return PolicyType.objects.filter(code=code, is_active=True).first()

    @staticmethod
    def list_active() -> Iterable[PolicyType]:
        return PolicyType.objects.filter(is_active=True).order_by("code")


class RiderRepository:
    @staticmethod
    def by_codes(codes: Iterable[str]) -> Iterable[Rider]:
        return Rider.objects.filter(code__in=list(codes), is_active=True)


class PolicyQuoteRepository:
    @staticmethod
    def find_idempotent(user_id: int, key: Optional[str]) -> Optional[PolicyQuote]:
        if not key:
            return None
        return (
            PolicyQuote.objects
            .filter(user_id=user_id, idempotency_key=key)
            .select_related("policy_type")
            .first()
        )

    @staticmethod
    def create(**fields) -> PolicyQuote:
        riders = fields.pop("riders", None)
        quote = PolicyQuote.objects.create(**fields)
        if riders:
            quote.riders.set(riders)
        return quote

    @staticmethod
    def for_user(user_id: int):
        return (
            PolicyQuote.objects
            .filter(user_id=user_id)
            .select_related("policy_type")
            .order_by("-created_at")
        )
