"""Reconciliation endpoint."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database.session import get_db_session
from app.services.reconciliation_service import ReconciliationService

router = APIRouter()
settings = get_settings()
DbSession = Annotated[AsyncSession, Depends(get_db_session)]


@router.get("/issues")
async def list_issues(
    db: DbSession,
    severity: str | None = Query(None, pattern="^(info|warning|error)$"),
    status: str | None = Query("open", pattern="^(open|resolved|dismissed|all)$"),
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
):
    """
    List open reconciliation issues.
    Default: open issues only, sorted by severity desc.
    """
    service = ReconciliationService(db)
    return await service.list_issues(
        user_id=uuid.UUID(settings.SINGLE_USER_ID),
        severity=severity,
        status=status if status != "all" else None,
        limit=limit,
        offset=offset,
    )


@router.get("/summary")
async def reconciliation_summary(db: DbSession):
    """Count of open issues by severity — for the dashboard widget."""
    service = ReconciliationService(db)
    return await service.get_summary(user_id=uuid.UUID(settings.SINGLE_USER_ID))


@router.post("/issues/{issue_id}/resolve")
async def resolve_issue(issue_id: uuid.UUID, payload: dict, db: DbSession):
    """
    Mark a reconciliation issue as resolved.
    Requires a resolution_note if not auto-resolved.
    """
    service = ReconciliationService(db)
    return await service.resolve_issue(
        issue_id=issue_id,
        user_id=uuid.UUID(settings.SINGLE_USER_ID),
        resolution_note=payload.get("resolution_note", ""),
    )


@router.post("/issues/{issue_id}/dismiss")
async def dismiss_issue(issue_id: uuid.UUID, db: DbSession):
    """Dismiss a reconciliation issue (won't affect portfolio data)."""
    service = ReconciliationService(db)
    return await service.dismiss_issue(
        issue_id=issue_id,
        user_id=uuid.UUID(settings.SINGLE_USER_ID),
    )
