"""Transactions endpoint."""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database.session import get_db_session
from app.services.transaction_service import TransactionService

router = APIRouter()
settings = get_settings()
DbSession = Annotated[AsyncSession, Depends(get_db_session)]


@router.get("/")
async def list_transactions(
    db: DbSession,
    account_id: uuid.UUID | None = Query(None),
    transaction_type: str | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    search: str | None = Query(None, max_length=200),
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
):
    """
    List transactions with filtering.
    Supports filtering by account, type, date range, and text search on description.
    """
    service = TransactionService(db)
    results = await service.list_transactions(
        user_id=uuid.UUID(settings.SINGLE_USER_ID),
        account_id=account_id,
        transaction_type=transaction_type,
        date_from=date_from,
        date_to=date_to,
        search=search,
        limit=limit,
        offset=offset,
    )
    return results


@router.get("/{transaction_id}")
async def get_transaction(transaction_id: uuid.UUID, db: DbSession):
    """Get a single transaction with full provenance details."""
    service = TransactionService(db)
    return await service.get_transaction(
        transaction_id=transaction_id,
        user_id=uuid.UUID(settings.SINGLE_USER_ID),
    )


@router.patch("/{transaction_id}")
async def update_transaction(transaction_id: uuid.UUID, payload: dict, db: DbSession):
    """
    Manually correct a transaction (type, amount, security, date).
    All manual edits are recorded in audit_logs.
    """
    service = TransactionService(db)
    return await service.update_transaction(
        transaction_id=transaction_id,
        user_id=uuid.UUID(settings.SINGLE_USER_ID),
        updates=payload,
    )
