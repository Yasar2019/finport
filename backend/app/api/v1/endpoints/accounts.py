"""Accounts endpoint stubs."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database.session import get_db_session
from app.services.account_service import AccountService

router = APIRouter()
settings = get_settings()
DbSession = Annotated[AsyncSession, Depends(get_db_session)]


@router.get("")
async def list_accounts(db: DbSession):
    """List all accounts for the current user."""
    service = AccountService(db)
    accounts = await service.list_accounts(user_id=uuid.UUID(settings.SINGLE_USER_ID))
    return {"items": accounts}


@router.get("/{account_id}")
async def get_account(account_id: uuid.UUID, db: DbSession):
    """Get account details including latest valuation."""
    service = AccountService(db)
    account = await service.get_account(
        account_id=account_id, user_id=uuid.UUID(settings.SINGLE_USER_ID)
    )
    if not account:
        raise HTTPException(status_code=404, detail="Account not found.")
    return account


@router.post("")
async def create_account(payload: dict, db: DbSession):
    """Manually create an account (when auto-detection is insufficient)."""
    service = AccountService(db)
    account = await service.create_account(
        user_id=uuid.UUID(settings.SINGLE_USER_ID), **payload
    )
    return account


@router.patch("/{account_id}")
async def update_account(account_id: uuid.UUID, payload: dict, db: DbSession):
    """Update account metadata (name, type, institution)."""
    service = AccountService(db)
    account = await service.update_account(
        account_id=account_id,
        user_id=uuid.UUID(settings.SINGLE_USER_ID),
        updates=payload,
    )
    return account
