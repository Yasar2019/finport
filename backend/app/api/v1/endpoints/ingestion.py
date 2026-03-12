"""
Statement ingestion endpoints.
Handles file uploads, import session management, and status polling.
"""

import hashlib
import uuid
from pathlib import Path
from typing import Annotated

import magic
import structlog
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database.session import get_db_session
from app.models.import_session import ImportSession
from app.services.ingestion_service import IngestionService
from app.core.storage import get_storage_backend

logger = structlog.get_logger(__name__)
settings = get_settings()
router = APIRouter()

DbSession = Annotated[AsyncSession, Depends(get_db_session)]


@router.post("/upload", status_code=status.HTTP_202_ACCEPTED)
async def upload_statement(
    file: Annotated[UploadFile, File()],
    db: DbSession,
):
    """
    Upload a financial statement for processing.

    Security checks performed before accepting:
    - MIME type validation (magic bytes, not just extension)
    - File size limit enforcement (configurable via MAX_UPLOAD_SIZE_MB)
    - SHA-256 hash deduplication (same file from same user is idempotent)

    Returns an import_session_id that the client polls for status.
    """
    # 1. Read first 2048 bytes for MIME detection without loading full file
    header = await file.read(2048)
    detected_mime = magic.from_buffer(header, mime=True)

    if detected_mime not in settings.ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"File type '{detected_mime}' is not supported.",
        )

    # 2. Read remaining bytes and enforce size limit
    rest = await file.read()
    content = header + rest
    size_bytes = len(content)
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024

    if size_bytes > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum size of {settings.MAX_UPLOAD_SIZE_MB} MB.",
        )

    # 3. Compute SHA-256 for deduplication
    file_hash = hashlib.sha256(content).hexdigest()

    # 4. Determine file format from filename + MIME
    suffix = Path(file.filename or "unknown").suffix.lower().lstrip(".")
    file_format = _resolve_format(suffix, detected_mime)

    if not file_format:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Could not determine file format.",
        )

    service = IngestionService(db=db, storage=get_storage_backend())
    session = await service.create_import_session(
        user_id=uuid.UUID(settings.SINGLE_USER_ID),
        original_filename=file.filename or "unnamed",
        content=content,
        file_hash=file_hash,
        file_format=file_format,
        file_size_bytes=size_bytes,
    )

    return {
        "import_session_id": str(session.id),
        "status": session.status,
        "status_url": f"/api/v1/imports/{session.id}/status",
    }


@router.get(
    "/{session_id}/status", responses={404: {"description": "Import session not found"}}
)
async def get_import_status(session_id: uuid.UUID, db: DbSession):
    """Poll the processing status of an import session."""
    service = IngestionService(db=db, storage=get_storage_backend())
    session = await service.get_session(
        session_id, user_id=uuid.UUID(settings.SINGLE_USER_ID)
    )
    if not session:
        raise HTTPException(status_code=404, detail="Import session not found.")
    return {
        "import_session_id": str(session.id),
        "status": session.status,
        "original_filename": session.original_filename,
        "detected_institution": (
            str(session.detected_institution_id)
            if session.detected_institution_id
            else None
        ),
        "statement_period_start": session.statement_period_start,
        "statement_period_end": session.statement_period_end,
        "error_message": session.error_message,
        "completed_at": session.completed_at,
    }


@router.get("")
async def list_import_sessions(db: DbSession, limit: int = 50, offset: int = 0):
    """List all import sessions for the current user."""
    service = IngestionService(db=db, storage=get_storage_backend())
    sessions = await service.list_sessions(
        user_id=uuid.UUID(settings.SINGLE_USER_ID),
        limit=limit,
        offset=offset,
    )
    return {"items": sessions, "limit": limit, "offset": offset}


@router.post("/{session_id}/reprocess", status_code=status.HTTP_202_ACCEPTED)
async def reprocess_import(session_id: uuid.UUID, db: DbSession):
    """
    Re-run the parsing pipeline on an existing import session.
    Useful after a parser update or to retry a failed import.
    """
    service = IngestionService(db=db, storage=get_storage_backend())
    task_id = await service.enqueue_reprocess(
        session_id=session_id,
        user_id=uuid.UUID(settings.SINGLE_USER_ID),
    )
    return {"task_id": task_id, "message": "Reprocessing enqueued."}


def _resolve_format(suffix: str, mime: str) -> str | None:
    """Map file extension + MIME to a canonical format string."""
    if suffix in ("pdf",) or "pdf" in mime:
        return "pdf"
    if suffix in ("csv",) or mime in ("text/csv", "text/plain"):
        return "csv"
    if suffix in ("xlsx", "xls") or "excel" in mime or "spreadsheet" in mime:
        return "excel"
    if suffix in ("ofx", "qfx"):
        return "ofx"
    return None
