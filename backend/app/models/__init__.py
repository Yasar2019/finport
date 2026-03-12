"""
Models package — imports all ORM models so Alembic autodiscover works.
"""

from app.models.institution import Institution  # noqa: F401
from app.models.account import Account  # noqa: F401
from app.models.import_session import ImportSession  # noqa: F401
from app.models.parser_run import ParserRun  # noqa: F401
from app.models.statement import Statement  # noqa: F401
from app.models.security import Security, SecurityAlias  # noqa: F401
from app.models.transaction import Transaction  # noqa: F401
from app.models.portfolio import (
    Holding,
    Valuation,
    TaxLot,
    CorporateAction,
)  # noqa: F401
from app.models.income import Dividend, Fee, Transfer  # noqa: F401
from app.models.audit import ReconciliationRecord, AuditLog  # noqa: F401
from app.models.fx_rate import FxRate  # noqa: F401
