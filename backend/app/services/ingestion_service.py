"""
Ingestion service — coordinates file acceptance and job dispatch.
"""

import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.storage import StorageBackend
from app.models.import_session import ImportSession

logger = structlog.get_logger(__name__)


class IngestionService:
    def __init__(self, db: AsyncSession, storage: StorageBackend):
        self._db = db
        self._storage = storage

    async def create_import_session(
        self,
        user_id: uuid.UUID,
        original_filename: str,
        content: bytes,
        file_hash: str,
        file_format: str,
        file_size_bytes: int,
    ) -> ImportSession:
        """
        Idempotent: if file_hash already exists for this user, return the existing session.
        Otherwise, encrypt and store the file, create an ImportSession, and enqueue the pipeline.
        """
        # Deduplication check
        existing = await self._db.execute(
            select(ImportSession).where(
                ImportSession.user_id == user_id,
                ImportSession.file_hash == file_hash,
            )
        )
        existing_session = existing.scalar_one_or_none()
        if existing_session:
            logger.info("ingestion.duplicate_detected", file_hash=file_hash)
            return existing_session

        # Build storage path and encrypt file
        session_id = uuid.uuid4()
        storage_path = self._storage.build_path(user_id, session_id, original_filename)
        await self._storage.write(storage_path, content)

        # Create DB record
        session = ImportSession(
            id=session_id,
            user_id=user_id,
            original_filename=original_filename,
            file_hash=file_hash,
            storage_path=storage_path,
            file_format=file_format,
            file_size_bytes=file_size_bytes,
            status="queued",
        )
        self._db.add(session)
        await self._db.flush()

        # Enqueue background task
        from app.workers.tasks import run_ingestion_pipeline

        run_ingestion_pipeline.delay(import_session_id=str(session.id))  # type: ignore[attr-defined]

        logger.info("ingestion.session_created", session_id=str(session.id))
        return session

    async def get_session(
        self, session_id: uuid.UUID, user_id: uuid.UUID
    ) -> ImportSession | None:
        result = await self._db.execute(
            select(ImportSession).where(
                ImportSession.id == session_id,
                ImportSession.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_sessions(
        self, user_id: uuid.UUID, limit: int = 50, offset: int = 0
    ) -> list[ImportSession]:
        result = await self._db.execute(
            select(ImportSession)
            .where(ImportSession.user_id == user_id)
            .order_by(ImportSession.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def enqueue_reprocess(self, session_id: uuid.UUID, user_id: uuid.UUID) -> str:
        session = await self.get_session(session_id, user_id)
        if not session:
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="Import session not found.")
        session.status = "queued"
        await self._db.flush()
        from app.workers.tasks import run_ingestion_pipeline

        task = run_ingestion_pipeline.delay(import_session_id=str(session.id))  # type: ignore[attr-defined]
        return task.id
