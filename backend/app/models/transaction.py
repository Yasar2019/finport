"""
Transaction ORM model — core financial event record.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        Index(
            "idx_transactions_dedup",
            "account_id",
            "transaction_date",
            "amount",
            "transaction_type",
            postgresql_where=__import__("sqlalchemy").text("deleted_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False
    )
    statement_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("statements.id"), nullable=True
    )
    import_session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("import_sessions.id"), nullable=True, index=True
    )
    parser_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("parser_runs.id"), nullable=True
    )

    # Date fields
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False)
    settlement_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    posted_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Classification
    transaction_type: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )
    # Values: buy | sell | dividend_cash | dividend_reinvest | interest | fee_commission |
    #         fee_management | fee_other | transfer_in | transfer_out | deposit | withdrawal |
    #         return_of_capital | corporate_action | split_adjustment | option_exercise |
    #         margin_interest | journal | unknown

    # Description
    description_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    description_normalized: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )

    # Amounts — positive = inflow, negative = outflow
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    fx_rate_to_usd: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 8), nullable=True
    )

    # Securities (nullable for cash-only transactions)
    security_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("securities.id"), nullable=True, index=True
    )
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    price_per_unit: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 6), nullable=True
    )
    lot_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    running_balance: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )

    # Provenance
    raw_source_ref: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    parser_confidence: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 4), nullable=True
    )

    # Reconciliation state
    is_reconciled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reconciliation_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_manually_reviewed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    is_excluded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
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

    # Relationships
    account: Mapped["Account"] = relationship("Account", back_populates="transactions")
    security: Mapped["Security | None"] = relationship("Security")

    def __repr__(self) -> str:
        return f"<Transaction {self.transaction_date} {self.transaction_type} {self.amount}>"
