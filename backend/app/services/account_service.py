"""Account service — CRUD for user accounts."""

import uuid
from typing import Any

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account

logger = structlog.get_logger(__name__)


class AccountService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def list_accounts(self, user_id: uuid.UUID) -> list[dict]:
        result = await self._db.execute(
            select(Account)
            .where(Account.user_id == user_id, Account.deleted_at.is_(None))
            .order_by(Account.account_name)
        )
        accounts = result.scalars().all()
        return [self._to_dict(a) for a in accounts]

    async def get_account(
        self, account_id: uuid.UUID, user_id: uuid.UUID
    ) -> dict | None:
        result = await self._db.execute(
            select(Account).where(
                Account.id == account_id,
                Account.user_id == user_id,
                Account.deleted_at.is_(None),
            )
        )
        account = result.scalar_one_or_none()
        return self._to_dict(account) if account else None

    async def create_account(self, user_id: uuid.UUID, **kwargs: Any) -> dict:
        account = Account(user_id=user_id, **kwargs)
        self._db.add(account)
        await self._db.commit()
        await self._db.refresh(account)
        return self._to_dict(account)

    async def update_account(
        self, account_id: uuid.UUID, user_id: uuid.UUID, updates: dict
    ) -> dict | None:
        await self._db.execute(
            update(Account)
            .where(Account.id == account_id, Account.user_id == user_id)
            .values(**updates)
        )
        await self._db.commit()
        return await self.get_account(account_id=account_id, user_id=user_id)

    @staticmethod
    def _to_dict(account: Account) -> dict:
        return {
            "id": str(account.id),
            "user_id": str(account.user_id),
            "account_name": account.account_name,
            "account_type": account.account_type,
            "institution_id": str(account.institution_id),
            "currency": account.currency,
            "is_active": account.is_active,
            "opened_date": (
                account.opened_date.isoformat() if account.opened_date else None
            ),
            "created_at": (
                account.created_at.isoformat() if account.created_at else None
            ),
        }
