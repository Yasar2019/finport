"""
Celery task definitions.
Each task corresponds to a stage of the ingestion pipeline.
Tasks use their own synchronous DB sessions (not FastAPI's async sessions).
"""

import uuid
from datetime import datetime, timezone

import structlog
from celery import Task
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.workers.celery_app import celery_app

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
            content = asyncio.get_event_loop().run_until_complete(
                storage.read(session.storage_path)
            )

            # Detect institution
            detector = InstitutionDetector()
            detection = detector.detect(
                filename=session.original_filename,
                content=content,
                file_format=session.file_format,
            )

            # Select parser
            parser_cls = ParserRegistry.get_parser(
                institution_key=detection.institution_key,
                file_format=session.file_format,
            )
            parser = parser_cls()

            # Write file to temp path, parse, clean up
            import tempfile, os

            with tempfile.NamedTemporaryFile(
                suffix=f".{session.file_format}", delete=False
            ) as tmp:
                tmp.write(content)
                tmp_path = tmp.name

            try:
                from pathlib import Path

                result = parser.parse(Path(tmp_path))
            finally:
                os.unlink(tmp_path)  # Always delete temp file

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

            # Normalise candidates
            from app.services.normalisation_service import NormalisationService

            norm_service = NormalisationService(db)
            norm_service.normalise(
                parser_result=result,
                import_session=session,
                parser_run=parser_run,
            )

            # Reconcile
            run_reconciliation.delay(import_session_id=import_session_id)

            # Update session
            session.status = (
                "completed" if result.overall_confidence >= 0.65 else "needs_review"
            )
            if detection.institution_key:
                pass  # resolve institution_id from short_code if needed
            session.statement_period_start = result.metadata.period_start
            session.statement_period_end = result.metadata.period_end
            session.statement_date = result.metadata.statement_date
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
        counts = engine.run(import_session_id=uuid.UUID(import_session_id))
        log.info("reconciliation.completed", issue_counts=counts)
        return counts
