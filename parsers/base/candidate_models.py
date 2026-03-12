"""
Candidate record models — the output contract of all parsers.
These Pydantic models are the boundary between raw parsing and the normalisation layer.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator


class RawSourceRef(BaseModel):
    """Pointer back to the raw location in the source file for auditability."""

    page: int | None = None
    table_index: int | None = None
    row_index: int | None = None
    cell_ref: str | None = None  # e.g. "B14" for Excel
    text_snippet: str | None = None  # first 100 chars

    model_config = {"frozen": True}


class CandidateTransaction(BaseModel):
    transaction_date: date
    settlement_date: date | None = None
    description_raw: str
    amount: Decimal
    currency: str = Field(default="USD", max_length=3)
    transaction_type_hint: str | None = None
    quantity: Decimal | None = None
    price_per_unit: Decimal | None = None
    symbol_raw: str | None = None
    running_balance: Decimal | None = None
    raw_source_ref: RawSourceRef
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("description_raw")
    @classmethod
    def truncate_description(cls, v: str) -> str:
        return v[:2000] if v else v


class CandidateHolding(BaseModel):
    symbol_raw: str
    name_raw: str | None = None
    quantity: Decimal
    price: Decimal | None = None
    market_value: Decimal | None = None
    cost_basis: Decimal | None = None
    currency: str = Field(default="USD", max_length=3)
    as_of_date: date
    raw_source_ref: RawSourceRef
    confidence: float = Field(ge=0.0, le=1.0)


class CandidateBalance(BaseModel):
    balance_type: str  # opening | closing | cash | total
    amount: Decimal
    currency: str = Field(default="USD", max_length=3)
    as_of_date: date
    raw_source_ref: RawSourceRef
    confidence: float = Field(ge=0.0, le=1.0)


class CandidateDividend(BaseModel):
    symbol_raw: str
    pay_date: date
    ex_date: date | None = None
    total_amount: Decimal
    amount_per_share: Decimal | None = None
    quantity: Decimal | None = None
    dividend_type_hint: str = "cash"
    tax_withheld: Decimal | None = None
    currency: str = Field(default="USD", max_length=3)
    raw_source_ref: RawSourceRef
    confidence: float = Field(ge=0.0, le=1.0)


class CandidateFee(BaseModel):
    fee_date: date
    description_raw: str
    amount: Decimal  # always positive
    currency: str = Field(default="USD", max_length=3)
    fee_type_hint: str | None = None
    raw_source_ref: RawSourceRef
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("amount")
    @classmethod
    def must_be_positive(cls, v: Decimal) -> Decimal:
        if v < 0:
            return abs(v)
        return v


class StatementMetadata(BaseModel):
    institution_name: str | None = None
    account_number_raw: str | None = None  # will be encrypted at normalisation
    account_type_hint: str | None = None
    period_start: date | None = None
    period_end: date | None = None
    statement_date: date | None = None
    currency: str = Field(default="USD", max_length=3)
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)


class ParserResult(BaseModel):
    """The complete output of one parser run over one file."""

    parser_name: str
    parser_version: str
    metadata: StatementMetadata
    transactions: list[CandidateTransaction] = []
    holdings: list[CandidateHolding] = []
    balances: list[CandidateBalance] = []
    dividends: list[CandidateDividend] = []
    fees: list[CandidateFee] = []
    overall_confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    warnings: list[str] = []
    errors: list[str] = []
    raw_text: str | None = None

    def record_count(self) -> int:
        return (
            len(self.transactions)
            + len(self.holdings)
            + len(self.dividends)
            + len(self.fees)
        )
