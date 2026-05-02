"""
Idempotent seeder for reference data (policy types + riders).

Run via: `python manage.py seed_reference`
"""

from datetime import date

from django.core.management.base import BaseCommand

from policies.models import PolicyType, PolicyVersion, Rider


POLICY_TYPES = [
    ("ENDOW", "Endowment Plan", "Traditional savings + protection plan."),
    ("TERM", "Term Plan", "Pure protection plan with no maturity benefit."),
    ("ULIP", "Unit-Linked Plan", "Investment + protection with market-linked returns."),
]

RIDERS = [
    ("ADB", "Accidental Death Benefit", "Pays additional SA on accidental death."),
    ("CI", "Critical Illness", "Lump sum on diagnosis of listed illnesses."),
    ("WOP", "Waiver of Premium", "Waives future premiums on disability."),
]


class Command(BaseCommand):
    help = "Seed reference data: policy types, riders, default policy version."

    def handle(self, *args, **options):
        for code, name, desc in POLICY_TYPES:
            obj, created = PolicyType.objects.get_or_create(
                code=code, defaults={"name": name, "description": desc}
            )
            self.stdout.write(("Created " if created else "Exists ") + str(obj))

        for code, name, desc in RIDERS:
            obj, created = Rider.objects.get_or_create(
                code=code, defaults={"name": name, "description": desc}
            )
            self.stdout.write(("Created " if created else "Exists ") + str(obj))

        endow = PolicyType.objects.get(code="ENDOW")
        PolicyVersion.objects.get_or_create(
            policy_type=endow,
            version="v1.0",
            defaults={
                "effective_from": date(2024, 1, 1),
                "notes": "Initial assumption set.",
            },
        )

        self.stdout.write(self.style.SUCCESS("Seed complete."))
