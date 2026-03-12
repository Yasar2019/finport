"""
Holding, Valuation, TaxLot, and CorporateAction ORM models.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base


class Holding(Base):
    """Point-in-time position snapshot as reported on a statement."""

    __tablename__ = "holdings"
    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "security_id",
            "as_of_date",
            "import_session_id",
            name="uq_holdings_account_security_date_session",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False
    )
    security_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("securities.id"), nullable=False, index=True
    )
    statement_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("statements.id"), nullable=True
    )
    import_session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("import_sessions.id"), nullable=True
    )
    parser_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("parser_runs.id"), nullable=True
    )

    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    cost_basis: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    cost_basis_method: Mapped[str | None] = mapped_column(String(20), nullable=True)
    market_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    unrealized_gain: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    unrealized_gain_pct: Mapped[Decimal | None] = mapped_column(
        Numeric(8, 4), nullable=True
    )

    raw_source_ref: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    parser_confidence: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 4), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    account: Mapped["Account"] = relationship("Account", back_populates="holdings")
    security: Mapped["Security"] = relationship("Security", back_populates="holdings")


class Valuation(Base):
    """Account-level net value snapshot over time."""

    __tablename__ = "valuations"
    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "as_of_date",
            "source",
            name="uq_valuations_account_date_source",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False
    )
    import_session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("import_sessions.id"), nullable=True
    )

    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    total_value: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    cash_balance: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    securities_value: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="statement")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    account: Mapped["Account"] = relationship("Account", back_populates="valuations")


class TaxLot(Base):
    """Acquisition-level cost basis for realised gain/loss calculation."""

    __tablename__ = "tax_lots"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False
    )
    security_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("securities.id"), nullable=False
    )
    opening_transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transactions.id"), nullable=True
    )

    acquisition_date: Mapped[date] = mapped_column(Date, nullable=False)
    quantity_original: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    quantity_remaining: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    cost_per_unit: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    total_cost: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    lot_type: Mapped[str | None] = mapped_column(
        String(10), nullable=True
    )  # long | short
    is_open: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, index=True
    )
    wash_sale_disallowed: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    account: Mapped["Account"] = relationship("Account", back_populates="tax_lots")
    security: Mapped["Security"] = relationship("Security", back_populates="tax_lots")


class CorporateAction(Base):
    """Splits, mergers, spin-offs — adjustments that retroactively affect holdings."""

    __tablename__ = "corporate_actions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    security_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("securities.id"), nullable=False
    )
    new_security_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("securities.id"), nullable=True
    )

    action_type: Mapped[str] = mapped_column(String(30), nullable=False)
    # split | reverse_split | merger | spin_off | name_change | delisting | rights_issue | special_dividend

    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    ratio_from: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    ratio_to: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    cash_in_lieu: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    security: Mapped["Security"] = relationship(
        "Security", foreign_keys=[security_id], back_populates="corporate_actions"
    )
