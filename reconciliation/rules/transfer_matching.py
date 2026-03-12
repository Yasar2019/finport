"""
Transfer matching rule.

When a transfer_out appears in one account and a corresponding transfer_in
appears in another account for the same amount (±0.01 tolerance) within
a 5-day window, they should be linked.  Unmatched transfers are flagged.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.models import ImportSession, ReconciliationRecord, Transaction
from reconciliation.rules.base import ReconciliationRule


class TransferMatchingRule(ReconciliationRule):
    name = "transfer_matching"
    _WINDOW_DAYS = 5
    _AMOUNT_TOLERANCE = 0.01

    def evaluate(
        self,
        import_session: ImportSession,
        db: Session,
    ) -> list[ReconciliationRecord]:
        issues: list[ReconciliationRecord] = []

        # Find transfer_in and transfer_out in this import session
        session_transfers = (
            db.query(Transaction)
            .filter(
                Transaction.import_session_id == import_session.id,
                Transaction.transaction_type.in_(["transfer_in", "transfer_out"]),
            )
            .all()
        )

        for tx in session_transfers:
            opposite_type = (
                "transfer_in"
                if tx.transaction_type == "transfer_out"
                else "transfer_out"
            )
            amount_check = abs(tx.amount)
            window_start = tx.transaction_date - timedelta(days=self._WINDOW_DAYS)
            window_end = tx.transaction_date + timedelta(days=self._WINDOW_DAYS)

            # Look for a matching opposite-type transaction in any other account
            match = (
                db.query(Transaction)
                .filter(
                    and_(
                        Transaction.transaction_type == opposite_type,
                        Transaction.transaction_date.between(window_start, window_end),
                        Transaction.account_id != tx.account_id,
                    )
                )
                .all()
            )

            matched = [
                m
                for m in match
                if abs(abs(m.amount) - float(amount_check)) <= self._AMOUNT_TOLERANCE
            ]

            if not matched:
                issues.append(
                    self._make_issue(
                        import_session_id=import_session.id,
                        record_type="transaction",
                        record_id=tx.id,
                        issue_type="unmatched_transfer",
                        severity="warning",
                        description=(
                            f"{tx.transaction_type.replace('_', ' ').title()} of "
                            f"{tx.amount} on {tx.transaction_date} has no matching "
                            f"counterpart in any other account within {self._WINDOW_DAYS} days."
                        ),
                        suggested_action=(
                            "Import statement from the counterpart account or "
                            "mark as external transfer."
                        ),
                    )
                )

        return issues
