# FinPort — Financial Portfolio Intelligence Platform

A self-hosted platform for ingesting financial statements (PDF, CSV, Excel) from banks,
brokerages, retirement accounts, credit cards, and crypto exchanges. FinPort normalises
every statement into a unified transaction ledger, reconciles across accounts, and
provides portfolio analytics through a React dashboard.

---

## Features

- **Multi-institution ingestion** — Fidelity, Schwab, Vanguard, Chase, E*TRADE,
  TD Ameritrade, Coinbase, Robinhood, plus a generic CSV/PDF fallback
- **Automatic parser detection** — filename regex, PDF header text, and CSV column
  fingerprinting used to select the right parser without manual configuration
- **Background processing** — Celery workers with Redis broker; file uploads return
  immediately while parsing happens asynchronously
- **Reconciliation engine** — duplicate detection, transfer matching across accounts,
  opening/closing balance verification
- **Portfolio analytics** — net worth over time, allocation by asset class / sector /
  account type, unrealized gain/loss per holding
- **Encrypted file storage** — uploaded statements encrypted at rest with Fernet
- **Docker-first** — full development environment in one command

---

## Quickstart (Docker)

```bash
# 1. Copy and configure environment variables
cp .env.example .env
# Edit .env — at minimum set FERNET_KEY (see instructions inside the file)

# 2. Start all services
docker compose up -d

# 3. Apply database migrations
docker compose exec api alembic upgrade head

# 4. Open the dashboard
open http://localhost:3000
```

API docs are available at [http://localhost:8000/docs](http://localhost:8000/docs).

---

## Local Development (without Docker)

### Prerequisites

| Tool | Version |
|------|---------|
| Python | 3.12+ |
| Node.js | 20 LTS |
| PostgreSQL | 16+ |
| Redis | 7+ |
| poppler | any (for PDF rendering) |
| ghostscript | any (for camelot PDF table extraction) |

### Setup

```bash
# Python dependencies
make install

# Node dependencies
make frontend-install

# Copy and edit environment variables
cp .env.example .env

# Apply database migrations
make migrate

# Terminal 1 — API server
make dev

# Terminal 2 — Celery worker
make worker

# Terminal 3 — Frontend dev server (proxies /api to port 8000)
make frontend-dev
```

Open [http://localhost:5173](http://localhost:5173).

---

## Project Structure

```
finport/
├── backend/                   # FastAPI application
│   ├── app/
│   │   ├── api/v1/endpoints/  # Route handlers
│   │   ├── models/            # SQLAlchemy ORM models
│   │   ├── schemas/           # Pydantic request/response schemas
│   │   ├── services/          # Business logic services
│   │   ├── worker/            # Celery app + task definitions
│   │   ├── database/          # Async engine, session factory
│   │   └── core/              # Config, security, storage, events
│   ├── alembic/               # Database migrations
│   └── tests/
├── parsers/                   # Statement parser framework
│   ├── base/                  # BaseParser ABC + ParserResult contract models
│   ├── generic/               # CSV and PDF fallback parsers
│   ├── institutions/          # Institution-specific parsers (fidelity, ...)
│   ├── registry.py            # ParserRegistry with @register decorator
│   └── detector.py            # Multi-signal institution detector
├── reconciliation/            # Reconciliation rule engine
│   ├── engine.py
│   └── rules/                 # DuplicateDetection, TransferMatching, BalanceVerification
├── analytics/                 # Portfolio analytics calculators
│   ├── engine.py
│   └── calculators/           # NetWorth, Allocation, Gains
├── frontend/                  # React 18 + TypeScript + Vite SPA
│   └── src/
│       ├── pages/             # Dashboard, Imports, Accounts, Transactions, ...
│       ├── components/        # Layout, shared UI
│       └── lib/api.ts         # Axios API client
├── docker/                    # Dockerfiles + nginx config
├── docs/                      # Architecture documentation
│   ├── ARCHITECTURE.md
│   ├── DATA_MODEL.md
│   ├── PARSER_FRAMEWORK.md
│   └── API_SPEC.md
├── docker-compose.yml
├── pyproject.toml
├── Makefile
└── .env.example
```

---

## Adding a New Institution Parser

See [docs/PARSER_FRAMEWORK.md](docs/PARSER_FRAMEWORK.md) for a complete walkthrough.

**Summary:**

1. Create `parsers/institutions/<slug>/parser.py`
2. Subclass `BaseParser` from `parsers.base.parser_interface`
3. Decorate with `@ParserRegistry.register("<slug>", formats=["csv", "pdf"])`
4. Implement `can_parse()`, `extract_metadata()`, `extract_transactions()`,
   `extract_holdings()`, `extract_balances()`
5. Add filename/header/CSV column fingerprint patterns to `parsers/detector.py`

The `FidelityParser` at `parsers/institutions/fidelity/parser.py` serves as the
reference implementation.

---

## Available Make Targets

```
make help
```

| Target | Description |
|--------|-------------|
| `make dev` | Start FastAPI with hot-reload |
| `make worker` | Start Celery worker |
| `make flower` | Start Flower task monitor on :5555 |
| `make migrate` | Apply pending Alembic migrations |
| `make makemigrations MESSAGE="..."` | Generate a new migration |
| `make test` | Run pytest |
| `make test-cov` | Run pytest with HTML coverage report |
| `make lint` | Lint with ruff |
| `make format` | Format with ruff |
| `make typecheck` | Static type check with mypy |
| `make build` | Build Docker images |
| `make up` | Start Docker Compose (detached) |
| `make clean` | Remove build artefacts |

---

## Architecture Documentation

| Document | Contents |
|----------|----------|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System overview, component diagram, tech stack rationale |
| [docs/DATA_MODEL.md](docs/DATA_MODEL.md) | Full ER diagram, ORM model descriptions, field-level notes |
| [docs/PARSER_FRAMEWORK.md](docs/PARSER_FRAMEWORK.md) | Parser contract, detection pipeline, how to add parsers |
| [docs/API_SPEC.md](docs/API_SPEC.md) | REST API endpoints, request/response shapes |

---

## Environment Variables

See [.env.example](.env.example) for the full list with descriptions.

Key variables:

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string (asyncpg) |
| `REDIS_URL` | Redis connection string |
| `FERNET_KEY` | 32-byte URL-safe base64 key for file encryption |
| `SECRET_KEY` | JWT signing key |
| `UPLOAD_MAX_SIZE_MB` | Maximum upload file size (default: 50) |

---

## License

MIT
