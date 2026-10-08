.PHONY: help up down logs migrate test lint install dev-api dev-web build-web
ifeq ($(OS),Windows_NT)
PYTHON ?= $(abspath .venv/Scripts/python.exe)
else
PYTHON ?= $(abspath .venv/bin/python)
endif

help:
	@echo "Targets: up down logs migrate test lint install dev-api dev-web build-web"
up:
	docker compose up --build -d
down:
	docker compose down
logs:
	docker compose logs -f api
migrate:
	cd apps/api && "$(PYTHON)" -m alembic upgrade head
test:
	"$(PYTHON)" -m pytest -q
lint:
	cd apps/web && npm run lint
install:
	"$(PYTHON)" -m pip install -r apps/api/requirements-dev.txt
	cd apps/web && npm ci
dev-api:
	cd apps/api && "$(PYTHON)" -m uvicorn src.main:app --reload --host 127.0.0.1 --port 8000
dev-web:
	cd apps/web && npm run dev -- --host 127.0.0.1
build-web:
	cd apps/web && npm run build
