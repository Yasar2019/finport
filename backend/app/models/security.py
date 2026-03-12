"""
Security (SecurityMaster) ORM model.
Canonical reference for all financial instruments.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base


class Security(Base):
    __tablename__ = "securities"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    symbol: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    isin: Mapped[str | None] = mapped_column(String(12), unique=True, nullable=True)
    cusip: Mapped[str | None] = mapped_column(String(9), unique=True, nullable=True)
    figi: Mapped[str | None] = mapped_column(String(12), nullable=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    security_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # stock | bond | etf | mutual_fund | money_market | option | future |
    # crypto | cash_equivalent | reit | other
    primary_exchange: Mapped[str | None] = mapped_column(String(30), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    sector: Mapped[str | None] = mapped_column(String(100), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(100), nullable=True)
    asset_class: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # equity | fixed_income | alternative | cash | real_estate | commodity
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    aliases: Mapped[list["SecurityAlias"]] = relationship(
        "SecurityAlias", back_populates="security"
    )
    holdings: Mapped[list["Holding"]] = relationship(
        "Holding", back_populates="security"
    )
    tax_lots: Mapped[list["TaxLot"]] = relationship("TaxLot", back_populates="security")
    corporate_actions: Mapped[list["CorporateAction"]] = relationship(
        "CorporateAction",
        foreign_keys="CorporateAction.security_id",
        back_populates="security",
    )

    def __repr__(self) -> str:
        return f"<Security {self.symbol or self.isin or self.cusip}>"


class SecurityAlias(Base):
    __tablename__ = "security_aliases"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    security_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("securities.id"), nullable=False
    )
    alias_symbol: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    institution_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("institutions.id"), nullable=True
    )
    alias_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="ticker"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    security: Mapped["Security"] = relationship("Security", back_populates="aliases")
    institution: Mapped["Institution | None"] = relationship(
        "Institution", back_populates="security_aliases"
    )


# Avoid circular import at module level
from sqlalchemy import (
    ForeignKey,
)  # noqa: E402 (already imported above, kept for clarity)
