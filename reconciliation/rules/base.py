"""Abstract base for all reconciliation rules."""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod

from sqlalchemy.orm import Session

from app.models import ImportSession, ReconciliationRecord


class ReconciliationRule(ABC):
    #: Unique rule identifier used in logs and issue records
    name: str

    @abstractmethod
    def evaluate(
        self,
        import_session: ImportSession,
        db: Session,
    ) -> list[ReconciliationRecord]:
        """
        Analyse the import session and its associated records.
        Return a (possibly empty) list of ReconciliationRecord objects.
        Do NOT call db.add() inside — the engine handles persistence.
        """

    @staticmethod
    def _make_issue(
        import_session_id: uuid.UUID,
        record_type: str,
        record_id: uuid.UUID | None,
        issue_type: str,
        severity: str,
        description: str,
        suggested_action: str | None = None,
    ) -> ReconciliationRecord:
        return ReconciliationRecord(
            id=uuid.uuid4(),
            import_session_id=import_session_id,
            record_type=record_type,
            record_id=record_id,
            issue_type=issue_type,
            severity=severity,
            description=description,
            suggested_action=suggested_action,
            status="open",
        )
