"""
Symmetric encryption helpers for sensitive PII at rest.

Strategy:
  * Fernet (AES-128-CBC + HMAC-SHA256) is used for reversibly encrypted
    fields like name, DOB, mobile. The key lives only in env (FIELD_ENCRYPTION_KEY).
  * For mobile we ALSO store a deterministic SHA-256 HMAC fingerprint
    so we can perform exact-match lookups without decrypting every row.
  * Custom Django model fields wrap encryption transparently so the rest
    of the codebase reads/writes plaintext while the DB only ever sees ciphertext.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import models


def _fernet() -> Fernet:
    key = settings.FIELD_ENCRYPTION_KEY
    if not key:
        raise RuntimeError("FIELD_ENCRYPTION_KEY is not configured")
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt(plaintext: Optional[str]) -> Optional[str]:
    if plaintext is None or plaintext == "":
        return plaintext
    token = _fernet().encrypt(plaintext.encode("utf-8"))
    return token.decode("utf-8")


def decrypt(token: Optional[str]) -> Optional[str]:
    if token is None or token == "":
        return token
    try:
        return _fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        return None


def fingerprint(plaintext: str) -> str:
    """
    Deterministic HMAC-SHA256 of a value, used for indexed equality lookups
    on encrypted fields (e.g. find user by mobile).
    """
    key = settings.FIELD_ENCRYPTION_KEY
    key_bytes = key.encode() if isinstance(key, str) else key
    return hmac.new(key_bytes, plaintext.encode("utf-8"), hashlib.sha256).hexdigest()


def mask_mobile(plaintext: Optional[str]) -> str:
    if not plaintext:
        return ""
    digits = "".join(c for c in plaintext if c.isdigit())
    if len(digits) <= 4:
        return "*" * len(digits)
    return "*" * (len(digits) - 4) + digits[-4:]


def mask_name(plaintext: Optional[str]) -> str:
    if not plaintext:
        return ""
    parts = plaintext.split()
    return " ".join((p[0] + "*" * (len(p) - 1)) if len(p) > 1 else p for p in parts)


def mask_dob(plaintext: Optional[str]) -> str:
    # ISO yyyy-mm-dd → ****-**-DD (keep year masked, day visible for support contexts)
    if not plaintext:
        return ""
    return "****-**-**"


class EncryptedCharField(models.TextField):
    """
    A TextField that transparently encrypts on save and decrypts on load.
    Stored as base64 ciphertext (Fernet token) in the DB.
    """

    description = "Symmetrically encrypted text field"

    def from_db_value(self, value, expression, connection):
        if value is None:
            return value
        return decrypt(value)

    def to_python(self, value):
        if value is None:
            return value
        # If it's plain text already (e.g. assigned in code), return as-is.
        if not isinstance(value, str):
            return value
        # Attempt decrypt; if it fails, assume plaintext.
        decrypted = decrypt(value)
        return decrypted if decrypted is not None else value

    def get_prep_value(self, value):
        if value is None:
            return value
        return encrypt(str(value))
