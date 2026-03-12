"""Security service — SecurityMaster search and lookup."""

import uuid

import structlog
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.security import Security, SecurityAlias

logger = structlog.get_logger(__name__)


class SecurityService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def search(self, query: str) -> list[dict]:
        pattern = f"%{query}%"
        result = await self._db.execute(
            select(Security)
            .where(
                Security.is_active.is_(True),
                or_(
                    Security.symbol.ilike(pattern),
                    Security.name.ilike(pattern),
                    Security.isin.ilike(pattern),
                    Security.cusip.ilike(pattern),
                ),
            )
            .limit(20)
        )
        securities = result.scalars().all()
        return [self._to_dict(s) for s in securities]

    async def get(self, security_id: uuid.UUID) -> dict | None:
        result = await self._db.execute(
            select(Security).where(Security.id == security_id)
        )
        sec = result.scalar_one_or_none()
        if sec is None:
            return None
        aliases_result = await self._db.execute(
            select(SecurityAlias).where(SecurityAlias.security_id == security_id)
        )
        aliases = aliases_result.scalars().all()
        data = self._to_dict(sec)
        data["aliases"] = [
            {"alias_type": a.alias_type, "alias_symbol": a.alias_symbol}
            for a in aliases
        ]
        return data

    @staticmethod
    def _to_dict(s: Security) -> dict:
        return {
            "id": str(s.id),
            "symbol": s.symbol,
            "isin": s.isin,
            "cusip": s.cusip,
            "name": s.name,
            "security_type": s.security_type,
            "asset_class": s.asset_class,
            "sector": s.sector,
            "currency": s.currency,
            "primary_exchange": s.primary_exchange,
        }
