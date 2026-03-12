"""Holdings service — current position snapshots."""

import uuid
from datetime import date
from decimal import Decimal

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.portfolio import Holding
from app.models.security import Security

logger = structlog.get_logger(__name__)


class HoldingsService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_holdings(
        self,
        user_id: uuid.UUID,
        account_id: uuid.UUID | None = None,
        as_of_date: date | None = None,
    ) -> dict:
        # Find the latest as_of_date per account if not specified
        if as_of_date is None:
            subq = (
                select(func.max(Holding.as_of_date))
                .where(Holding.user_id == user_id)
                .scalar_subquery()
            )
            q = select(Holding).where(
                Holding.user_id == user_id, Holding.as_of_date == subq
            )
        else:
            q = select(Holding).where(
                Holding.user_id == user_id, Holding.as_of_date == as_of_date
            )

        if account_id is not None:
            q = q.where(Holding.account_id == account_id)

        result = await self._db.execute(q)
        holdings = result.scalars().all()
        return {"items": [self._to_dict(h) for h in holdings], "total": len(holdings)}

    async def get_holdings_summary(self, user_id: uuid.UUID) -> dict:
        subq = (
            select(func.max(Holding.as_of_date))
            .where(Holding.user_id == user_id)
            .scalar_subquery()
        )
        result = await self._db.execute(
            select(Holding).where(
                Holding.user_id == user_id, Holding.as_of_date == subq
            )
        )
        holdings = result.scalars().all()

        total_market_value = sum(
            (h.market_value or Decimal(0)) for h in holdings
        )

        return {
            "total_market_value": float(total_market_value),
            "holdings_count": len(holdings),
            "as_of_date": holdings[0].as_of_date.isoformat() if holdings else None,
        }

    @staticmethod
    def _to_dict(h: Holding) -> dict:
        return {
            "id": str(h.id),
            "account_id": str(h.account_id),
            "security_id": str(h.security_id),
            "as_of_date": h.as_of_date.isoformat(),
            "quantity": float(h.quantity),
            "cost_basis": float(h.cost_basis) if h.cost_basis is not None else None,
            "market_value": float(h.market_value) if h.market_value is not None else None,
            "price": float(h.price) if h.price is not None else None,
            "currency": h.currency,
            "unrealized_gain": float(h.unrealized_gain) if h.unrealized_gain is not None else None,
            "unrealized_gain_pct": float(h.unrealized_gain_pct) if h.unrealized_gain_pct is not None else None,
        }
