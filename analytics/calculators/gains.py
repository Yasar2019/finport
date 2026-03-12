"""
Gains calculator.

Realized gains:  match sell transactions against tax lots (FIFO default).
Unrealized gains: market_value − cost_basis per current holding.

Tax lot matching is a placeholder in Phase 1 — full FIFO/LIFO/specific-lot
matching will be implemented in Phase 3 when the TaxLot model is populated
during normalisation.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.models import Account, Holding, Transaction


class GainsCalculator:
    def __init__(self, db: Session) -> None:
        self._db = db

    def realized_gains(
        self,
        user_id: uuid.UUID,
        tax_year: int | None = None,
        account_id: uuid.UUID | None = None,
    ) -> dict:
        """
        Sum realized gains from sell transactions.
        Phase 1: uses amount directly (proceeds − cost not yet computed).
        Phase 3: will compute gain per tax lot.
        """
        account_ids = self._user_account_ids(user_id)
        if account_id:
            account_ids = [a for a in account_ids if a == account_id]

        query = self._db.query(Transaction).filter(
            and_(
                Transaction.account_id.in_(account_ids),
                Transaction.transaction_type == "sell",
            )
        )

        if tax_year:
            query = query.filter(
                and_(
                    Transaction.transaction_date >= date(tax_year, 1, 1),
                    Transaction.transaction_date <= date(tax_year, 12, 31),
                )
            )

        sells = query.all()

        total_proceeds = sum((abs(t.amount) for t in sells), Decimal("0"))
        # Phase 1: gain = proceeds (cost basis tracking in Phase 3)
        return {
            "tax_year": tax_year,
            "total_proceeds": float(total_proceeds),
            "total_realized_gain": None,  # Populated in Phase 3
            "short_term_gain": None,
            "long_term_gain": None,
            "transactions_count": len(sells),
            "note": "Cost basis tracking requires Phase 3 tax lot implementation.",
        }

    def unrealized_gains(
        self,
        user_id: uuid.UUID,
        account_id: uuid.UUID | None = None,
    ) -> dict:
        account_ids = self._user_account_ids(user_id)
        if account_id:
            account_ids = [a for a in account_ids if a == account_id]

        holdings = (
            self._db.query(Holding).filter(Holding.account_id.in_(account_ids)).all()
        )

        total_market_value = Decimal("0")
        total_cost_basis = Decimal("0")
        rows: list[dict] = []

        for h in holdings:
            mv = h.market_value or Decimal("0")
            cb = h.cost_basis or Decimal("0")
            gain = mv - cb if cb else None
            total_market_value += mv
            total_cost_basis += cb
            rows.append(
                {
                    "security_id": str(h.security_id),
                    "holding_id": str(h.id),
                    "market_value": float(mv),
                    "cost_basis": float(cb) if cb else None,
                    "unrealized_gain": float(gain) if gain is not None else None,
                    "unrealized_pct": (
                        round(float(gain / cb * 100), 2)
                        if gain is not None and cb
                        else None
                    ),
                }
            )

        total_unrealized = total_market_value - total_cost_basis
        return {
            "total_market_value": float(total_market_value),
            "total_cost_basis": float(total_cost_basis),
            "total_unrealized_gain": float(total_unrealized),
            "positions": sorted(
                rows,
                key=lambda x: x["unrealized_gain"] or 0,
                reverse=True,
            ),
        }

    def _user_account_ids(self, user_id: uuid.UUID) -> list[uuid.UUID]:
        accounts = (
            self._db.query(Account).filter_by(user_id=user_id, is_active=True).all()
        )
        return [a.id for a in accounts]
