"""
Reconciliation engine — orchestrates all reconciliation rules against
a completed import session.

Usage (inside Celery task):
    engine = ReconciliationEngine(db)
    issues = engine.run(import_session_id)
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models import ImportSession, ReconciliationRecord
from reconciliation.rules.balance_verification import BalanceVerificationRule
from reconciliation.rules.duplicate_detection import DuplicateDetectionRule
from reconciliation.rules.transfer_matching import TransferMatchingRule

logger = logging.getLogger(__name__)


class ReconciliationEngine:
    def __init__(self, db: Session) -> None:
        self._db = db
        self._rules = [
            DuplicateDetectionRule(),
            TransferMatchingRule(),
            BalanceVerificationRule(),
        ]

    def run(self, import_session_id: uuid.UUID) -> list[ReconciliationRecord]:
        """
        Execute all registered rules against the import session.
        Returns the list of ReconciliationRecord ORM objects added to the session.
        """
        import_session: ImportSession | None = self._db.get(
            ImportSession, import_session_id
        )
        if import_session is None:
            raise ValueError(f"ImportSession {import_session_id} not found")

        all_issues: list[ReconciliationRecord] = []

        for rule in self._rules:
            try:
                issues = rule.evaluate(import_session, self._db)
                for issue in issues:
                    self._db.add(issue)
                all_issues.extend(issues)
                logger.info(
                    "[reconcile] rule=%s → %d issues for session %s",
                    rule.name,
                    len(issues),
                    import_session_id,
                )
            except Exception as exc:
                logger.error(
                    "[reconcile] rule=%s raised: %s (session=%s)",
                    rule.name,
                    exc,
                    import_session_id,
                    exc_info=True,
                )

        self._db.flush()
        return all_issues

    def resolve_issue(
        self,
        issue_id: uuid.UUID,
        resolution_note: str,
        auto_resolved: bool = False,
    ) -> ReconciliationRecord:
        from datetime import UTC, datetime

        record: ReconciliationRecord | None = self._db.get(
            ReconciliationRecord, issue_id
        )
        if record is None:
            raise ValueError(f"ReconciliationRecord {issue_id} not found")
        record.status = "resolved"
        record.resolution_note = resolution_note
        record.auto_resolved = auto_resolved
        record.resolved_at = datetime.now(UTC)
        self._db.flush()
        return record
