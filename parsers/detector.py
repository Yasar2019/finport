"""
InstitutionDetector — analyses an uploaded file and determines which institution
it most likely came from, returning a confidence-ranked list of candidates.

Detection is multi-signal:
  1. Filename pattern matching (regex against known institution filename patterns)
  2. PDF text header / watermark patterns (first 2 pages extracted via pdfplumber)
  3. CSV column fingerprinting (header row matching against known column sets)

The detector intentionally does NOT do full parsing — it reads only the minimum
needed to identify the institution so the registry can pick the right parser.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
#  Detection signal definitions                                                #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class FilenamePattern:
    institution_key: str
    regex: re.Pattern[str]
    confidence: float = 0.7


@dataclass(frozen=True)
class HeaderPattern:
    institution_key: str
    phrases: list[str]  # ALL phrases must be present (case-insensitive)
    confidence: float = 0.9


@dataclass(frozen=True)
class CsvColumnFingerprint:
    institution_key: str
    required_columns: frozenset[str]  # header values, lower-stripped
    confidence: float = 0.85


@dataclass
class DetectionResult:
    institution_key: str | None
    confidence: float
    method: str  # "filename" | "header" | "csv_columns" | "none"
    candidates: list[tuple[str, float]] = field(default_factory=list)


# --------------------------------------------------------------------------- #
#  Known institution patterns (extend as parsers are added)                   #
# --------------------------------------------------------------------------- #

_FILENAME_PATTERNS: list[FilenamePattern] = [
    FilenamePattern("fidelity", re.compile(r"fidelity|fid_", re.I), 0.75),
    FilenamePattern("schwab", re.compile(r"schwab|SWAB", re.I), 0.75),
    FilenamePattern("vanguard", re.compile(r"vanguard|vg_stmt", re.I), 0.75),
    FilenamePattern("chase", re.compile(r"chase|jpmorgan", re.I), 0.75),
    FilenamePattern("etrade", re.compile(r"e[\-_]?trade", re.I), 0.75),
    FilenamePattern(
        "tdameritrade", re.compile(r"tdameritrade|td_ameritrade", re.I), 0.75
    ),
    FilenamePattern("coinbase", re.compile(r"coinbase|cb_report", re.I), 0.75),
    FilenamePattern("robinhood", re.compile(r"robinhood|rh_stmt", re.I), 0.75),
]

_HEADER_PATTERNS: list[HeaderPattern] = [
    HeaderPattern(
        "fidelity", ["Fidelity Investments", "Fidelity Brokerage Services"], 0.95
    ),
    HeaderPattern("schwab", ["Charles Schwab", "Schwab One"], 0.95),
    HeaderPattern("vanguard", ["The Vanguard Group", "Vanguard Brokerage"], 0.95),
    HeaderPattern("chase", ["JPMorgan Chase", "Chase Bank"], 0.95),
    HeaderPattern("etrade", ["E*TRADE", "Morgan Stanley"], 0.90),
    HeaderPattern("tdameritrade", ["TD Ameritrade", "TD AMERITRADE"], 0.95),
    HeaderPattern("coinbase", ["Coinbase, Inc.", "Coinbase Pro"], 0.95),
    HeaderPattern("robinhood", ["Robinhood Markets", "Robinhood Securities"], 0.95),
]

_CSV_FINGERPRINTS: list[CsvColumnFingerprint] = [
    CsvColumnFingerprint(
        "fidelity",
        frozenset(
            [
                "run date",
                "action",
                "symbol",
                "description",
                "type",
                "quantity",
                "price",
                "amount",
            ]
        ),
        0.90,
    ),
    CsvColumnFingerprint(
        "schwab",
        frozenset(
            [
                "date",
                "action",
                "symbol",
                "description",
                "quantity",
                "price",
                "fees & comm",
                "amount",
            ]
        ),
        0.90,
    ),
    CsvColumnFingerprint(
        "coinbase",
        frozenset(
            [
                "timestamp",
                "transaction type",
                "asset",
                "quantity transacted",
                "spot price currency",
                "subtotal",
                "total",
            ]
        ),
        0.95,
    ),
    CsvColumnFingerprint(
        "robinhood",
        frozenset(
            [
                "activity date",
                "process date",
                "settle date",
                "instrument",
                "description",
                "trans code",
                "quantity",
                "price",
                "amount",
            ]
        ),
        0.90,
    ),
]


# --------------------------------------------------------------------------- #
#  Detector                                                                    #
# --------------------------------------------------------------------------- #


class InstitutionDetector:
    def detect(
        self,
        filename: str,
        file_path: Path,
        file_format: str,
    ) -> DetectionResult:
        """
        Run all detection signals and return the highest-confidence result.
        """
        candidates: list[tuple[str, float, str]] = []

        candidates.extend(self._check_filename(filename))

        if file_format == "pdf":
            candidates.extend(self._check_pdf_headers(file_path))
        elif file_format in ("csv", "tsv"):
            candidates.extend(self._check_csv_columns(file_path))

        if not candidates:
            return DetectionResult(institution_key=None, confidence=0.0, method="none")

        # Sort descending by confidence
        candidates.sort(key=lambda x: x[1], reverse=True)
        best_key, best_conf, best_method = candidates[0]

        return DetectionResult(
            institution_key=best_key,
            confidence=best_conf,
            method=best_method,
            candidates=[(k, c) for k, c, _ in candidates],
        )

    def _check_filename(self, filename: str) -> list[tuple[str, float, str]]:
        results: list[tuple[str, float, str]] = []
        lower = filename.lower()
        for pat in _FILENAME_PATTERNS:
            if pat.regex.search(lower):
                results.append((pat.institution_key, pat.confidence, "filename"))
        return results

    def _check_pdf_headers(self, path: Path) -> list[tuple[str, float, str]]:
        try:
            import pdfplumber  # type: ignore[import-untyped]
        except ImportError:
            logger.warning("pdfplumber not installed; skipping PDF header detection")
            return []

        try:
            with pdfplumber.open(path) as pdf:
                text_sample = ""
                for page in pdf.pages[:3]:
                    page_text = page.extract_text() or ""
                    text_sample += page_text + "\n"
                    if len(text_sample) > 8000:
                        break
        except Exception as exc:
            logger.warning("PDF header read failed for %s: %s", path.name, exc)
            return []

        results: list[tuple[str, float, str]] = []
        for pat in _HEADER_PATTERNS:
            if all(phrase.lower() in text_sample.lower() for phrase in pat.phrases):
                results.append((pat.institution_key, pat.confidence, "header"))
        return results

    def _check_csv_columns(self, path: Path) -> list[tuple[str, float, str]]:
        try:
            with path.open("r", encoding="utf-8", errors="replace") as fh:
                # Some CSVs have preamble rows before the actual header
                for _ in range(10):
                    line = fh.readline()
                    if not line:
                        break
                    header_cells = frozenset(c.strip().lower() for c in line.split(","))
                    for fp in _CSV_FINGERPRINTS:
                        overlap = fp.required_columns & header_cells
                        if len(overlap) / len(fp.required_columns) >= 0.75:
                            score = fp.confidence * (
                                len(overlap) / len(fp.required_columns)
                            )
                            return [
                                (fp.institution_key, round(score, 3), "csv_columns")
                            ]
        except Exception as exc:
            logger.warning("CSV column fingerprint failed for %s: %s", path.name, exc)

        return []
