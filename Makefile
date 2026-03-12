.PHONY: help dev worker flower migrate makemigrations test lint format typecheck build \
        install frontend-dev frontend-build clean

# ── default target ──────────────────────────────────────────────────────────
help:          ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*##' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*## "}{printf "  \033[36m%-20s\033[0m %s\n",$$1,$$2}'

# ── Python environment ──────────────────────────────────────────────────────
install:       ## Install Python dependencies (editable)
	pip install -e "backend/[dev]"

# ── Backend services ─────────────────────────────────────────────────────────
dev:           ## Start FastAPI with hot-reload
	cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

worker:        ## Start Celery worker (ingestion + reconciliation queues)
	cd backend && celery -A app.worker.celery_app worker \
	    --queues ingestion,reconciliation \
	    --concurrency 2 \
	    --loglevel info

flower:        ## Start Flower task monitor on :5555
	cd backend && celery -A app.worker.celery_app flower --port=5555

# ── Database ─────────────────────────────────────────────────────────────────
migrate:       ## Apply all pending Alembic migrations
	cd backend && alembic upgrade head

makemigrations: ## Generate a new Alembic migration (provide MESSAGE= on CLI)
	@test -n "$(MESSAGE)" || (echo "Usage: make makemigrations MESSAGE='describe change'" && exit 1)
	cd backend && alembic revision --autogenerate -m "$(MESSAGE)"

downgrade:     ## Roll back the last migration
	cd backend && alembic downgrade -1

# ── Tests ─────────────────────────────────────────────────────────────────────
test:          ## Run full pytest suite
	cd backend && pytest

test-cov:      ## Run pytest with coverage report
	cd backend && pytest --cov=app --cov=parsers --cov=reconciliation --cov=analytics \
	    --cov-report=term-missing --cov-report=html

# ── Linting / formatting ──────────────────────────────────────────────────────
lint:          ## Lint with ruff
	ruff check backend parsers reconciliation analytics

format:        ## Format with ruff
	ruff format backend parsers reconciliation analytics

typecheck:     ## Static type checking with mypy
	mypy backend/app parsers reconciliation analytics

# ── Frontend ──────────────────────────────────────────────────────────────────
frontend-install: ## Install Node dependencies
	cd frontend && npm install

frontend-dev:  ## Start Vite dev server on :5173 (proxies /api to :8000)
	cd frontend && npm run dev

frontend-build: ## Production build into frontend/dist
	cd frontend && npm run build

# ── Docker ────────────────────────────────────────────────────────────────────
build:         ## Build all Docker images
	docker compose build

up:            ## Start all services (detached)
	docker compose up -d

down:          ## Stop all services
	docker compose down

logs:          ## Tail logs for all services
	docker compose logs -f

# ── Cleanup ───────────────────────────────────────────────────────────────────
clean:         ## Remove Python/Node build artefacts
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -name "*.pyc" -delete
	rm -rf backend/.mypy_cache backend/.pytest_cache backend/htmlcov
	rm -rf frontend/dist frontend/node_modules/.vite
