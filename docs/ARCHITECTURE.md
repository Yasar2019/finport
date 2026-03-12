# FinPort — Financial Portfolio Intelligence Platform

<!-- markdownlint-disable MD024 -->

## Complete Technical Architecture & Implementation Plan

---

## Part 1 — Expert Review Panel

Before finalising the architecture, the design was stress-tested by five specialists. Their findings are incorporated into all decisions below.

---

### Reviewer 1 — Senior Backend Architect

#### Weaknesses identified

- A naive monolithic design would couple ingestion, parsing, normalisation, and analytics tightly, making SaaS decomposition difficult later.
- Synchronous PDF parsing inside the HTTP request cycle will time-out on large statements (some broker PDFs exceed 200 pages).
- Without explicit API versioning from day one, future breaking changes force either flag-based branching or a full migration.

#### Missing components

- An asynchronous job queue with worker isolation (Celery + Redis).
- A job-status polling mechanism (SSE or a `/imports/{id}/status` endpoint) so the UI can track long-running parses.
- Background task monitoring (Flower dashboard for Celery).
- A CQRS split: write path (ingestion commands) separated from the read path (portfolio queries).

#### Improvements adopted

- All parsing, normalisation, and reconciliation runs in Celery workers; the API only enqueues and returns a job ID.
- Module boundaries are enforced through abstract interfaces, not just directories.
- `v1/` prefix on all API routes from the start.

---

### Reviewer 2 — Data Engineering Specialist

#### Weaknesses identified

- A single parser per institution will fail silently when the institution changes its statement layout.
- Transfer detection across institutions (the same wire appears as a debit at bank A and a credit at bank B) requires a dedicated reconciler — parsers must not guess.
- No schema-level validation guarantees parser output is safe to persist.

#### Missing components

- **Parser versioning**: each parser records its version; re-processing historical imports when the parser is updated must be supported.
- **Data lineage**: every normalised record must carry `import_session_id`, `parser_run_id`, `raw_source_ref` (JSON pointer to the raw row), and `parser_confidence`.
- **Idempotent ingestion**: SHA-256 hash of the uploaded file prevents re-ingesting the same statement.
- A validation layer (Pydantic models) between raw parser output and the persistence layer.

#### Improvements adopted

- The parser outputs `CandidateRecord` Pydantic models, not raw dicts.
- Every ORM model carries provenance columns (`import_session_id`, `parser_run_id`, `parser_confidence`, `raw_source_ref`).
- File deduplication enforced at upload via SHA-256 comparison before any work is done.

---

### Reviewer 3 — Security Engineer

#### Weaknesses identified

- PDF/Excel parsers are attack surfaces: malicious files can trigger exploits in parsing libraries. Workers must be sandboxed.
- Uploaded financial documents contain PII and must be encrypted at rest, not just in transit.
- Common mistake: logging raw account numbers or transaction amounts at DEBUG level.

#### Missing components

- File-type validation (MIME + magic bytes, not just extension) and size limits before accepting uploads.
- Fernet symmetric encryption for files at rest; application-managed key stored in environment.
- Append-only `audit_logs` table — no updates or soft-deletes.
- Argon2-id for password hashing (future multi-user).
- Secure temporary file cleanup after parsing completes.

#### Improvements adopted

- Upload endpoint validates MIME type, enforces a 50 MB size cap, and rejects files that don't match expected magic bytes.
- Uploaded files are encrypted before writing to disk using Fernet; the encryption key lives in the environment only.
- Celery parsing tasks run with restricted filesystem access.
- Sensitive DB columns (account numbers) stored encrypted via SQLAlchemy-level transformation.
- Audit logging wraps every mutation.

---

### Reviewer 4 — FinTech Domain Expert

#### Weaknesses identified

- Cost-basis calculation requires knowing the acquisition lot (FIFO, LIFO, specific lot, or average cost) — this must be a first-class concept.
- Corporate actions (splits, mergers, spin-offs) retroactively change unit quantities and cost basis. Without a `corporate_actions` table, historical performance is inaccurate.
- Dividend reinvestment (DRIP) creates fractional-share purchases — easy to mis-classify as pure income.
- Ticker symbols are not a reliable security primary key: the same Bloomberg ticker can change meaning; CUSIP/ISIN is authoritative.

