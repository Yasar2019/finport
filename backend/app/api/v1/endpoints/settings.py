"""Settings endpoint."""

from fastapi import APIRouter

router = APIRouter()


@router.get("")
async def get_settings_view():
    """
    Return non-sensitive application settings.
    Secrets (API keys, encryption keys) are never returned.
    """
    from app.config import get_settings

    s = get_settings()
    return {
        "environment": s.ENVIRONMENT,
        "storage_backend": s.STORAGE_BACKEND,
        "max_upload_size_mb": s.MAX_UPLOAD_SIZE_MB,
        "reconciliation_auto_resolve_confidence": s.RECONCILIATION_AUTO_RESOLVE_CONFIDENCE,
    }
