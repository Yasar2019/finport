"""
Storage abstraction layer.
Provides a common interface for file I/O that works with local filesystem today
and can be swapped for S3-compatible storage without changing callers.
"""

import os
import uuid
from abc import ABC, abstractmethod
from pathlib import Path

from cryptography.fernet import Fernet

from app.config import get_settings

settings = get_settings()


class StorageBackend(ABC):
    """Abstract storage interface. All implementations must be byte-for-byte identical."""

    @abstractmethod
    async def write(self, relative_path: str, content: bytes) -> str:
        """Write encrypted content. Returns the storage path."""
        ...

    @abstractmethod
    async def read(self, relative_path: str) -> bytes:
        """Read and decrypt content at relative_path."""
        ...

    @abstractmethod
    async def delete(self, relative_path: str) -> None:
        """Permanently delete a file."""
        ...

    @abstractmethod
    def build_path(
        self, user_id: uuid.UUID, session_id: uuid.UUID, filename: str
    ) -> str:
        """Construct a storage-safe path. Never uses the original filename on disk."""
        ...


class LocalEncryptedStorageBackend(StorageBackend):
    """
    Stores files encrypted at rest using Fernet (AES-128-CBC + HMAC-SHA256).
    Key sourced exclusively from STORAGE_ENCRYPTION_KEY env var.
    """

    def __init__(self):
        key = settings.STORAGE_ENCRYPTION_KEY.encode()
        self._fernet = Fernet(key)
        self._root = Path(settings.LOCAL_STORAGE_ROOT)
        self._root.mkdir(parents=True, exist_ok=True)

    def _full_path(self, relative_path: str) -> Path:
        # Prevent path traversal: resolve and assert it stays inside root
        full = (self._root / relative_path).resolve()
        if not str(full).startswith(str(self._root.resolve())):
            raise ValueError("Path traversal attempt detected.")
        return full

    async def write(self, relative_path: str, content: bytes) -> str:
        encrypted = self._fernet.encrypt(content)
        path = self._full_path(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(encrypted)
        return relative_path

    async def read(self, relative_path: str) -> bytes:
        path = self._full_path(relative_path)
        encrypted = path.read_bytes()
        return self._fernet.decrypt(encrypted)

    async def delete(self, relative_path: str) -> None:
        path = self._full_path(relative_path)
        if path.exists():
            path.unlink()

    def build_path(
        self, user_id: uuid.UUID, session_id: uuid.UUID, filename: str
    ) -> str:
        # UUID-based path — never uses original filename on disk
        ext = Path(filename).suffix.lower()
        return f"{user_id}/{session_id}/original{ext}"


# S3 backend error message constant to avoid repetition
_S3_NOT_IMPLEMENTED = "S3 storage backend not yet implemented."


class S3StorageBackend(StorageBackend):
    """
    S3-compatible storage backend (Phase 5).
    Stub implementation — replace with boto3/aiobotocore when needed.
    """

    async def write(self, relative_path: str, content: bytes) -> str:
        raise NotImplementedError(_S3_NOT_IMPLEMENTED)

    async def read(self, relative_path: str) -> bytes:
        raise NotImplementedError(_S3_NOT_IMPLEMENTED)

    async def delete(self, relative_path: str) -> None:
        raise NotImplementedError(_S3_NOT_IMPLEMENTED)

    def build_path(
        self, user_id: uuid.UUID, session_id: uuid.UUID, filename: str
    ) -> str:
        ext = Path(filename).suffix.lower()
        return f"{user_id}/{session_id}/original{ext}"


def get_storage_backend() -> StorageBackend:
    """Factory — returns the configured storage backend."""
    if settings.STORAGE_BACKEND == "s3":
        return S3StorageBackend()
    return LocalEncryptedStorageBackend()
