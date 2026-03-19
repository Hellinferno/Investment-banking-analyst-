# ============================================================================
# AIBAA Makefile — Development & Production Convenience Commands
# ============================================================================

.PHONY: help up down logs test lint migrate clean shell-api install dev-api dev-web

PYTHON := .venv/Scripts/python.exe
PIP    := .venv/Scripts/pip.exe
API_DIR := apps/api

# Default target
help:
	@echo "Available commands:"
	@echo "  make up         — Start all services with Docker Compose"
	@echo "  make down       — Stop all services"
	@echo "  make logs       — Follow API service logs"
	@echo "  make test       — Run all backend tests"
	@echo "  make lint       — Run linters (ruff, eslint)"
	@echo "  make migrate    — Run Alembic migrations"
	@echo "  make clean      — Remove Docker volumes and cached files"
	@echo "  make shell-api  — Open a shell in the API container"
	@echo "  make install    — Install all Python dependencies"
	@echo "  make dev-api    — Start FastAPI dev server (no Docker)"
	@echo "  make dev-web    — Start Vite dev server (no Docker)"

# ---- Docker Compose --------------------------------------------------------

up:
	docker compose up --build -d
	@echo "API:  http://localhost:8000/docs"
	@echo "Web:  http://localhost:3000"

down:
	docker compose down

logs:
	docker compose logs -f api

clean:
	docker compose down -v --remove-orphans
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true

shell-api:
	docker compose exec api bash

# ---- Database Migrations ---------------------------------------------------

migrate:
	cd $(API_DIR) && $(PYTHON) -m alembic upgrade head

migrate-down:
	cd $(API_DIR) && $(PYTHON) -m alembic downgrade -1

migrate-new:
	@read -p "Migration name: " name; \
	cd $(API_DIR) && $(PYTHON) -m alembic revision --autogenerate -m "$$name"

# ---- Testing ---------------------------------------------------------------

test:
	cd $(API_DIR) && $(PYTHON) -m pytest src/ -v --tb=short 2>&1

test-unit:
	cd $(API_DIR) && $(PYTHON) -m pytest src/ -v -m unit --tb=short 2>&1

test-integration:
	cd $(API_DIR) && $(PYTHON) -m pytest src/ -v -m integration --tb=short 2>&1

# ---- Linting ---------------------------------------------------------------

lint:
	$(PYTHON) -m ruff check $(API_DIR)/src/ --fix 2>&1 || true
	cd apps/web && npx eslint src/ --fix 2>&1 || true

# ---- Local Development (without Docker) ------------------------------------

install:
	$(PIP) install -r $(API_DIR)/requirements.txt

dev-api:
	cd $(API_DIR) && $(PYTHON) -m uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

dev-web:
	cd apps/web && npm run dev
