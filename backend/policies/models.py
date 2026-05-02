"""
Policy domain models.

Designed for extensibility:
  * `PolicyType` and `Rider` are reference tables — adding a new product or rider
    is a data-only change, no schema migration required for the calculator.
  * `PolicyVersion` lets us version the calculation logic / factor tables alongside
    the policy snapshot, so historical illustrations remain reproducible.
  * `PolicyQuote` is an audit trail of every illustration request — useful for
    compliance, reproducibility, and bulk-pipeline retries.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models


class PolicyType(models.Model):
    """Reference data — e.g. 'Endowment', 'ULIP', 'Term'."""

    code = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["code"])]

    def __str__(self) -> str:
        return f"{self.code} — {self.name}"


class Rider(models.Model):
    """Optional add-ons that can be attached to a policy."""

    code = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self) -> str:
        return f"{self.code} — {self.name}"


class PremiumFrequency(models.TextChoices):
    ANNUAL = "annual", "Annual"
    SEMI = "semi", "Semi-Annual"
    QUARTERLY = "quarterly", "Quarterly"
    MONTHLY = "monthly", "Monthly"


class PolicyVersion(models.Model):
    """
    Snapshot of the assumption set used for a calculation. Bumping `version`
    when the calculator's factor tables change keeps old illustrations
    reproducible without rewriting calculator code.
    """

    policy_type = models.ForeignKey(
        PolicyType, on_delete=models.PROTECT, related_name="versions"
    )
    version = models.CharField(max_length=20)
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        unique_together = ("policy_type", "version")
        indexes = [models.Index(fields=["policy_type", "effective_from"])]

    def __str__(self) -> str:
        return f"{self.policy_type.code}@{self.version}"


class PolicyQuote(models.Model):
    """
    A single illustration request + its computed result.

    Indexed on (user, created_at) so we can paginate a user's history fast.
    The full row payload is kept as JSON — denormalized on purpose: writing
    is the hot path (millions/run), reads are infrequent and structured.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="quotes"
    )
    policy_type = models.ForeignKey(PolicyType, on_delete=models.PROTECT)
    policy_version = models.ForeignKey(
        PolicyVersion, on_delete=models.PROTECT, null=True, blank=True
    )
    riders = models.ManyToManyField(Rider, blank=True)

    # Snapshotted inputs (so a later version-bump can't mutate history).
    age_at_entry = models.PositiveSmallIntegerField()
    gender = models.CharField(max_length=1)
    premium = models.DecimalField(max_digits=12, decimal_places=2)
    premium_frequency = models.CharField(
        max_length=16,
        choices=PremiumFrequency.choices,
        default=PremiumFrequency.ANNUAL,
    )
    premium_term = models.PositiveSmallIntegerField()
    policy_term = models.PositiveSmallIntegerField()
    sum_assured = models.DecimalField(max_digits=14, decimal_places=2)

    # Idempotency: clients may pass an Idempotency-Key to replay the same
    # request without re-doing the work. (See API layer.)
    idempotency_key = models.CharField(
        max_length=64, null=True, blank=True, db_index=True
    )

    # Computed output kept as JSONB for fast reads / flexible schema evolution.
    result = models.JSONField()

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["policy_type", "-created_at"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "idempotency_key"],
                name="uniq_user_idempotency_key",
                condition=models.Q(idempotency_key__isnull=False),
            ),
        ]

    def __str__(self) -> str:
        return f"Quote#{self.pk} ({self.policy_type.code})"
