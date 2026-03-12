"""
Asset allocation calculator.

Returns a breakdown of portfolio value by:
  - asset_class  (stock, bond, etf, cash, crypto, …)
  - account_type (brokerage, ira, 401k, …)
  - sector       (if available on SecurityMaster)
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import Account, Holding, Security


class AllocationCalculator:
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
        account_map = {a.id: a for a in accounts}

        holdings = (
            self._db.query(Holding).filter(Holding.account_id.in_(account_map)).all()
        )

        if as_of_date:
            holdings = [h for h in holdings if h.as_of_date <= as_of_date]

        # Deduplicate to latest holding per (account, security)
        latest: dict[tuple, Holding] = {}
        for h in holdings:
            key = (h.account_id, h.security_id)
            if key not in latest or h.as_of_date > latest[key].as_of_date:
                latest[key] = h

        by_asset_class: dict[str, Decimal] = defaultdict(Decimal)
        by_account_type: dict[str, Decimal] = defaultdict(Decimal)
        by_sector: dict[str, Decimal] = defaultdict(Decimal)
        total = Decimal("0")

        for h in latest.values():
            value = h.market_value or Decimal("0")
            if value == 0:
                continue

            security: Security | None = self._db.get(Security, h.security_id)
            account: Account = account_map[h.account_id]

            asset_class = (
                security.asset_class if security and security.asset_class else "unknown"
            )
            sector = security.sector if security and security.sector else "unknown"
            acct_type = account.account_type or "other"

            by_asset_class[asset_class] += value
            by_account_type[acct_type] += value
            by_sector[sector] += value
            total += value

        def _pct(d: dict) -> list[dict]:
            return sorted(
                [
                    {
                        "label": k,
                        "value": float(v),
                        "pct": round(float(v / total * 100), 2) if total else 0.0,
                    }
                    for k, v in d.items()
                ],
                key=lambda x: x["value"],
                reverse=True,
            )

        return {
            "total_value": float(total),
            "as_of_date": str(as_of_date or date.today()),
            "by_asset_class": _pct(by_asset_class),
            "by_account_type": _pct(by_account_type),
            "by_sector": _pct(by_sector),
        }
