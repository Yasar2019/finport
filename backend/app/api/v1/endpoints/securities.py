"""Securities and settings endpoints."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database.session import get_db_session

router = APIRouter()
settings_obj = get_settings()
DbSession = Annotated[AsyncSession, Depends(get_db_session)]


@router.get("/search")
async def search_securities(
    q: Annotated[str, Query(min_length=1, max_length=100)],
    db: DbSession,
):
    """Search the SecurityMaster by symbol, ISIN, CUSIP, or name."""
    from app.services.security_service import SecurityService

    service = SecurityService(db)
    return await service.search(query=q)


@router.get("/{security_id}")
async def get_security(security_id: uuid.UUID, db: DbSession):
    """Get security details including all known aliases."""
    from app.services.security_service import SecurityService

    service = SecurityService(db)
    return await service.get(security_id=security_id)
