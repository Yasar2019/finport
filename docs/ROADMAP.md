# FinPort — Development Roadmap

---

## Phasing Philosophy

Each phase delivers a **vertical slice** — functional end-to-end capability — rather than
building one horizontal layer at a time. Users have a working system at the end of every phase.

Phases are sized for a solo developer or small team. Each phase is estimated in weeks of
focused work, not calendar time.

---

## Phase 1 — Foundation: Ingestion & Basic Dashboard

**Goal:** Upload statements, see them in the UI, view raw parsed data.

### Backend Deliverables

- [ ] FastAPI app skeleton with `/health` endpoint
- [ ] PostgreSQL + Alembic migrations for core tables (institutions, accounts, import_sessions, parser_runs, audit_logs)
- [ ] File upload endpoint: MIME validation, SHA-256 deduplication, encrypted storage, ImportSession creation
- [ ] Celery + Redis worker infrastructure with Flower monitoring
- [ ] Import pipeline skeleton: queued task that updates ImportSession status
- [ ] Basic GenericCSVParser (reads any CSV with date/description/amount columns)
- [ ] REST endpoints: list import sessions, get import session status
- [ ] Single-user bearer token authentication
- [ ] Audit logging middleware

### Frontend Deliverables

- [ ] Vite + React + TypeScript + Tailwind CSS project setup
- [ ] Sidebar navigation layout
- [ ] Statement Upload page (drag-and-drop, progress indicator, status polling)
- [ ] Import History page (list all sessions with status badges)
- [ ] Import Detail page (parser confidence, warnings, raw extracted data preview)
- [ ] Basic Accounts page (list accounts with institution logos)

### DevOps Deliverables

- [ ] Docker Compose: api, worker, redis, db, frontend, flower
- [ ] `.env.example` with all required variables
- [ ] `Makefile` with `make dev`, `make test`, `make migrate`, `make build`
- [ ] `pytest` configuration, first API integration test

### Definition of Done

A user can upload a CSV bank statement, see it being processed, and view the raw extracted rows.

---

## Phase 2 — Parser Framework & Normalisation Pipeline

**Goal:** Parse real-world statements from major institutions; data stored in normalised DB.

### Backend Deliverables

- [ ] Full parser framework: `BaseParser`, `ParserRegistry`, `InstitutionDetector`
- [ ] `CandidateRecord` Pydantic models and validation layer
- [ ] Institution parsers (MVP set):
  - [ ] `FidelityCSVParser` (brokerage activity CSV)
  - [ ] `SchwabCSVParser`
  - [ ] `VanguardPDFParser` or CSV
  - [ ] `ChaseBankCSVParser`
  - [ ] `CoinbaseCSVParser`
- [ ] `GenericPDFParser` using pdfplumber
- [ ] `GenericExcelParser` using pandas/openpyxl
- [ ] Normalisation pipeline: CandidateRecords → ORM entities (transactions, holdings, balances, dividends, fees)
- [ ] SecurityMaster: symbol resolution + `security_aliases`
- [ ] Full DB schema: all tables from DATABASE_SCHEMA.md
- [ ] Parser versioning in `parser_runs`
- [ ] Re-process endpoint: re-run parser on existing import session
- [ ] Manual corrections API: update individual transaction fields

### Frontend Deliverables

- [ ] Holdings page: table + donut chart by asset class
- [ ] Transactions page: filterable table (date range, account, type, search)
- [ ] Parsed data review: diff view showing raw vs normalised values
- [ ] Manual correction UI: inline editing with audit trail
- [ ] Account detail page with balance history chart

### Definition of Done

Upload a real Fidelity or Schwab CSV statement; transactions appear correctly in the
transactions table and holdings show in the portfolio view.

---

## Phase 3 — Reconciliation Engine

**Goal:** Automatically detect and surface data quality issues.

### Backend Deliverables

- [ ] `ReconciliationEngine` with pluggable rule sets
- [ ] Rules implemented:
  - [ ] Duplicate transaction detection (hash + fuzzy date-amount matching)
  - [ ] Internal transfer pair matching (debit in account A ↔ credit in account B)
  - [ ] Statement balance verification (sum of transactions = closing - opening balance)
  - [ ] Ticker symbol not found in SecurityMaster
  - [ ] Negative quantity detection
  - [ ] DRIP mis-classification detection
  - [ ] Fee vs transaction amount mismatch
  - [ ] Multi-currency inconsistency
- [ ] `ReconciliationRecord` persistence
- [ ] Auto-resolve for high-confidence matches
- [ ] Reconciliation summary endpoint
- [ ] Exception queue endpoint (open issues, severity sorted)

### Frontend Deliverables

- [ ] Reconciliation Center page
  - Issue list with severity badges (error / warning / info)
  - Suggested match preview
  - Accept / dismiss / manually resolve actions
  - Bulk resolve tool
