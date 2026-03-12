"""
Celery application configuration.
Workers handle all CPU-intensive parsing, normalisation, and reconciliation.
"""

from celery import Celery

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "finport",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Prevent tasks from running indefinitely
    task_soft_time_limit=300,  # 5 min soft limit (SoftTimeLimitExceeded raised)
    task_time_limit=360,  # 6 min hard limit (worker killed)
    # Retry configuration
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    # Queue routing
    task_routes={
        "app.workers.tasks.run_ingestion_pipeline": {"queue": "ingestion"},
        "app.workers.tasks.run_reconciliation": {"queue": "reconciliation"},
    },
    # Worker concurrency (override via CELERYD_CONCURRENCY env var)
    worker_prefetch_multiplier=1,  # important for long-running tasks
)
