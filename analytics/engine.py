"""
Analytics engine — entry point for all portfolio calculations.

All calculators are pure-function modules that receive a SQLAlchemy session
and parameters, and return plain Python objects (no ORM models in responses).
The engine also serves as the service layer called by analytics API endpoints.
"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from analytics.calculators.allocation import AllocationCalculator
from analytics.calculators.gains import GainsCalculator
from analytics.calculators.net_worth import NetWorthCalculator


class AnalyticsEngine:
    def __init__(self, db: Session) -> None:
        self._db = db

    def net_worth(self, user_id: uuid.UUID, as_of_date=None) -> dict:
        return NetWorthCalculator(self._db).calculate(user_id, as_of_date)

    def allocation(self, user_id: uuid.UUID, as_of_date=None) -> dict:
        return AllocationCalculator(self._db).calculate(user_id, as_of_date)

    def realized_gains(
        self,
        user_id: uuid.UUID,
        tax_year: int | None = None,
        account_id: uuid.UUID | None = None,
    ) -> dict:
        return GainsCalculator(self._db).realized_gains(user_id, tax_year, account_id)

    def unrealized_gains(
        self,
        user_id: uuid.UUID,
        account_id: uuid.UUID | None = None,
    ) -> dict:
        return GainsCalculator(self._db).unrealized_gains(user_id, account_id)
