"""
Generic CSV parser — attempts to parse any CSV-format financial statement by
auto-detecting column roles using a scored column-name matching strategy.

Falls back gracefully: rows that cannot be fully parsed are skipped with a
warning rather than causing the whole parse to fail.
"""

from __future__ import annotations

import csv
import logging
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from parsers.base.candidate_models import (
    CandidateBalance,
    CandidateHolding,
    CandidateTransaction,
    ParserResult,
    RawSourceRef,
    StatementMetadata,
)
from parsers.base.parser_interface import BaseParser
from parsers.registry import ParserRegistry

logger = logging.getLogger(__name__)

# Column name aliases for auto-detection
_DATE_ALIASES = {
    "date",
    "trade date",
    "activity date",
    "transaction date",
    "posted date",
    "run date",
}
_DESC_ALIASES = {"description", "activity description", "memo", "payee", "action"}
_AMOUNT_ALIASES = {"amount", "debit/credit", "net amount", "total"}
_DEBIT_ALIASES = {"debit", "withdrawals", "withdrawal"}
_CREDIT_ALIASES = {"credit", "deposits", "deposit"}
_SYMBOL_ALIASES = {"symbol", "ticker", "security", "cusip", "isin"}
_BALANCE_ALIASES = {"balance", "running balance"}
_QUANTITY_ALIASES = {"quantity", "qty", "shares", "units"}
_PRICE_ALIASES = {"price", "price/share", "unit price"}


def _find_col(headers: list[str], aliases: set[str]) -> int | None:
    for i, h in enumerate(headers):
        if h.strip().lower() in aliases:
            return i
    return None


def _parse_date(raw: str) -> date | None:
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y", "%d/%m/%Y", "%m/%d/%y", "%Y%m%d"):
        try:
            return datetime.strptime(raw.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _parse_decimal(raw: str) -> Decimal | None:
    cleaned = raw.strip().replace(",", "").replace("$", "").replace(" ", "")
    if not cleaned or cleaned in ("-", "—", "N/A"):
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


@ParserRegistry.register_generic(formats=["csv"])
class GenericCSVParser(BaseParser):
    name = "generic-csv"
    version = "1.0.0"

    @classmethod
    def can_parse(cls, filename: str, file_format: str, content_sample: bytes) -> float:
        if file_format.lower() == "csv":
            return 0.5  # medium confidence — institution parsers should beat this
        return 0.0

    def extract_metadata(self, path: Path) -> StatementMetadata:
        return StatementMetadata(
            institution_name=None,
            account_number_raw=None,
            confidence=0.3,
        )

    def extract_transactions(self, path: Path) -> list[CandidateTransaction]:
        results: list[CandidateTransaction] = []
        with path.open("r", encoding="utf-8", errors="replace", newline="") as fh:
            reader = csv.reader(fh)
            rows = list(reader)

        # Find header row (first row that contains a recognisable date/description column)
        header_idx = None
        for i, row in enumerate(rows[:15]):
            lower_cells = [c.strip().lower() for c in row]
            if any(a in lower_cells for a in _DATE_ALIASES | _DESC_ALIASES):
                header_idx = i
                break

        if header_idx is None:
            logger.warning(
                "[generic-csv] Could not auto-detect header row in %s", path.name
            )
            return []

        headers = [c.strip().lower() for c in rows[header_idx]]
        date_col = _find_col(headers, _DATE_ALIASES)
        desc_col = _find_col(headers, _DESC_ALIASES)
        amount_col = _find_col(headers, _AMOUNT_ALIASES)
        debit_col = _find_col(headers, _DEBIT_ALIASES)
        credit_col = _find_col(headers, _CREDIT_ALIASES)
        symbol_col = _find_col(headers, _SYMBOL_ALIASES)
        balance_col = _find_col(headers, _BALANCE_ALIASES)
        qty_col = _find_col(headers, _QUANTITY_ALIASES)
        price_col = _find_col(headers, _PRICE_ALIASES)

        def _get(row: list[str], idx: int | None) -> str:
            if idx is None or idx >= len(row):
                return ""
            return row[idx].strip()

        for row_num, row in enumerate(rows[header_idx + 1 :], start=1):
            if not any(c.strip() for c in row):
                continue  # skip blank rows

            date_raw = _get(row, date_col)
            desc_raw = _get(row, desc_col) or "No description"
            tx_date = _parse_date(date_raw) if date_raw else None

            if tx_date is None:
                continue  # cannot create a transaction without a date

            # Amount resolution: prefer explicit amount col, then credit - debit
            amount: Decimal | None = None
            if amount_col is not None:
                amount = _parse_decimal(_get(row, amount_col))
            if amount is None:
                credit = _parse_decimal(_get(row, credit_col))
                debit = _parse_decimal(_get(row, debit_col))
                if credit is not None:
                    amount = credit
                elif debit is not None:
                    amount = -abs(debit)

            if amount is None:
                continue

            ref = RawSourceRef(row_index=row_num, text_snippet=", ".join(row)[:100])
            results.append(
                CandidateTransaction(
                    transaction_date=tx_date,
                    description_raw=desc_raw,
                    amount=amount,
                    symbol_raw=_get(row, symbol_col) or None,
                    running_balance=_parse_decimal(_get(row, balance_col)),
                    quantity=_parse_decimal(_get(row, qty_col)),
                    price_per_unit=_parse_decimal(_get(row, price_col)),
                    raw_source_ref=ref,
                    confidence=0.6,
                )
            )
        return results

    def extract_holdings(self, path: Path) -> list[CandidateHolding]:
        return []

    def extract_balances(self, path: Path) -> list[CandidateBalance]:
        return []
