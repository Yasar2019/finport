"""
Generic PDF parser — attempts to parse any PDF financial statement using
pdfplumber for text + camelot for table extraction.

Extraction strategy:
  1. Extract all text via pdfplumber (works for text-based PDFs)
  2. Attempt camelot table extraction (lattice then stream mode)
  3. If both yield nothing, record an OCR-needed warning

Institution-specific parsers that inherit from this class get pdfplumber
and camelot helpers for free and only need to specialise the column mappings.
"""

from __future__ import annotations

import logging
import re
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

_DATE_PATTERNS = [
    re.compile(r"\b(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})\b"),
    re.compile(r"\b(\d{4}[/\-]\d{2}[/\-]\d{2})\b"),
    re.compile(r"\b([A-Z][a-z]{2,8}\.?\s+\d{1,2},?\s+\d{4})\b"),
]


def _parse_date(raw: str) -> date | None:
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y", "%d/%m/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(raw.strip(), fmt).date()
        except ValueError:
            continue
    for fmt in ("%B %d, %Y", "%B %d %Y", "%b %d, %Y", "%b %d %Y"):
        try:
            return datetime.strptime(raw.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _parse_decimal(raw: str) -> Decimal | None:
    cleaned = raw.strip().replace(",", "").replace("$", "").replace(" ", "")
    if not cleaned or cleaned in ("-", "—", "N/A", "()", ""):
        return None
    # Handle parentheses as negatives: (1,234.56) → -1234.56
    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = "-" + cleaned[1:-1]
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


@ParserRegistry.register_generic(formats=["pdf"])
class GenericPDFParser(BaseParser):
    name = "generic-pdf"
    version = "1.0.0"

    @classmethod
    def can_parse(cls, filename: str, file_format: str, content_sample: bytes) -> float:
        if file_format.lower() == "pdf":
            # Only use as fallback; institution parsers score higher
            return 0.35
        return 0.0

    # ------------------------------------------------------------------ #
    # pdfplumber helpers available to subclasses                          #
    # ------------------------------------------------------------------ #

    @staticmethod
    def extract_full_text(path: Path) -> str:
        """Extract all text from every page via pdfplumber."""
        try:
            import pdfplumber  # type: ignore[import-untyped]
        except ImportError:
            return ""
        text_parts: list[str] = []
        try:
            with pdfplumber.open(path) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(page_text)
        except Exception as exc:
            logger.warning("[generic-pdf] pdfplumber failed on %s: %s", path.name, exc)
        return "\n".join(text_parts)

    @staticmethod
    def extract_tables_camelot(path: Path) -> list[list[list[str]]]:
        """
        Extract all tables from a PDF using camelot (lattice mode first, stream fallback).
        Returns list of tables, each table is list of rows, each row is list of cell strings.
        """
        try:
            import camelot  # type: ignore[import-untyped]
        except ImportError:
            logger.warning(
                "[generic-pdf] camelot not installed; table extraction skipped"
            )
            return []

        tables = []
        for flavor in ("lattice", "stream"):
            try:
                result = camelot.read_pdf(str(path), pages="all", flavor=flavor)
                if result and result.n > 0:
                    tables = [t.df.values.tolist() for t in result]
                    break
            except Exception as exc:
                logger.debug("[generic-pdf] camelot %s flavor failed: %s", flavor, exc)
                continue
        return tables

    # ------------------------------------------------------------------ #
    # BaseParser implementation                                            #
    # ------------------------------------------------------------------ #

    def extract_metadata(self, path: Path) -> StatementMetadata:
        text = self.extract_full_text(path)
        account_match = re.search(
            r"account\s*(?:number|#|no\.?)[\s:]*([X\*\d]{4,20})", text, re.I
        )
        period_match = re.search(
            r"(?:period|statement)\s+(?:from\s+)?(\w+ \d+,? \d{4})\s+to\s+(\w+ \d+,? \d{4})",
            text,
            re.I,
        )
        return StatementMetadata(
            account_number_raw=(account_match.group(1) if account_match else None),
            period_start=(_parse_date(period_match.group(1)) if period_match else None),
            period_end=(_parse_date(period_match.group(2)) if period_match else None),
            confidence=0.3,
        )

    def extract_transactions(self, path: Path) -> list[CandidateTransaction]:
        """
        Best-effort extraction from camelot tables.
        Subclasses should override this with institution-specific column mappings.
        """
        tables = self.extract_tables_camelot(path)
        if not tables:
            return []

        results: list[CandidateTransaction] = []
        for tbl_idx, table in enumerate(tables):
            if len(table) < 2:
                continue
            header = [str(c).strip().lower() for c in table[0]]
            for row_idx, row in enumerate(table[1:], start=1):
                # Simple heuristic: look for a date in the first few cells
                tx_date: date | None = None
                amount: Decimal | None = None
                desc_raw = ""

                for cell_idx, cell in enumerate(row[:6]):
                    cell_str = str(cell).strip()
                    if tx_date is None:
                        tx_date = _parse_date(cell_str)
                    if amount is None and cell_idx > 0:
                        amount = _parse_decimal(cell_str)
                    if len(cell_str) > 5 and not tx_date:
                        desc_raw = desc_raw or cell_str

                if tx_date is None or amount is None:
                    continue

                ref = RawSourceRef(
                    table_index=tbl_idx,
                    row_index=row_idx,
                    text_snippet=" | ".join(str(c) for c in row)[:100],
                )
                results.append(
                    CandidateTransaction(
                        transaction_date=tx_date,
                        description_raw=desc_raw or "See source",
                        amount=amount,
                        raw_source_ref=ref,
                        confidence=0.45,
                    )
                )
        return results

    def extract_holdings(self, path: Path) -> list[CandidateHolding]:
        return []

    def extract_balances(self, path: Path) -> list[CandidateBalance]:
        return []
