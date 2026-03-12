"""
Balance verification rule.

Computes the running sum of all transactions and compares it against the
reported opening and closing balances extracted from the statement.
Flags a discrepancy if the difference exceeds the configured threshold.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import ImportSession, ReconciliationRecord, Statement, Transaction
from reconciliation.rules.base import ReconciliationRule

_TOLERANCE = Decimal("0.02")  # $0.02 — accounts for rounding in statements


class BalanceVerificationRule(ReconciliationRule):
    name = "balance_verification"

    def evaluate(
        self,
        import_session: ImportSession,
        db: Session,
    ) -> list[ReconciliationRecord]:
        issues: list[ReconciliationRecord] = []

        # Get the Statement created during normalisation
        statements = (
            db.query(Statement)
            .filter(Statement.import_session_id == import_session.id)
            .all()
        )

        for stmt in statements:
            if stmt.opening_balance is None or stmt.closing_balance is None:
                continue  # Cannot verify without both boundaries

            # Sum all transactions for this statement
            txs = (
                db.query(Transaction).filter(Transaction.statement_id == stmt.id).all()
            )
            if not txs:
                continue

            total_tx_amount = sum(
                (t.amount for t in txs),
                Decimal("0"),
            )
            expected_closing = stmt.opening_balance + total_tx_amount
            discrepancy = abs(expected_closing - stmt.closing_balance)

            if discrepancy > _TOLERANCE:
                issues.append(
                    self._make_issue(
                        import_session_id=import_session.id,
                        record_type="balance",
                        record_id=stmt.id,
                        issue_type="balance_mismatch",
                        severity="warning",
                        description=(
                            f"Expected closing balance {expected_closing:.2f} "
                            f"(opening {stmt.opening_balance:.2f} + transactions "
                            f"{total_tx_amount:.2f}) but statement reports "
                            f"{stmt.closing_balance:.2f}. "
                            f"Discrepancy: {discrepancy:.2f}."
                        ),
                        suggested_action=(
                            "Check for missing transactions, fees, or interest "
                            "entries not extracted by the parser."
                        ),
                    )
                )

        return issues
