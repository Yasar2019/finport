"""
ImportSession ORM model.
Represents one uploaded file and the full lifecycle of its processing.
"""

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base

if TYPE_CHECKING:
    from app.models.account import Account
    from app.models.audit import ReconciliationRecord
    from app.models.institution import Institution
    from app.models.parser_run import ParserRun


class ImportSession(Base):
    __tablename__ = "import_sessions"
    __table_args__ = (
        UniqueConstraint("user_id", "file_hash", name="uq_import_sessions_user_hash"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=True
    )
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_format: Mapped[str] = mapped_column(String(20), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)

    # Status lifecycle: pending → queued → processing → completed | needs_review | failed
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="pending", index=True
    )

    detected_institution_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("institutions.id"), nullable=True
    )
    detected_account_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    statement_period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    statement_period_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    statement_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(
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
    account: Mapped["Account | None"] = relationship(
        "Account", back_populates="import_sessions"
    )
    detected_institution: Mapped["Institution | None"] = relationship("Institution")
    parser_runs: Mapped[list["ParserRun"]] = relationship(
        "ParserRun", back_populates="import_session", cascade="all, delete-orphan"
    )
    reconciliation_records: Mapped[list["ReconciliationRecord"]] = relationship(
        "ReconciliationRecord", back_populates="import_session"
    )

    def __repr__(self) -> str:
        return f"<ImportSession {self.original_filename} [{self.status}]>"
