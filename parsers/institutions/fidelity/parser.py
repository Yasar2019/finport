"""
Fidelity brokerage statement parser — PDF and CSV formats.

PDF format:    Monthly brokerage account statement
CSV format:    "Download" export from Fidelity activity page

Detection: Fidelity PDF statements contain "Fidelity Investments" in the header.
           Fidelity CSVs have the column set defined in the registry detector.
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from parsers.base.candidate_models import (
    CandidateBalance,
    CandidateDividend,
    CandidateFee,
    CandidateHolding,
    CandidateTransaction,
    RawSourceRef,
    StatementMetadata,
)
from parsers.generic.pdf_parser import GenericPDFParser, _parse_date, _parse_decimal
from parsers.registry import ParserRegistry

logger = logging.getLogger(__name__)

# Transaction type classification map for Fidelity action descriptions
_FIDELITY_TX_TYPES: dict[str, str] = {
    "you bought": "buy",
    "you sold": "sell",
    "dividend received": "dividend",
    "reinvestment": "dividend_reinvest",
    "interest earned": "interest",
    "service charge": "fee",
    "transfer of assets": "transfer_in",
    "transferred from": "transfer_in",
    "transferred to": "transfer_out",
    "direct debit": "withdrawal",
    "direct deposit": "deposit",
    "return of capital": "return_of_capital",
    "stock split": "corporate_action",
}

# Fidelity CSV header columns for detection
_FIDELITY_CSV_COLS = {
    "run date",
    "action",
    "symbol",
    "description",
    "amount",
}


def _classify_type(description: str) -> str:
    lower = description.lower()
    for keyword, tx_type in _FIDELITY_TX_TYPES.items():
        if keyword in lower:
            return tx_type
    return "other"


@ParserRegistry.register("fidelity", formats=["pdf", "csv"])
class FidelityParser(GenericPDFParser):
    """
    Concrete parser for Fidelity Investments statements.

    For PDF files, inherits camelot table extraction from GenericPDFParser
    and specialises with Fidelity-specific column mappings and type hints.

    For CSV files, uses Fidelity's known column schema:
      Run Date, Action, Symbol, Description, Type, Quantity, Price, Commission, Amount

    When adding support for a new Fidelity statement sub-format (e.g., 401k),
    create a new subclass (e.g., Fidelity401kParser) and register it separately.
    """

    name = "fidelity"
    version = "1.0.0"

    @classmethod
    def can_parse(cls, filename: str, file_format: str, content_sample: bytes) -> float:
        lower_name = filename.lower()
        if "fidelity" in lower_name:
            return 0.9
        if file_format == "pdf":
            try:
                sample_text = content_sample.decode("utf-8", errors="ignore")
                if "fidelity investments" in sample_text.lower():
                    return 0.95
            except Exception:
                pass
        if file_format == "csv":
            try:
                header_line = content_sample.split(b"\n")[0].decode(
                    "utf-8", errors="ignore"
                )
                csv_cols = {
                    c.strip().lower().strip('"') for c in header_line.split(",")
                }
                overlap = _FIDELITY_CSV_COLS & csv_cols
                if len(overlap) >= 4:
                    return 0.95
            except Exception:
                pass
        return 0.0

    # ------------------------------------------------------------------ #
    #  Metadata                                                            #
    # ------------------------------------------------------------------ #

    def extract_metadata(self, path: Path) -> StatementMetadata:
        if path.suffix.lower() == ".csv":
            return StatementMetadata(
                institution_name="Fidelity Investments",
                account_number_raw=None,  # Not in CSV — obtained from PDF or manual entry
                confidence=0.5,
            )
        # PDF path
        text = self.extract_full_text(path)
        account_match = re.search(r"Account\s+(?:Number|#)[\s:]*([X\d\-]{6,20})", text)
        period_match = re.search(
            r"(?:For the Period|Statement Period)[:\s]+(\w+ \d+,?\s+\d{4})\s+(?:to|-)\s+(\w+ \d+,?\s+\d{4})",
            text,
            re.I,
        )
        return StatementMetadata(
            institution_name="Fidelity Investments",
            account_number_raw=(
                account_match.group(1).strip() if account_match else None
            ),
            period_start=(_parse_date(period_match.group(1)) if period_match else None),
            period_end=(_parse_date(period_match.group(2)) if period_match else None),
            confidence=0.85,
        )

    # ------------------------------------------------------------------ #
    #  Transactions                                                        #
    # ------------------------------------------------------------------ #

    def extract_transactions(self, path: Path) -> list[CandidateTransaction]:
        if path.suffix.lower() == ".csv":
            return self._parse_csv_transactions(path)
        return self._parse_pdf_transactions(path)

    def _parse_csv_transactions(self, path: Path) -> list[CandidateTransaction]:
        import csv

        results: list[CandidateTransaction] = []

        # Fidelity CSVs can have a multi-line preamble before the header row
        header_row_idx = None
        rows: list[list[str]] = []
        with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as fh:
            reader = csv.reader(fh)
            for i, row in enumerate(reader):
                lower = [c.strip().lower() for c in row]
                if "run date" in lower and "action" in lower:
                    header_row_idx = i
                    rows.append(row)
                elif header_row_idx is not None:
                    rows.append(row)

        if not rows:
            return []

        headers = [c.strip().lower() for c in rows[0]]

        def col(name: str) -> int | None:
            try:
                return headers.index(name)
            except ValueError:
                return None

        c_date = col("run date")
        c_action = col("action")
        c_symbol = col("symbol")
        c_qty = col("quantity")
        c_price = col("price")
        c_amount = col("amount")

        for row_n, row in enumerate(rows[1:], start=1):
            if not any(c.strip() for c in row):
                continue

            def g(c: int | None) -> str:
                return row[c].strip() if c is not None and c < len(row) else ""

            tx_date = _parse_date(g(c_date))
            amount = _parse_decimal(g(c_amount))

            if tx_date is None or amount is None:
                continue

            action_raw = g(c_action)
            results.append(
                CandidateTransaction(
                    transaction_date=tx_date,
                    description_raw=action_raw,
                    amount=amount,
                    transaction_type_hint=_classify_type(action_raw),
                    symbol_raw=g(c_symbol) or None,
                    quantity=_parse_decimal(g(c_qty)),
                    price_per_unit=_parse_decimal(g(c_price)),
                    raw_source_ref=RawSourceRef(
                        row_index=row_n,
                        text_snippet=", ".join(row)[:100],
                    ),
                    confidence=0.90,
                )
            )
        return results

    def _parse_pdf_transactions(self, path: Path) -> list[CandidateTransaction]:
        """
        Fidelity PDF table layout:
        Date | Description | Symbol | Quantity | Price | Amount
        Uses camelot lattice extraction then maps known column positions.
        """
        tables = self.extract_tables_camelot(path)
        results: list[CandidateTransaction] = []

        for tbl_idx, table in enumerate(tables):
            if len(table) < 2:
                continue

            header = [str(c).strip().lower() for c in table[0]]
            date_col = next((i for i, h in enumerate(header) if "date" in h), None)
            desc_col = next(
                (i for i, h in enumerate(header) if "description" in h), None
            )
            symbol_col = next((i for i, h in enumerate(header) if "symbol" in h), None)
            qty_col = next(
                (i for i, h in enumerate(header) if "qty" in h or "quantity" in h), None
            )
            price_col = next((i for i, h in enumerate(header) if "price" in h), None)
            amount_col = next((i for i, h in enumerate(header) if "amount" in h), None)

            def g(row: list, idx: int | None) -> str:
                return (
                    str(row[idx]).strip() if idx is not None and idx < len(row) else ""
                )

            for row_idx, row in enumerate(table[1:], start=1):
                tx_date = _parse_date(g(row, date_col))
                amount = _parse_decimal(g(row, amount_col))
                if tx_date is None or amount is None:
                    continue
                desc_raw = g(row, desc_col) or "See source"
                results.append(
                    CandidateTransaction(
                        transaction_date=tx_date,
                        description_raw=desc_raw,
                        amount=amount,
                        transaction_type_hint=_classify_type(desc_raw),
                        symbol_raw=g(row, symbol_col) or None,
                        quantity=_parse_decimal(g(row, qty_col)),
                        price_per_unit=_parse_decimal(g(row, price_col)),
                        raw_source_ref=RawSourceRef(
                            table_index=tbl_idx,
                            row_index=row_idx,
                            text_snippet=" | ".join(str(c) for c in row)[:100],
                        ),
                        confidence=0.85,
                    )
                )
        return results

    # ------------------------------------------------------------------ #
    #  Holdings                                                            #
    # ------------------------------------------------------------------ #

    def extract_holdings(self, path: Path) -> list[CandidateHolding]:
        if path.suffix.lower() != ".pdf":
            return []
        tables = self.extract_tables_camelot(path)
        holdings: list[CandidateHolding] = []
        for tbl_idx, table in enumerate(tables):
            if len(table) < 2:
                continue
            header = [str(c).strip().lower() for c in table[0]]
            # Fidelity positions table header keywords
            if not any("shares" in h or "market value" in h for h in header):
                continue
            sym_col = next((i for i, h in enumerate(header) if "symbol" in h), None)
            name_col = next(
                (
                    i
                    for i, h in enumerate(header)
                    if "description" in h or "security" in h
                ),
                None,
            )
            qty_col = next(
                (i for i, h in enumerate(header) if "shares" in h or "qty" in h), None
            )
            val_col = next(
                (i for i, h in enumerate(header) if "market value" in h), None
            )
            price_col = next((i for i, h in enumerate(header) if "price" in h), None)

            def g(row: list, idx: int | None) -> str:
                return (
                    str(row[idx]).strip() if idx is not None and idx < len(row) else ""
                )

            # Use today as a placeholder; extract_metadata period_end is preferable
            stmt_date = date.today()

            for row_idx, row in enumerate(table[1:], start=1):
                symbol_raw = g(row, sym_col)
                qty = _parse_decimal(g(row, qty_col))
                if not symbol_raw or qty is None:
                    continue
                holdings.append(
                    CandidateHolding(
                        symbol_raw=symbol_raw,
                        name_raw=g(row, name_col) or None,
                        quantity=qty,
                        price=_parse_decimal(g(row, price_col)),
                        market_value=_parse_decimal(g(row, val_col)),
                        as_of_date=stmt_date,
                        raw_source_ref=RawSourceRef(
                            table_index=tbl_idx,
                            row_index=row_idx,
                            text_snippet=" | ".join(str(c) for c in row)[:100],
                        ),
                        confidence=0.85,
                    )
                )
        return holdings

    def extract_balances(self, path: Path) -> list[CandidateBalance]:
        return []