#### Missing components

- `tax_lots` table for acquisition-level cost basis.
- `corporate_actions` table with split ratios.
- `security_aliases` to map institution-specific identifiers to the canonical SecurityMaster.
- FX rate storage for multi-currency portfolios.
- Return-of-capital handling (tax treatment differs from ordinary dividends).
- Transaction classification taxonomy: `buy`, `sell`, `dividend_cash`, `dividend_reinvest`, `interest`, `fee_commission`, `fee_management`, `fee_other`, `transfer_in`, `transfer_out`, `deposit`, `withdrawal`, `return_of_capital`, `corporate_action`, `split_adjustment`, `option_exercise`, `margin_interest`, `journal`.

#### Improvements adopted

- SecurityMaster is a dedicated table; all holdings/transactions reference it by ID.
- `security_aliases` resolve institution-specific symbols.
- `corporate_actions` table with `ratio_from`/`ratio_to` and effective date.
- `tax_lots` enables per-lot gain/loss calculation.
- Transaction type is an Enum with the full taxonomy above.

---

### Reviewer 5 — DevOps / Infrastructure Engineer

#### Weaknesses identified

- Heavy PDF libraries (camelot, pdfminer) can consume 500 MB+ RAM per worker; workers must be isolated and resource-limited.
- Using SQLite in a Docker volume is fragile; the architecture must make PostgreSQL the standard target from Phase 1.
- No storage abstraction — `open("path")` calls scattered through code make S3 migration expensive later.

#### Missing components

- Docker Compose with services: `api`, `worker`, `redis`, `db`, `frontend`, `flower`.
- A `StorageBackend` abstraction (local filesystem today, S3-compatible tomorrow).
- Health-check endpoints (`/health`, `/readiness`).
- Alembic for migrations from day one.
- `Makefile` with standard dev commands.
- Graceful worker shutdown (SIGTERM handling in Celery).

#### Improvements adopted

- `StorageBackend` interface with `LocalStorageBackend` and a stub `S3StorageBackend`.
- Full Docker Compose provided.
- `GET /health` returns service status and DB connectivity.
- Alembic wired up with `env.py` targeting the async engine.

---

## Part 2 — System Architecture

### 2.1 High-Level Component Map

```text
┌─────────────────────────────────────────────────────────────────────┐
│                        FINPORT PLATFORM                             │
│                                                                     │
│  ┌─────────────┐    ┌──────────────────────────────────────────┐   │
│  │   React UI  │───▶│           FastAPI (v1)                   │   │
│  │  (Vite/TS)  │    │  /imports  /accounts  /holdings          │   │
│  └─────────────┘    │  /transactions  /analytics  /reconcile   │   │
│                     └──────────────────┬─────────────────────–─┘   │
│                                        │                            │
│               ┌────────────────────────▼──────────────────────┐    │
│               │               Celery Task Queue                │    │
│               │    ┌──────────────────────────────────────┐    │    │
│               │    │           Worker Pool                │    │    │
│               │    │  ┌──────────┐  ┌─────────────────┐  │    │    │
│               │    │  │ Ingestion│  │   Parse Task    │  │    │    │
│               │    │  │  Task   │  │ (per-file)      │  │    │    │
│               │    │  └────┬────┘  └────────┬────────┘  │    │    │
│               │    │       │               │            │    │    │
│               │    │  ┌────▼───────────────▼────────┐   │    │    │
│               │    │  │    Normalisation Pipeline   │   │    │    │
│               │    │  └──────────────┬──────────────┘   │    │    │
│               │    │                 │                   │    │    │
│               │    │  ┌──────────────▼──────────────┐   │    │    │
│               │    │  │   Reconciliation Engine     │   │    │    │
│               │    │  └─────────────────────────────┘   │    │    │
│               │    └──────────────────────────────────┘    │    │
│               │           (Redis broker)                    │    │
│               └────────────────────────────────────────────┘    │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────┐     │
│  │                    PostgreSQL Database                     │     │
│  │  institutions · accounts · import_sessions · statements    │     │
│  │  transactions · securities · holdings · tax_lots           │     │
│  │  dividends · fees · transfers · reconciliation_records     │     │
│  │  corporate_actions · audit_logs · parser_runs              │     │
│  └───────────────────────────────────────────────────────────┘     │
│                                                                     │
│  ┌──────────────────────────────────┐                              │
│  │       Encrypted File Store       │                              │
│  │  (local: /data/uploads           │                              │
│  │   future: S3-compatible)         │                              │
│  └──────────────────────────────────┘                              │
└─────────────────────────────────────────────────────────────────────┘
```

