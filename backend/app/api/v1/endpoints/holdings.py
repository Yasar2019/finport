"""Holdings endpoint."""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database.session import get_db_session
from app.services.holdings_service import HoldingsService

router = APIRouter()
settings = get_settings()
DbSession = Annotated[AsyncSession, Depends(get_db_session)]


@router.get("")
async def list_holdings(
    db: DbSession,
    account_id: uuid.UUID | None = Query(None),
    as_of_date: date | None = Query(
        None, description="Defaults to latest available date"
    ),
):
    """
    Return current holdings, optionally filtered by account and date.
    When as_of_date is omitted, returns the most recent snapshot per account.
    """
    service = HoldingsService(db)
    return await service.get_holdings(
        user_id=uuid.UUID(settings.SINGLE_USER_ID),
        account_id=account_id,
        as_of_date=as_of_date,
    )


@router.get("/summary")
async def holdings_summary(db: DbSession):
    """
    Aggregated holdings summary: total market value, allocation by asset class,
    top positions by weight.
    """
    service = HoldingsService(db)
    return await service.get_holdings_summary(
        user_id=uuid.UUID(settings.SINGLE_USER_ID)
    )
