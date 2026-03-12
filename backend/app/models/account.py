"""
Account ORM model.
Sensitive account_number is stored encrypted (application-layer AES via EncryptedString).
"""

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base
from app.models.types import EncryptedString

if TYPE_CHECKING:
    from app.models.import_session import ImportSession
    from app.models.institution import Institution
    from app.models.portfolio import Holding, TaxLot, Valuation
    from app.models.statement import Statement
    from app.models.transaction import Transaction


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    institution_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("institutions.id"), nullable=False, index=True
    )
    # Encrypted at application layer — stored as bytes in the DB
    account_number_enc: Mapped[str | None] = mapped_column(
        EncryptedString, nullable=True
    )
    account_name: Mapped[str] = mapped_column(String(200), nullable=False)
    account_type: Mapped[str] = mapped_column(String(50), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    opened_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    closed_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
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
    institution: Mapped["Institution"] = relationship(
        "Institution", back_populates="accounts"
    )
    import_sessions: Mapped[list["ImportSession"]] = relationship(
        "ImportSession", back_populates="account"
    )
    statements: Mapped[list["Statement"]] = relationship(
        "Statement", back_populates="account"
    )
    transactions: Mapped[list["Transaction"]] = relationship(
        "Transaction", back_populates="account"
    )
    holdings: Mapped[list["Holding"]] = relationship(
        "Holding", back_populates="account"
    )
    valuations: Mapped[list["Valuation"]] = relationship(
        "Valuation", back_populates="account"
    )
    tax_lots: Mapped[list["TaxLot"]] = relationship("TaxLot", back_populates="account")

    def __repr__(self) -> str:
        return f"<Account {self.account_name} ({self.account_type})>"
