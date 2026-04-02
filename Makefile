.PHONY: help install dev test lint format run server web docker-up docker-down clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install package in production mode
	pip install -e .

dev: ## Install package with dev dependencies
	pip install -e ".[dev]"
	playwright install chromium

test: ## Run tests with pytest
	pytest tests/ -v --tb=short

test-cov: ## Run tests with coverage
	pytest tests/ -v --tb=short --cov=agentic_computer --cov-report=term-missing

lint: ## Run linter
	ruff check agentic_computer/ tests/

format: ## Format code
	ruff format agentic_computer/ tests/

typecheck: ## Run type checking
	mypy agentic_computer/

run: ## Run the CLI agent
	python -m agentic_computer.main

server: ## Start the FastAPI server
	uvicorn agentic_computer.server.app:app --reload --host 0.0.0.0 --port 8000

web: ## Start the Next.js web UI (dev mode)
	cd web && npm run dev

docker-up: ## Start all services via Docker Compose
	docker compose up -d --build

docker-down: ## Stop all Docker services
	docker compose down

clean: ## Remove build artifacts and caches
	rm -rf build/ dist/ *.egg-info .pytest_cache .mypy_cache .ruff_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
