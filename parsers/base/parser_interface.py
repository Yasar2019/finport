"""
Abstract base class for all financial statement parsers.
Every institution parser must implement this interface.
"""

from __future__ import annotations

import hashlib
import logging
from abc import ABC, abstractmethod
from pathlib import Path

from parsers.base.candidate_models import (
    CandidateBalance,
    CandidateDividend,
    CandidateFee,
    CandidateHolding,
    CandidateTransaction,
    ParserResult,
    StatementMetadata,
)

logger = logging.getLogger(__name__)


class BaseParser(ABC):
    """
    All parsers must subclass BaseParser and implement every abstract method.

    Lifecycle:
        1. parsers.detector.InstitutionDetector calls can_parse() to candidate selection
        2. IngestPipelineTask calls parse() — the public entry point
        3. parse() calls the individual extraction methods in order
        4. parse() collects results into a ParserResult and computes overall_confidence
    """

    #: Unique kebab-case identifier — used as registry key and in DB parser_run records
    name: str
    #: Semantic version string e.g. "1.0.0"
    version: str = "1.0.0"

    # ------------------------------------------------------------------ #
    #  Selection                                                           #
    # ------------------------------------------------------------------ #

    @classmethod
    @abstractmethod
    def can_parse(cls, filename: str, file_format: str, content_sample: bytes) -> float:
        """
        Return a confidence score 0.0–1.0 indicating how likely this parser can
        handle the given file.  The registry picks the highest-scoring candidate.

        Args:
            filename: Original upload filename (lowercased by caller).
            file_format: "pdf" | "csv" | "xlsx"
            content_sample: First 4096 bytes of the (decrypted) file.

        Returns:
            0.0  — definitely cannot parse
            0.5  — uncertain; generic parser may be attempted
            1.0  — definite match (e.g. institution watermark found)
        """

    # ------------------------------------------------------------------ #
    #  Extraction — implement each one; return [] / None if not applicable #
    # ------------------------------------------------------------------ #

    @abstractmethod
    def extract_metadata(self, path: Path) -> StatementMetadata:
        """Extract account number (raw), statement period, institution name."""

    @abstractmethod
    def extract_transactions(self, path: Path) -> list[CandidateTransaction]:
        """Extract all transactions from the statement."""

    @abstractmethod
    def extract_holdings(self, path: Path) -> list[CandidateHolding]:
        """Extract point-in-time portfolio positions."""

    @abstractmethod
    def extract_balances(self, path: Path) -> list[CandidateBalance]:
        """Extract opening/closing/cash balances."""

    def extract_dividends(self, path: Path) -> list[CandidateDividend]:
        """Override if dividends are in a separate section from transactions."""
        return []

    def extract_fees(self, path: Path) -> list[CandidateFee]:
        """Override if fees are in a separate section from transactions."""
        return []

    # ------------------------------------------------------------------ #
    #  Orchestration — do not override unless you have a compelling reason #
    # ------------------------------------------------------------------ #

    def parse(self, path: Path) -> ParserResult:
        """
        Orchestrate extraction and build a ParserResult.
        Exceptions from individual extractors are caught, logged as errors,
        and the parse continues so partial results are always returned.
        """
        warnings: list[str] = []
        errors: list[str] = []

        metadata = StatementMetadata()
        transactions: list[CandidateTransaction] = []
        holdings: list[CandidateHolding] = []
        balances: list[CandidateBalance] = []
        dividends: list[CandidateDividend] = []
        fees: list[CandidateFee] = []

        steps: dict[str, object] = {
            "metadata": (self.extract_metadata, None),
            "transactions": (self.extract_transactions, []),
            "holdings": (self.extract_holdings, []),
            "balances": (self.extract_balances, []),
            "dividends": (self.extract_dividends, []),
            "fees": (self.extract_fees, []),
        }

        for step_name, (fn, default) in steps.items():
            try:
                result = fn(path)  # type: ignore[operator]
                if step_name == "metadata":
                    metadata = result
                elif step_name == "transactions":
                    transactions = result
                elif step_name == "holdings":
                    holdings = result
                elif step_name == "balances":
                    balances = result
                elif step_name == "dividends":
                    dividends = result
                elif step_name == "fees":
                    fees = result
            except Exception as exc:
                msg = f"{step_name} extraction failed: {exc}"
                logger.warning("[%s] %s", self.name, msg)
                errors.append(msg)

        overall_confidence = self._compute_confidence(
            metadata, transactions, holdings, balances
        )

        return ParserResult(
            parser_name=self.name,
            parser_version=self.version,
            metadata=metadata,
            transactions=transactions,
            holdings=holdings,
            balances=balances,
            dividends=dividends,
            fees=fees,
            overall_confidence=overall_confidence,
            warnings=warnings,
            errors=errors,
        )

    # ------------------------------------------------------------------ #
    #  Helpers available to all subclasses                                 #
    # ------------------------------------------------------------------ #

    @staticmethod
    def file_sha256(path: Path) -> str:
        h = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    @staticmethod
    def _compute_confidence(
        metadata: StatementMetadata,
        transactions: list[CandidateTransaction],
        holdings: list[CandidateHolding],
        balances: list[CandidateBalance],
    ) -> float:
        """
        Heuristic overall confidence based on what was extracted.
        Parsers may override this if they have better signals.
        """
        score = 0.0
        if metadata.account_number_raw:
            score += 0.2
        if metadata.period_start and metadata.period_end:
            score += 0.2
        if transactions:
            tx_avg = sum(t.confidence for t in transactions) / len(transactions)
            score += 0.4 * tx_avg
        if holdings:
            h_avg = sum(h.confidence for h in holdings) / len(holdings)
            score += 0.1 * h_avg
        if balances:
            score += 0.1
        return min(round(score, 4), 1.0)
