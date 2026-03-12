"""
NormalisationService — maps ParserResult candidate records to ORM entities
and persists them to the database inside the Celery ingestion pipeline.

Responsibilities:
  - Resolve or create SecurityMaster entries for each candidate symbol
  - Apply transaction type classification from raw type hints
  - Encrypt sensitive fields (handled transparently by EncryptedString)
  - Build ORM objects and bulk-insert with conflict handling
  - Update ImportSession counters (n_transactions, n_holdings …)
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models import (
    Account,
    Holding,
    ImportSession,
    ParserRun,
    Security,
    SecurityAlias,
    Statement,
    Transaction,
)
from parsers.base.candidate_models import (
    CandidateDividend,
    CandidateFee,
    CandidateHolding,
    CandidateTransaction,
    ParserResult,
)

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
#  Transaction type mapping                                                    #
# --------------------------------------------------------------------------- #

_TYPE_NORMALISATION_MAP: dict[str, str] = {
    "buy": "buy",
    "sell": "sell",
    "dividend": "dividend",
    "dividend_reinvest": "dividend_reinvest",
    "interest": "interest",
    "fee": "fee",
    "transfer_in": "transfer_in",
    "transfer_out": "transfer_out",
    "deposit": "deposit",
    "withdrawal": "withdrawal",
    "return_of_capital": "return_of_capital",
    "corporate_action": "corporate_action",
    "other": "other",
}

_POSITIVE_TO_TYPE: dict[bool, str] = {
    True: "deposit",
    False: "withdrawal",
}


def _normalise_tx_type(hint: str | None, amount: Decimal) -> str:
    if hint and hint in _TYPE_NORMALISATION_MAP:
        return _TYPE_NORMALISATION_MAP[hint]
    # Heuristic fallback
    if amount > 0:
        return "deposit"
    return "withdrawal"


class NormalisationService:
    """
    Stateless service — create one instance per pipeline run.
    All DB writes use the synchronous Session passed from the Celery task.
    """

    def normalise(
        self,
        parser_result: ParserResult,
        import_session: ImportSession,
        parser_run: ParserRun,
        db: Session,
    ) -> None:
        """
        Translate all candidate records in parser_result into ORM entities
        and write them to the database.
        """
        account = self._resolve_account(import_session, parser_result, db)
        statement = self._create_statement(
            import_session, parser_run, parser_result, account, db
        )

        self._persist_transactions(
            parser_result, import_session, statement, account, db
        )
        self._persist_holdings(parser_result, import_session, statement, account, db)
        self._persist_dividends_as_transactions(
            parser_result, import_session, statement, account, db
        )
        self._persist_fees_as_transactions(
            parser_result, import_session, statement, account, db
        )

        db.flush()
        logger.info(
            "[normalise] import_session=%s: %d tx, %d holdings",
            import_session.id,
            len(parser_result.transactions),
            len(parser_result.holdings),
        )

    # ------------------------------------------------------------------ #
    #  Account resolution                                                  #
    # ------------------------------------------------------------------ #

    def _resolve_account(
        self,
        import_session: ImportSession,
        _parser_result: ParserResult,
        db: Session,
    ) -> Account | None:
        """Return the associated Account if already linked, else None."""
        if import_session.account_id:
            return db.get(Account, import_session.account_id)
        return None

    # ------------------------------------------------------------------ #
    #  Statement                                                           #
    # ------------------------------------------------------------------ #

    def _create_statement(
        self,
        import_session: ImportSession,
        _parser_run: ParserRun,
        parser_result: ParserResult,
        account: Account | None,
        db: Session,
    ) -> Statement:
        meta = parser_result.metadata
        closing = next(
            (b.amount for b in parser_result.balances if b.balance_type == "closing"),
            None,
        )
        opening = next(
            (b.amount for b in parser_result.balances if b.balance_type == "opening"),
            None,
        )
        stmt = Statement(
            id=uuid.uuid4(),
            import_session_id=import_session.id,
            account_id=(account.id if account else None),
            institution_id=import_session.detected_institution_id,
            statement_date=meta.period_end or meta.statement_date,
            period_start=meta.period_start,
            period_end=meta.period_end,
            opening_balance=opening,
            closing_balance=closing,
            currency=meta.currency,
        )
        db.add(stmt)
        return stmt

    # ------------------------------------------------------------------ #
    #  Transactions                                                        #
    # ------------------------------------------------------------------ #

    def _persist_transactions(
        self,
        parser_result: ParserResult,
        import_session: ImportSession,
        statement: Statement,
        account: Account | None,
        db: Session,
    ) -> None:
        for candidate in parser_result.transactions:
            security = (
                self._resolve_security(candidate.symbol_raw, db)
                if candidate.symbol_raw
                else None
            )
            tx = Transaction(
                id=uuid.uuid4(),
                account_id=(account.id if account else None),
                statement_id=statement.id,
                import_session_id=import_session.id,
                transaction_date=candidate.transaction_date,
                settlement_date=candidate.settlement_date,
                description_raw=candidate.description_raw,
                description_normalised=candidate.description_raw,
                transaction_type=_normalise_tx_type(
                    candidate.transaction_type_hint, candidate.amount
                ),
                amount=candidate.amount,
                currency=candidate.currency,
                quantity=candidate.quantity,
                price_per_unit=candidate.price_per_unit,
                security_id=(security.id if security else None),
                running_balance=candidate.running_balance,
                raw_source_ref=candidate.raw_source_ref.model_dump(),
                parser_confidence=candidate.confidence,
            )
            db.add(tx)

    # ------------------------------------------------------------------ #
    #  Holdings                                                            #
    # ------------------------------------------------------------------ #

    def _persist_holdings(
        self,
        parser_result: ParserResult,
        import_session: ImportSession,
        statement: Statement,
        account: Account | None,
        db: Session,
    ) -> None:
        for candidate in parser_result.holdings:
            security = self._resolve_security(candidate.symbol_raw, db)
            if security is None:
                continue
            holding = Holding(
                id=uuid.uuid4(),
                account_id=(account.id if account else None),
                security_id=security.id,
                statement_id=statement.id,
                import_session_id=import_session.id,
                as_of_date=candidate.as_of_date,
                quantity=candidate.quantity,
                cost_basis=candidate.cost_basis,
                market_value=candidate.market_value,
                price=candidate.price,
                currency=candidate.currency,
                raw_source_ref=candidate.raw_source_ref.model_dump(),
                parser_confidence=candidate.confidence,
            )
            db.add(holding)

    # ------------------------------------------------------------------ #
    #  Dividends and Fees (promoted to Transaction records)                #
    # ------------------------------------------------------------------ #

    def _persist_dividends_as_transactions(
        self,
        parser_result: ParserResult,
        import_session: ImportSession,
        statement: Statement,
        account: Account | None,
        db: Session,
    ) -> None:
        for candidate in parser_result.dividends:
            security = (
                self._resolve_security(candidate.symbol_raw, db)
                if candidate.symbol_raw
                else None
            )
            tx = Transaction(
                id=uuid.uuid4(),
                account_id=(account.id if account else None),
                statement_id=statement.id,
                import_session_id=import_session.id,
                transaction_date=candidate.pay_date,
                description_raw=f"Dividend: {candidate.symbol_raw}",
                description_normalised=f"Dividend: {candidate.symbol_raw}",
                transaction_type=candidate.dividend_type_hint or "dividend",
                amount=candidate.total_amount,
                currency=candidate.currency,
                quantity=candidate.quantity,
                price_per_unit=candidate.amount_per_share,
                security_id=(security.id if security else None),
                raw_source_ref=candidate.raw_source_ref.model_dump(),
                parser_confidence=candidate.confidence,
            )
            db.add(tx)

    def _persist_fees_as_transactions(
        self,
        parser_result: ParserResult,
        import_session: ImportSession,
        statement: Statement,
        account: Account | None,
        db: Session,
    ) -> None:
        for candidate in parser_result.fees:
            tx = Transaction(
                id=uuid.uuid4(),
                account_id=(account.id if account else None),
                statement_id=statement.id,
                import_session_id=import_session.id,
                transaction_date=candidate.fee_date,
                description_raw=candidate.description_raw,
                description_normalised=candidate.description_raw,
                transaction_type="fee",
                amount=-abs(candidate.amount),  # fees are always negative
                currency=candidate.currency,
                raw_source_ref=candidate.raw_source_ref.model_dump(),
                parser_confidence=candidate.confidence,
            )
            db.add(tx)

    # ------------------------------------------------------------------ #
    #  Security resolution                                                 #
    # ------------------------------------------------------------------ #

    def _resolve_security(self, symbol_raw: str, db: Session) -> Security | None:
        """
        Look up SecurityMaster by ticker or alias.  If unknown, create a
        placeholder 'unresolved' entry so the holding is not silently dropped.
        """
        if not symbol_raw or not symbol_raw.strip():
            return None

        symbol = symbol_raw.strip().upper()

        # 1. Exact ticker match
        security = db.query(Security).filter_by(symbol=symbol).first()
        if security:
            return security

        # 2. Alias match
        alias = (
            db.query(SecurityAlias).filter(SecurityAlias.alias_symbol == symbol).first()
        )
        if alias:
            return db.get(Security, alias.security_id)

        # 3. Create placeholder — will be enriched by a future enrichment task
        security = Security(
            id=uuid.uuid4(),
            symbol=symbol,
            name=symbol,
            security_type="unknown",
        )
        db.add(security)
        logger.info("[normalise] Created placeholder security: %s", symbol)
        return security
