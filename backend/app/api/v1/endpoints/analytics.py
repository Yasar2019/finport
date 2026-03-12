"""Analytics endpoint."""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database.session import get_db_session
from app.services.analytics_service import AnalyticsService

router = APIRouter()
settings = get_settings()
DbSession = Annotated[AsyncSession, Depends(get_db_session)]


@router.get("/net-worth")
async def net_worth_history(
    db: DbSession,
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
):
    """
    Consolidated net worth over time (time-series from valuations).
    Suitable for the main portfolio balance chart.
    """
    service = AnalyticsService(db)
    return await service.get_net_worth_history(
        user_id=uuid.UUID(settings.SINGLE_USER_ID),
        date_from=date_from,
        date_to=date_to,
    )


@router.get("/allocation")
async def portfolio_allocation(db: DbSession):
    """
    Current portfolio allocation breakdowns:
    - by asset class
    - by sector
    - by account
    - by currency
    """
    service = AnalyticsService(db)
    return await service.get_allocation(user_id=uuid.UUID(settings.SINGLE_USER_ID))


@router.get("/performance")
async def performance(
    db: DbSession,
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
):
    """
    Realised and unrealised gains/losses.
    Uses FIFO tax-lot method by default.
    Output is analytics data only — not financial advice.
    """
    service = AnalyticsService(db)
    return await service.get_performance(
        user_id=uuid.UUID(settings.SINGLE_USER_ID),
        date_from=date_from,
        date_to=date_to,
    )


@router.get("/dividends")
async def dividend_income(
    db: DbSession,
    year: Annotated[int | None, Query()] = None,
    group_by: Annotated[
        str, Query(pattern="^(month|quarter|year|security)$")
    ] = "month",
):
    """Dividend income history grouped by the specified period or security."""
    service = AnalyticsService(db)
    return await service.get_dividend_income(
        user_id=uuid.UUID(settings.SINGLE_USER_ID),
        year=year,
        group_by=group_by,
    )


@router.get("/fees")
async def fee_analysis(
    db: DbSession,
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
):
    """Fee analysis: total fees by type and account."""
    service = AnalyticsService(db)
    return await service.get_fee_analysis(
        user_id=uuid.UUID(settings.SINGLE_USER_ID),
        date_from=date_from,
        date_to=date_to,
    )
