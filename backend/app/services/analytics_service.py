"""Analytics service — net worth, allocation, performance, dividends, fees."""

import uuid
from datetime import date
from decimal import Decimal

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.portfolio import Holding, Valuation
from app.models.transaction import Transaction

logger = structlog.get_logger(__name__)


class AnalyticsService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_net_worth_history(
        self,
        user_id: uuid.UUID,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[dict]:
        q = select(
            Valuation.as_of_date,
            func.sum(Valuation.total_value).label("total"),
        ).where(Valuation.user_id == user_id)

        if date_from:
            q = q.where(Valuation.as_of_date >= date_from)
        if date_to:
            q = q.where(Valuation.as_of_date <= date_to)

        q = q.group_by(Valuation.as_of_date).order_by(Valuation.as_of_date)
        result = await self._db.execute(q)
        rows = result.all()
        return [
            {"date": row.as_of_date.isoformat(), "total_value": float(row.total)}
            for row in rows
        ]

    async def get_allocation(self, user_id: uuid.UUID) -> dict:
        # Latest snapshot
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

        total = sum((h.market_value or Decimal(0)) for h in holdings) or Decimal(1)

        # Group by account
        by_account: dict[str, Decimal] = {}
        for h in holdings:
            key = str(h.account_id)
            by_account[key] = by_account.get(key, Decimal(0)) + (
                h.market_value or Decimal(0)
            )

        return {
            "total_market_value": float(total),
            "by_account": [
                {"account_id": k, "value": float(v), "weight": float(v / total)}
                for k, v in by_account.items()
            ],
            "by_asset_class": [],  # Populated once security data is enriched
            "by_sector": [],
        }

    async def get_performance(
        self,
        user_id: uuid.UUID,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> dict:
        # Unrealized gains from latest holdings snapshot
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

        total_unrealized = sum(
            (h.unrealized_gain or Decimal(0)) for h in holdings
        )

        return {
            "unrealized_gain_loss": float(total_unrealized),
            "realized_gain_loss": None,  # Phase 3: requires tax-lot matching
            "holdings": [
                {
                    "security_id": str(h.security_id),
                    "quantity": float(h.quantity),
                    "cost_basis": float(h.cost_basis) if h.cost_basis else None,
                    "market_value": float(h.market_value) if h.market_value else None,
                    "unrealized_gain": float(h.unrealized_gain) if h.unrealized_gain else None,
                    "unrealized_gain_pct": float(h.unrealized_gain_pct) if h.unrealized_gain_pct else None,
                }
                for h in holdings
            ],
        }

    async def get_dividend_income(
        self,
        user_id: uuid.UUID,
        year: int | None = None,
        group_by: str = "month",
    ) -> list[dict]:
        q = select(Transaction).where(
            Transaction.user_id == user_id,
            Transaction.transaction_type.in_(
                ["dividend_cash", "dividend_reinvest"]
            ),
            Transaction.deleted_at.is_(None),
        )
        if year is not None:
            q = q.where(
                func.extract("year", Transaction.transaction_date) == year
            )

        result = await self._db.execute(q)
        transactions = result.scalars().all()

        # Simple grouping
        groups: dict[str, Decimal] = {}
        for t in transactions:
            if group_by == "security":
                key = str(t.security_id) if t.security_id else "unknown"
            elif group_by == "year":
                key = str(t.transaction_date.year)
            elif group_by == "quarter":
                q_num = (t.transaction_date.month - 1) // 3 + 1
                key = f"{t.transaction_date.year}-Q{q_num}"
            else:
                key = t.transaction_date.strftime("%Y-%m")
            groups[key] = groups.get(key, Decimal(0)) + t.amount

        return [
            {"period": k, "amount": float(v)} for k, v in sorted(groups.items())
        ]

    async def get_fee_analysis(
        self,
        user_id: uuid.UUID,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> dict:
        fee_types = [
            "fee_commission",
            "fee_management",
            "fee_other",
        ]
        q = select(Transaction).where(
            Transaction.user_id == user_id,
            Transaction.transaction_type.in_(fee_types),
            Transaction.deleted_at.is_(None),
        )
        if date_from:
            q = q.where(Transaction.transaction_date >= date_from)
        if date_to:
            q = q.where(Transaction.transaction_date <= date_to)

        result = await self._db.execute(q)
        transactions = result.scalars().all()

        by_type: dict[str, Decimal] = {}
        for t in transactions:
            by_type[t.transaction_type] = (
                by_type.get(t.transaction_type, Decimal(0)) + abs(t.amount)
            )

        total = sum(by_type.values(), Decimal(0))
        return {
            "total_fees": float(total),
            "by_type": [
                {"type": k, "amount": float(v)} for k, v in by_type.items()
            ],
        }
