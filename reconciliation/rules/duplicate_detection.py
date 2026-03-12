"""
Duplicate transaction detection rule.

Flags transactions that share the same (account_id, transaction_date, amount,
description_raw) tuple within the current import session's account.
Cross-session duplicates (same values in a previously imported statement) are
flagged at 'warning' severity; within-session duplicates are 'error'.
"""

from __future__ import annotations

import uuid
from collections import Counter

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.models import ImportSession, ReconciliationRecord, Transaction
from reconciliation.rules.base import ReconciliationRule


class DuplicateDetectionRule(ReconciliationRule):
    name = "duplicate_detection"

    def evaluate(
        self,
        import_session: ImportSession,
        db: Session,
    ) -> list[ReconciliationRecord]:
        issues: list[ReconciliationRecord] = []

        # 1. Within-session duplicates (exact same row extracted twice)
        rows = (
            db.query(
                Transaction.transaction_date,
                Transaction.amount,
                Transaction.description_raw,
                func.count().label("cnt"),
                func.array_agg(Transaction.id).label("ids"),
            )
            .filter(Transaction.import_session_id == import_session.id)
            .group_by(
                Transaction.transaction_date,
                Transaction.amount,
                Transaction.description_raw,
            )
            .having(func.count() > 1)
            .all()
        )

        for row in rows:
            issues.append(
                self._make_issue(
                    import_session_id=import_session.id,
                    record_type="transaction",
                    record_id=row.ids[0],
                    issue_type="within_session_duplicate",
                    severity="error",
                    description=(
                        f"Transaction on {row.transaction_date} for {row.amount} "
                        f"appears {row.cnt} times in this import."
                    ),
                    suggested_action="Review and remove extra entries.",
                )
            )

        # 2. Cross-session duplicates (same key already exists in a prior import)
        if import_session.account_id:
            existing = (
                db.query(Transaction)
                .filter(
                    and_(
                        Transaction.account_id == import_session.account_id,
                        Transaction.import_session_id != import_session.id,
                    )
                )
                .all()
            )
            existing_keys: set[tuple] = {
                (str(t.transaction_date), str(t.amount), t.description_raw)
                for t in existing
            }

            current_txs = (
                db.query(Transaction)
                .filter(Transaction.import_session_id == import_session.id)
                .all()
            )
            for tx in current_txs:
                key = (str(tx.transaction_date), str(tx.amount), tx.description_raw)
                if key in existing_keys:
                    issues.append(
                        self._make_issue(
                            import_session_id=import_session.id,
                            record_type="transaction",
                            record_id=tx.id,
                            issue_type="cross_session_duplicate",
                            severity="warning",
                            description=(
                                f"Transaction on {tx.transaction_date} for {tx.amount} "
                                "was already imported in a previous session."
                            ),
                            suggested_action="Mark as duplicate or merge with existing record.",
                        )
                    )

        return issues
