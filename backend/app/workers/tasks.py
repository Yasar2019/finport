"""
Celery task definitions.
Each task corresponds to a stage of the ingestion pipeline.
Tasks use their own synchronous DB sessions (not FastAPI's async sessions).
"""

import uuid
from datetime import datetime, timezone

import structlog
from celery import Task
from sqlalchemy import select
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.workers.celery_app import celery_app

# Register all parsers (generic + institution-specific) at worker startup
from parsers.registry import ParserRegistry

ParserRegistry.load_all_parsers()

logger = structlog.get_logger(__name__)
settings = get_settings()

# Synchronous engine for Celery workers (asyncpg not available in sync context)
_sync_db_url = settings.DATABASE_URL.replace("+asyncpg", "").replace("+aiosqlite", "")
_sync_engine = create_engine(_sync_db_url, pool_pre_ping=True)
SyncSession = sessionmaker(bind=_sync_engine, expire_on_commit=False)


class BaseTask(Task):
    """Base task class with structured logging and error handling."""

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        logger.error(
            "task.failed",
            task_id=task_id,
            task_name=self.name,
            error=str(exc),
        )


@celery_app.task(
    base=BaseTask, name="app.workers.tasks.run_ingestion_pipeline", bind=True
)
def run_ingestion_pipeline(self, import_session_id: str) -> dict:
    """
    Full ingestion pipeline for one uploaded file.

    Steps:
      1. Update ImportSession status → processing
      2. Load encrypted file from storage
      3. Detect institution + format
      4. Select and run parser → CandidateRecords
      5. Validate candidates with Pydantic
      6. Normalise → ORM entities, persist to DB
      7. Run reconciliation rules
      8. Update ImportSession status → completed | needs_review | failed
    """
    session_id = uuid.UUID(import_session_id)
    log = logger.bind(import_session_id=import_session_id, task_id=self.request.id)
    log.info("ingestion.started")

    with SyncSession() as db:
        from app.models.import_session import ImportSession
        from app.core.storage import get_storage_backend
        from parsers.registry import ParserRegistry
        from parsers.detector import InstitutionDetector

        # Load session
        session = db.get(ImportSession, session_id)
        if not session:
            log.error("ingestion.session_not_found")
            return {"error": "session not found"}

        try:
            # Mark as processing
            session.status = "processing"
            db.commit()

            # Load file from encrypted storage (sync wrapper)
            import asyncio

            storage = get_storage_backend()
            content = asyncio.run(storage.read(session.storage_path))

            # Write file to temp path for detection + parsing
            import tempfile, os

            with tempfile.NamedTemporaryFile(
                suffix=f".{session.file_format}", delete=False
            ) as tmp:
                tmp.write(content)
                tmp_path = tmp.name

            try:
                from pathlib import Path

                # Detect institution
                detector = InstitutionDetector()
                detection = detector.detect(
                    filename=session.original_filename,
                    file_path=Path(tmp_path),
                    file_format=session.file_format,
                )

                # Select parser
                parser_cls = ParserRegistry.get_parser(
                    institution_key=detection.institution_key,
                    file_format=session.file_format,
                )
                if parser_cls is None:
                    raise ValueError(
                        f"No parser available for format={session.file_format} "
                        f"institution={detection.institution_key}"
                    )
                parser = parser_cls()
                result = parser.parse(Path(tmp_path))
            finally:
                os.unlink(tmp_path)

            # Persist parser run
            from app.models.parser_run import ParserRun

            parser_run = ParserRun(
                import_session_id=session_id,
                parser_name=result.parser_name,
                parser_version=result.parser_version,
                started_at=datetime.now(timezone.utc),
                completed_at=datetime.now(timezone.utc),
                status="completed",
                confidence_score=result.overall_confidence,
                records_extracted={
                    "transactions": len(result.transactions),
                    "holdings": len(result.holdings),
                    "dividends": len(result.dividends),
                    "fees": len(result.fees),
                    "balances": len(result.balances),
                },
                warnings=result.warnings,
                errors=result.errors,
            )
            db.add(parser_run)
            db.flush()

            # Resolve or create institution, then ensure the session is linked to an account
            from app.models.account import Account
            from app.models.institution import Institution

            institution_code = (detection.institution_key or "unknown").lower()
            institution = db.execute(
                select(Institution).where(Institution.short_code == institution_code)
            ).scalar_one_or_none()
            if institution is None:
                institution = Institution(
                    short_code=institution_code,
                    name=(
                        detection.institution_key.replace("_", " ").title()
                        if detection.institution_key
                        else "Unknown Institution"
                    ),
                    institution_type="brokerage",
                    country="US",
                    default_currency=result.metadata.currency or "USD",
                    parser_key=detection.institution_key,
                )
                db.add(institution)
                db.flush()

            session.detected_institution_id = institution.id

            if not session.account_id:
                account_name = f"{institution.name} Imported Account"
                account = db.execute(
                    select(Account).where(
                        Account.user_id == session.user_id,
                        Account.institution_id == institution.id,
                        Account.account_name == account_name,
                        Account.deleted_at.is_(None),
                    )
                ).scalar_one_or_none()
                if account is None:
                    account = Account(
                        user_id=session.user_id,
                        institution_id=institution.id,
                        account_name=account_name,
                        account_type="brokerage",
                        currency=result.metadata.currency or "USD",
                    )
                    db.add(account)
                    db.flush()
                session.account_id = account.id

            from app.services.normalisation_service import NormalisationService

            norm_service = NormalisationService()
            norm_service.normalise(
                parser_result=result,
                import_session=session,
                parser_run=parser_run,
                db=db,
            )

            # Reconcile only after successful normalisation
            run_reconciliation.delay(import_session_id=import_session_id)  # type: ignore[attr-defined]

            # Update session
            if result.overall_confidence < 0.65:
                session.status = "needs_review"
            else:
                session.status = "completed"
            session.statement_period_start = result.metadata.period_start
            session.statement_period_end = result.metadata.period_end
            session.statement_date = result.metadata.statement_date
            session.error_message = None
            session.completed_at = datetime.now(timezone.utc)
            db.commit()

            log.info(
                "ingestion.completed",
                confidence=result.overall_confidence,
                status=session.status,
            )
            return {
                "status": session.status,
                "confidence": float(result.overall_confidence),
            }

        except Exception as exc:
            session.status = "failed"
            session.error_message = str(exc)[:1000]
            db.commit()
            log.error("ingestion.failed", error=str(exc), exc_info=True)
            raise self.retry(exc=exc, countdown=60, max_retries=2)


@celery_app.task(base=BaseTask, name="app.workers.tasks.run_reconciliation", bind=True)
def run_reconciliation(self, import_session_id: str) -> dict:
    """
    Run all reconciliation rules against a completed import session.
    Generates ReconciliationRecord rows for each detected issue.
    """
    log = logger.bind(import_session_id=import_session_id, task_id=self.request.id)
    log.info("reconciliation.started")

    with SyncSession() as db:
        from reconciliation.engine import ReconciliationEngine

        engine = ReconciliationEngine(db)
        issues = engine.run(import_session_id=uuid.UUID(import_session_id))
        counts = {"issues_created": len(issues)}
        log.info("reconciliation.completed", issue_counts=counts)
        return counts
