"""
Application lifecycle events: startup and shutdown hooks.
"""

import structlog

logger = structlog.get_logger(__name__)


def startup_event() -> None:
    """Called once on application startup."""
    logger.info("finport.startup", message="FinPort API starting up")
    # Future: warm up connection pools, seed SecurityMaster, etc.


def shutdown_event() -> None:
    """Called on application shutdown."""
    logger.info("finport.shutdown", message="FinPort API shutting down")
