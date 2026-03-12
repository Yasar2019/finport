"""
Net worth calculator.

Definition: Net Worth = sum of all account market values (holdings + cash)
            as of the requested date.

If as_of_date is None, the most recent valuation date per account is used.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import Account, Holding, Valuation


class NetWorthCalculator:
    def __init__(self, db: Session) -> None:
        self._db = db

    def calculate(
        self,
        user_id: uuid.UUID,
        as_of_date: date | None = None,
    ) -> dict:
        accounts = (
            self._db.query(Account).filter_by(user_id=user_id, is_active=True).all()
        )

        total = Decimal("0")
        breakdown: list[dict] = []

        for account in accounts:
            value = self._account_value(account.id, as_of_date)
            total += value
            breakdown.append(
                {
                    "account_id": str(account.id),
                    "account_name": account.account_name,
                    "account_type": account.account_type,
                    "value": float(value),
                    "currency": account.currency or "USD",
                }
            )

        return {
            "as_of_date": str(as_of_date or date.today()),
            "total_net_worth": float(total),
            "currency": "USD",
            "accounts": sorted(breakdown, key=lambda x: x["value"], reverse=True),
        }

    def _account_value(self, account_id: uuid.UUID, as_of_date: date | None) -> Decimal:
        """
        Use the most recent Valuation snapshot if available,
        otherwise sum current holdings market_value.
        """
        query = self._db.query(Valuation).filter_by(account_id=account_id)
        if as_of_date:
            query = query.filter(Valuation.as_of_date <= as_of_date)
        snapshot = query.order_by(Valuation.as_of_date.desc()).first()

        if snapshot:
            return snapshot.total_value or Decimal("0")

        # Fallback: sum holding market values
        holdings = self._db.query(Holding).filter_by(account_id=account_id).all()
        if as_of_date:
            holdings = [h for h in holdings if h.as_of_date <= as_of_date]

        # Use most recent set of holdings per security
        latest: dict[uuid.UUID, Holding] = {}
        for h in holdings:
            if (
                h.security_id not in latest
                or h.as_of_date > latest[h.security_id].as_of_date
            ):
                latest[h.security_id] = h

        return sum(
            (h.market_value or Decimal("0") for h in latest.values()),
            Decimal("0"),
        )