- [ ] Transfers page: matched and unmatched transfer pairs
- [ ] Dashboard: reconciliation health score widget

### Definition of Done

Upload statements from two linked accounts; the system detects the internal transfer
and marks both sides as reconciled, with no false positives on unique transactions.

---

## Phase 4 — Portfolio Analytics Engine

**Goal:** Compute and display meaningful portfolio insights.

### Backend Deliverables

- [ ] `AnalyticsEngine` service
- [ ] Computations:
  - [ ] Consolidated net worth over time (time-series from valuations)
  - [ ] Portfolio allocation by asset class, sector, account
  - [ ] Holdings at latest date with market-price enrichment hook
  - [ ] Realised gain/loss (FIFO by default, configurable)
  - [ ] Unrealised gain/loss from cost basis
  - [ ] Dividend income history (monthly/annual aggregation)
  - [ ] Fee analysis by type and account
  - [ ] Contribution and withdrawal history
  - [ ] Portfolio drift relative to target allocation (user-defined)
  - [ ] Currency exposure breakdown
- [ ] Tax-lot tracking for sell transactions
- [ ] Corporate actions application (split adjustments to historical holdings)
- [ ] `/analytics` endpoints: net_worth, allocation, performance, dividends, fees

### Frontend Deliverables

- [ ] Analytics dashboard with:
  - Net worth time-series chart
  - Asset allocation pie/donut chart
  - Sector breakdown bar chart
  - Dividend income calendar / bar chart
  - Fee analysis chart
  - Realised gains table
  - Portfolio drift gauge
- [ ] Exportable reports (CSV download for each analytics view)
- [ ] Date range picker for all analytics views

### Definition of Done

User can see their consolidated net worth trend, exact portfolio allocation,
and total dividend income for any calendar year.

---

## Phase 5 — Advanced Insights & SaaS Readiness

**Goal:** Polish, performance, audit, and multi-tenancy preparation.

### Backend Deliverables

- [ ] Multi-user authentication (JWT with refresh tokens)
- [ ] Row-level security preparation (add RLS policies to PostgreSQL)
- [ ] `tenant_id` migration if needed (user_id already present)
- [ ] Rate limiting on API endpoints
- [ ] S3-compatible storage backend implementation
- [ ] Price feed integration hook (alpha vantage / yfinance for current prices)
- [ ] FX rate feed integration
- [ ] OCR fallback (pytesseract) for scanned PDFs
- [ ] Additional institution parsers (community-contributed)
- [ ] OpenTelemetry tracing
- [ ] Data export: full portfolio export to CSV/JSON
- [ ] Scheduled re-reconciliation job

### Frontend Deliverables

- [ ] User settings page (profile, preferences, target allocation editor)
- [ ] Dark mode
- [ ] Mobile-responsive layouts
- [ ] Notification centre (new import completed, reconciliation issues found)
- [ ] Keyboard shortcuts and accessibility audit
- [ ] Password-protected local setup (settings page)

### Infrastructure Deliverables

- [ ] Production Docker Compose with Nginx reverse proxy + TLS
- [ ] Health check endpoints for all services
- [ ] Backup scripts for DB and encrypted file store
- [ ] GitHub Actions CI: lint + test on every PR
- [ ] Deployment guide for VPS (DigitalOcean / Hetzner)

### Definition of Done

Two separate user accounts each upload statements; they see only their own data.
The system is deployable to a VPS with one command.

---

## Dependency Graph

```
Phase 1 (foundation)
    └── Phase 2 (parsers + normalisation)
            └── Phase 3 (reconciliation)       ← depends on normalised data
            └── Phase 4 (analytics)            ← depends on normalised data
                    └── Phase 5 (SaaS)
```

Phases 3 and 4 can proceed in parallel after Phase 2.

---

## Testing Strategy by Phase

| Phase | Test Focus |
|---|---|
| 1 | API integration tests (upload, status polling), worker task execution |
| 2 | Parser unit tests with real fixture statements, normalisation unit tests, SecurityMaster resolution |
| 3 | Reconciliation rule unit tests, de-duplication edge cases, transfer matching |
| 4 | Analytics computation unit tests, gain/loss calculation validation, tax-lot FIFO ordering |
| 5 | Multi-user isolation tests, load tests, security penetration checklist |

---

## Fixture Statement Library

`tests/fixtures/statements/` should accumulate real (anonymised) statement samples:

```
tests/fixtures/statements/
├── fidelity/
│   ├── brokerage_activity_2024.csv
│   └── account_statement_2024.pdf
├── schwab/
├── vanguard/
├── chase_bank/
├── coinbase/
└── generic/
    ├── simple_transactions.csv
    └── multi_account_excel.xlsx
```

Parser authors must include at least one fixture per parser and a corresponding test.