---

### 2.2 Service Boundaries

| Layer | Responsibility | Process |
| --- | --- | --- |
| **API Layer** | HTTP handling, auth, file validation, job dispatch | FastAPI (uvicorn) |
| **Task Layer** | CPU-intensive parsing, normalisation, reconciliation | Celery workers |
| **Parser Framework** | Institution-specific and generic document parsing | Library (imported by workers) |
| **Normalisation Pipeline** | CandidateRecords → ORM models | Library (imported by workers) |
| **Reconciliation Engine** | Duplicate detection, transfer matching, balance checks | Library (imported by workers) |
| **Analytics Engine** | Portfolio aggregation, gain/loss, allocation | Library (imported by API + workers) |
| **Storage Abstraction** | File I/O, encryption, path resolution | Library |
| **Database** | Persistence, migrations | PostgreSQL + SQLAlchemy async |
| **Message Broker** | Task queue, result backend | Redis |
| **Frontend** | UI, charts, upload, corrections | React + TypeScript (Vite) |

---

### 2.3 Core Data Flow — Statement Ingestion

```text
User uploads file (PDF / CSV / Excel)
          │
          ▼
[API] validate_upload()
  • MIME + magic-byte check
  • Size limit (50 MB)
  • Compute SHA-256 hash
  • Check duplicate hash in import_sessions
  • Encrypt + write to file store
  • Create ImportSession(status=PENDING)
  • Return {import_session_id, status_url}
          │
          ▼
[Celery] task: run_ingestion_pipeline(import_session_id)
  │
  ├─ Step 1: Detect institution & format
  │     • Filename heuristics
  │     • PDF text header analysis
  │     • CSV column fingerprinting
  │     • Returns: InstitutionDetectionResult
  │
  ├─ Step 2: Select parser
  │     • ParserRegistry.get_parser(institution, format)
  │     • Falls back to GenericParser if no match
  │     • Logs parser selection + confidence
  │
  ├─ Step 3: Execute parser
  │     • Structured extraction (pdfplumber tables / pandas)
  │     • OCR fallback if structured yield < threshold
  │     • Outputs: List[CandidateRecord]
  │     • Writes ParserRun record with confidence score
  │
  ├─ Step 4: Validate candidates
  │     • Pydantic validation of each CandidateRecord
  │     • Invalid records → ParserRun.warnings
  │
  ├─ Step 5: Normalise candidates
  │     • CandidateRecord → ORM entities
  │     • Resolve security symbols → SecurityMaster
  │     • Attach provenance (import_session_id, parser_run_id, raw_source_ref)
  │     • Persist to DB (transactions, holdings, dividends, fees, balances)
  │
  ├─ Step 6: Reconcile
  │     • Duplicate transaction detection
  │     • Transfer pair matching
  │     • Balance verification
  │     • Generate ReconciliationRecord rows (warnings / errors)
  │
  └─ Step 7: Update ImportSession(status=COMPLETED | NEEDS_REVIEW)
             • Emit completion event
             • UI polls /imports/{id}/status
```

---

### 2.4 Security Architecture

