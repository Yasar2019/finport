"""
Custom SQLAlchemy type decorators for sensitive data handling.
"""

from typing import Any

from cryptography.fernet import Fernet
from sqlalchemy import LargeBinary, TypeDecorator

from app.config import get_settings


class EncryptedString(TypeDecorator):
    """
    Application-layer AES encryption for sensitive string columns.
    Stored as BYTEA in the database; transparently decrypted on load.
    Key is sourced from STORAGE_ENCRYPTION_KEY env var.
    """

    impl = LargeBinary
    cache_ok = True

    def _get_fernet(self) -> Fernet:
        settings = get_settings()
        key = settings.STORAGE_ENCRYPTION_KEY.encode()
        return Fernet(key)

    def process_bind_param(self, value: str | None, dialect: Any) -> bytes | None:
        """Encrypt before writing to DB."""
        if value is None:
            return None
        return self._get_fernet().encrypt(value.encode("utf-8"))

    def process_result_value(self, value: bytes | None, dialect: Any) -> str | None:
        """Decrypt after reading from DB."""
        if value is None:
            return None
        return self._get_fernet().decrypt(value).decode("utf-8")
