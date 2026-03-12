"""Reconciliation service — issue management."""

import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import ReconciliationRecord

logger = structlog.get_logger(__name__)


class ReconciliationService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def list_issues(
        self,
        user_id: uuid.UUID,
        severity: str | None = None,
        status: str | None = "open",
        limit: int = 100,
        offset: int = 0,
    ) -> dict:
        q = select(ReconciliationRecord).where(
            ReconciliationRecord.user_id == user_id
        )
        if severity is not None:
            q = q.where(ReconciliationRecord.severity == severity)
        if status is not None:
            q = q.where(ReconciliationRecord.status == status)

        q = (
            q.order_by(
                ReconciliationRecord.severity.desc(),
                ReconciliationRecord.created_at.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
        result = await self._db.execute(q)
        items = result.scalars().all()
        return {"items": [self._to_dict(r) for r in items], "total": len(items)}

    async def get_summary(self, user_id: uuid.UUID) -> dict:
        result = await self._db.execute(
            select(
                ReconciliationRecord.severity,
                func.count().label("count"),
            )
            .where(
                ReconciliationRecord.user_id == user_id,
                ReconciliationRecord.status == "open",
            )
            .group_by(ReconciliationRecord.severity)
        )
        rows = result.all()
        counts = {row.severity: row.count for row in rows}
        return {
            "error": counts.get("error", 0),
            "warning": counts.get("warning", 0),
            "info": counts.get("info", 0),
            "total_open": sum(counts.values()),
        }

    async def resolve_issue(
        self,
        issue_id: uuid.UUID,
        user_id: uuid.UUID,
        resolution_note: str,
    ) -> dict | None:
        await self._db.execute(
            update(ReconciliationRecord)
            .where(
                ReconciliationRecord.id == issue_id,
                ReconciliationRecord.user_id == user_id,
            )
            .values(
                status="resolved",
                resolution_note=resolution_note,
                resolved_at=datetime.now(timezone.utc),
                resolved_by=user_id,
            )
        )
        await self._db.commit()
        return await self._get_one(issue_id=issue_id, user_id=user_id)

    async def dismiss_issue(
        self, issue_id: uuid.UUID, user_id: uuid.UUID
    ) -> dict | None:
        await self._db.execute(
            update(ReconciliationRecord)
            .where(
                ReconciliationRecord.id == issue_id,
                ReconciliationRecord.user_id == user_id,
            )
            .values(status="dismissed", resolved_at=datetime.now(timezone.utc))
        )
        await self._db.commit()
        return await self._get_one(issue_id=issue_id, user_id=user_id)

    async def _get_one(
        self, issue_id: uuid.UUID, user_id: uuid.UUID
    ) -> dict | None:
        result = await self._db.execute(
            select(ReconciliationRecord).where(
                ReconciliationRecord.id == issue_id,
                ReconciliationRecord.user_id == user_id,
            )
        )
        r = result.scalar_one_or_none()
        return self._to_dict(r) if r else None

    @staticmethod
    def _to_dict(r: ReconciliationRecord) -> dict:
        return {
            "id": str(r.id),
            "entity_type": r.entity_type,
            "entity_id": str(r.entity_id),
            "issue_type": r.issue_type,
            "severity": r.severity,
            "description": r.description,
            "suggested_action": r.suggested_action,
            "status": r.status,
            "resolution_note": r.resolution_note,
            "auto_resolved": r.auto_resolved,
            "created_at": r.created_at.isoformat(),
            "resolved_at": r.resolved_at.isoformat() if r.resolved_at else None,
        }
