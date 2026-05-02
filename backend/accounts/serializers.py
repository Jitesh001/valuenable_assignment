import re
from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

User = get_user_model()

MOBILE_RE = re.compile(r"^[6-9]\d{9}$")  # Indian mobile pattern, 10 digits.


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True, required=True, validators=[validate_password], min_length=8
    )
    full_name = serializers.CharField(write_only=True, max_length=120, required=True)
    dob = serializers.DateField(write_only=True, required=True)
    mobile = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = User
        fields = ("email", "password", "full_name", "dob", "mobile")

    def validate_mobile(self, value: str) -> str:
        digits = re.sub(r"\D", "", value)
        if not MOBILE_RE.match(digits):
            raise serializers.ValidationError("Enter a valid 10-digit Indian mobile number.")
        return digits

    def validate_dob(self, value: date) -> date:
        if value >= date.today():
            raise serializers.ValidationError("DOB must be in the past.")
        return value

    def create(self, validated_data):
        full_name = validated_data.pop("full_name")
        dob = validated_data.pop("dob")
        mobile = validated_data.pop("mobile")
        password = validated_data.pop("password")

        user = User(email=validated_data["email"])
        user.full_name_enc = full_name
        user.dob_enc = dob.isoformat()
        user.set_mobile(mobile)
        user.set_password(password)
        user.save()
        return user


class UserSerializer(serializers.ModelSerializer):
    """Read serializer — emits MASKED versions of PII only."""

    full_name = serializers.CharField(source="masked_full_name", read_only=True)
    mobile = serializers.CharField(source="masked_mobile", read_only=True)
    dob = serializers.CharField(source="masked_dob", read_only=True)

    class Meta:
        model = User
        fields = ("id", "email", "full_name", "mobile", "dob", "created_at")
        read_only_fields = fields
