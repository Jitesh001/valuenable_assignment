from datetime import date
from decimal import Decimal

from rest_framework import serializers

from .domain import PolicyInput
from .models import PolicyQuote, PolicyType, PremiumFrequency, Rider


class PolicyTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = PolicyType
        fields = ("code", "name", "description")


class RiderSerializer(serializers.ModelSerializer):
    class Meta:
        model = Rider
        fields = ("code", "name", "description")


class IllustrationRequestSerializer(serializers.Serializer):
    """
    Wire-format → DTO. Note: this serializer does only structural validation
    (types, ranges that the framework enforces cheaply). The 5 business
    validations live in `domain.validators` so they can run outside DRF.
    """

    policy_type = serializers.CharField(max_length=32)
    dob = serializers.DateField()
    quote_date = serializers.DateField(required=False)
    gender = serializers.ChoiceField(choices=("M", "F", "O"))
    premium = serializers.DecimalField(max_digits=12, decimal_places=2)
    premium_frequency = serializers.ChoiceField(
        choices=PremiumFrequency.choices, default=PremiumFrequency.ANNUAL
    )
    premium_term = serializers.IntegerField(min_value=1, max_value=50)
    policy_term = serializers.IntegerField(min_value=1, max_value=99)
    sum_assured = serializers.DecimalField(max_digits=14, decimal_places=2)
    riders = serializers.ListField(
        child=serializers.CharField(max_length=32), required=False, default=list
    )

    def to_domain(self) -> PolicyInput:
        data = self.validated_data
        return PolicyInput(
            dob=data["dob"],
            quote_date=data.get("quote_date") or date.today(),
            gender=data["gender"],
            premium=Decimal(data["premium"]),
            premium_frequency=data["premium_frequency"],
            premium_term=data["premium_term"],
            policy_term=data["policy_term"],
            sum_assured=Decimal(data["sum_assured"]),
            rider_codes=tuple(data.get("riders", [])),
        )


class PolicyQuoteSerializer(serializers.ModelSerializer):
    policy_type = serializers.CharField(source="policy_type.code", read_only=True)

    class Meta:
        model = PolicyQuote
        fields = (
            "id",
            "policy_type",
            "age_at_entry",
            "gender",
            "premium",
            "premium_frequency",
            "premium_term",
            "policy_term",
            "sum_assured",
            "result",
            "created_at",
        )
        read_only_fields = fields
