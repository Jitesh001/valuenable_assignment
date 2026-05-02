from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models

from .crypto import (
    EncryptedCharField,
    fingerprint,
    mask_dob,
    mask_mobile,
    mask_name,
)


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra):
        if not email:
            raise ValueError("Email is required")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        return self._create_user(email, password, **extra)


class User(AbstractUser):
    """
    Custom user keyed by email. Sensitive PII (name/dob/mobile) is encrypted
    at rest. We also keep an indexed deterministic HMAC of the mobile so
    that login / lookup by mobile works without scanning the table.
    """

    username = None
    email = models.EmailField(unique=True, db_index=True)

    # Encrypted PII — never stored in plaintext.
    full_name_enc = EncryptedCharField(null=True, blank=True)
    dob_enc = EncryptedCharField(null=True, blank=True)
    mobile_enc = EncryptedCharField(null=True, blank=True)

    # Deterministic fingerprint for lookups on encrypted mobile.
    mobile_fp = models.CharField(
        max_length=64, null=True, blank=True, db_index=True, unique=True
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    objects = UserManager()

    def set_mobile(self, mobile: str) -> None:
        self.mobile_enc = mobile
        self.mobile_fp = fingerprint(mobile) if mobile else None

    @property
    def masked_full_name(self) -> str:
        return mask_name(self.full_name_enc)

    @property
    def masked_mobile(self) -> str:
        return mask_mobile(self.mobile_enc)

    @property
    def masked_dob(self) -> str:
        return mask_dob(self.dob_enc)

    def __str__(self) -> str:  # pragma: no cover
        # NEVER include raw PII here — used in logs/admin.
        return f"User<{self.email}>"
