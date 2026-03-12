"""
API v1 router — aggregates all endpoint routers.
"""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    accounts,
    analytics,
    holdings,
    ingestion,
    reconciliation,
    securities,
    settings as settings_router,
    transactions,
)

api_router = APIRouter()

api_router.include_router(
    ingestion.router, prefix="/imports", tags=["Statement Imports"]
)
api_router.include_router(accounts.router, prefix="/accounts", tags=["Accounts"])
api_router.include_router(
    transactions.router, prefix="/transactions", tags=["Transactions"]
)
api_router.include_router(holdings.router, prefix="/holdings", tags=["Holdings"])
api_router.include_router(securities.router, prefix="/securities", tags=["Securities"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["Analytics"])
api_router.include_router(
    reconciliation.router, prefix="/reconciliation", tags=["Reconciliation"]
)
api_router.include_router(settings_router.router, prefix="/settings", tags=["Settings"])
