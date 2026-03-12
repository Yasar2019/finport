"""Transaction service — list, get, and update transactions."""

import uuid
from datetime import date

import structlog
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.transaction import Transaction

logger = structlog.get_logger(__name__)


class TransactionService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def list_transactions(
        self,
        user_id: uuid.UUID,
        account_id: uuid.UUID | None = None,
        transaction_type: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        search: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict:
        q = select(Transaction).where(
            Transaction.user_id == user_id,
            Transaction.deleted_at.is_(None),
        )
        if account_id is not None:
            q = q.where(Transaction.account_id == account_id)
        if transaction_type is not None:
            q = q.where(Transaction.transaction_type == transaction_type)
        if date_from is not None:
            q = q.where(Transaction.transaction_date >= date_from)
        if date_to is not None:
            q = q.where(Transaction.transaction_date <= date_to)
        if search:
            pattern = f"%{search}%"
            q = q.where(
                or_(
                    Transaction.description_normalized.ilike(pattern),
                    Transaction.description_raw.ilike(pattern),
                )
            )

        q = q.order_by(Transaction.transaction_date.desc()).limit(limit).offset(offset)
        result = await self._db.execute(q)
        items = result.scalars().all()
        return {"items": [self._to_dict(t) for t in items], "total": len(items)}

    async def get_transaction(
        self, transaction_id: uuid.UUID, user_id: uuid.UUID
    ) -> dict | None:
        result = await self._db.execute(
            select(Transaction).where(
                Transaction.id == transaction_id,
                Transaction.user_id == user_id,
                Transaction.deleted_at.is_(None),
            )
        )
        t = result.scalar_one_or_none()
        return self._to_dict(t) if t else None

    async def update_transaction(
        self, transaction_id: uuid.UUID, user_id: uuid.UUID, updates: dict
    ) -> dict | None:
        updates.pop("id", None)
        updates.pop("user_id", None)
        await self._db.execute(
            update(Transaction)
            .where(
                Transaction.id == transaction_id,
                Transaction.user_id == user_id,
            )
            .values(**updates, is_manually_reviewed=True)
        )
        await self._db.commit()
        return await self.get_transaction(
            transaction_id=transaction_id, user_id=user_id
        )

    @staticmethod
    def _to_dict(t: Transaction) -> dict:
        return {
            "id": str(t.id),
            "account_id": str(t.account_id),
            "transaction_date": t.transaction_date.isoformat(),
            "transaction_type": t.transaction_type,
            "amount": float(t.amount),
            "currency": t.currency,
            "description": t.description_normalized or t.description_raw,
            "security_id": str(t.security_id) if t.security_id else None,
            "quantity": float(t.quantity) if t.quantity is not None else None,
            "price_per_unit": float(t.price_per_unit) if t.price_per_unit is not None else None,
            "is_reconciled": t.is_reconciled,
            "is_manually_reviewed": t.is_manually_reviewed,
        }