```text
TRANSPORT:  TLS everywhere (HTTPS in production, localhost in dev)

AUTHENTICATION:
  • Phase 1: single-user with config-file bearer token (local-only)
  • Phase 2: JWT (HS256 → RS256) with refresh token rotation
  • Phase 5: OAuth2/OIDC for SaaS multi-tenant

FILE STORAGE:
  • Fernet symmetric encryption (AES-128-CBC + HMAC-SHA256)
  • Key from STORAGE_ENCRYPTION_KEY env var (never in code)
  • Files written to /data/uploads/{user_id}/{session_id}/
  • Original filenames never used on disk (UUID-based paths)

DATABASE:
  • Account numbers stored encrypted (app-layer AES via SQLAlchemy TypeDecorator)
  • Sensitive fields (SSN if ever needed) never stored plain
  • Audit log is append-only; application user has no DELETE privilege on audit_logs

PROCESS ISOLATION:
  • Celery workers run as non-root user
  • Parsed temp files deleted immediately after processing
  • Parser exceptions caught and logged; never surfaced raw to API responses

UPLOADS:
  • Max file size: 50 MB
  • Allowed MIME types enforced via python-magic (magic bytes, not just extension)
  • File content scanned for ZIP bombs (PDF deflate attacks)
```

---

### 2.5 Technology Stack Justification

| Choice | Rationale |
| --- | --- |
| **Python 3.12** | Rich ecosystem for document parsing, finance, and data engineering. Pydantic v2 and SQLAlchemy 2.0 make it excellent for typed domain models. |
| **FastAPI** | Native async, auto-generated OpenAPI docs, Pydantic-native request/response models, excellent performance. Straightforward to migrate to microservices later. |
| **SQLAlchemy 2.0 async** | Type-safe ORM, async-native, Alembic support for migrations, compatible with both SQLite (dev) and PostgreSQL (prod). |
| **PostgreSQL** | ACID transactions essential for financial data integrity. JSON columns for `raw_source_ref`. pgcrypto for column-level encryption. Superior to SQLite for concurrent write workloads. |
| **Celery + Redis** | Proven at scale for background tasks. Redis doubles as result backend and cache. Flower provides task monitoring. Trivially scales horizontally. |
| **pdfplumber + camelot** | Best in class for structured PDF table extraction without needing Java (avoiding Tabula). Camelot excels at lattice tables; pdfplumber at stream extraction. |
| **pandas + openpyxl** | Industry standard for CSV/Excel ingestion. Handles encoding quirks, multi-header layouts, and merged cells. |
| **pytesseract (fallback)** | For scanned PDFs where structured extraction yields nothing useful. Used only as a last resort. |
| **React 18 + TypeScript** | Component-based UI, strong typing prevents runtime financial display errors. Vite for fast HMR. |
| **TanStack Query** | Optimal for the polling-based import status updates and stale-while-revalidate patterns needed for portfolio data. |
| **Recharts** | React-native charting, composable, well-typed. Sufficient for allocation pie charts, time-series balance charts, and gain/loss bar charts. |
| **Tailwind CSS + shadcn/ui** | Rapid UI development. shadcn/ui components are copy-paste (no black-box library), fully customisable. |
| **Alembic** | Database migration management from day one. Critical for SaaS where schema evolution must not break production. |
| **Docker Compose** | Reproducible local dev environment matching production topology. Single `make dev` command to spin up all services. |

---

### 2.6 Future SaaS Migration Path

The local-first architecture is deliberately designed to permit SaaS evolution without rewrites.

| Concern | Local (Phase 1) | SaaS (Phase 5) |
| --- | --- | --- |
| Auth | Single-user bearer token | Auth0 / Cognito OIDC |
| File storage | Local encrypted filesystem | AWS S3 / Cloudflare R2 (same `StorageBackend` interface) |
| Database | PostgreSQL (Docker) | AWS RDS / Supabase — add `tenant_id` column via migration |
| Workers | Single Celery worker | Auto-scaling ECS / Kubernetes worker pods |
| Config | `.env` file | AWS Secrets Manager / Vault |
| Monitoring | Flower | Datadog / OpenTelemetry |
| Multi-tenancy | `user_id` column exists from day one | Enable row-level security in PostgreSQL |

The single most important SaaS-readiness decision is adding `user_id` to every entity table from Phase 1, even when there is only one user. This means the multi-tenant migration is an index + RLS policy, not a schema redesign.
