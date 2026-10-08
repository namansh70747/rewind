.DEFAULT_GOAL := help

.PHONY: help install lint format typecheck test cov docs docs-build check clean

help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: ## Install project with all extras and set up pre-commit hooks
	uv sync --extra dev --extra docs --extra integrations --extra tui --extra ml
	uv run pre-commit install

lint: ## Run ruff linter
	uv run ruff check .

format: ## Format code with ruff
	uv run ruff format .

typecheck: ## Run mypy static type checks
	uv run mypy

test: ## Run the test suite
	uv run pytest

cov: ## Run tests with coverage report
	uv run pytest --cov=flightrecorder --cov-report=term-missing

docs: ## Serve the documentation locally
	uv run mkdocs serve

docs-build: ## Build the documentation (fails on warnings)
	uv run mkdocs build --strict

check: lint typecheck test ## Run lint, typecheck, and tests

clean: ## Remove caches and build artifacts
	rm -rf build dist *.egg-info
	rm -rf .ruff_cache .mypy_cache .pytest_cache .coverage htmlcov
	find . -type d -name __pycache__ -exec rm -rf {} +
