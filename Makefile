# jansky-forge — antenna design/build/characterization (see plans/jansky_forge.md).
# Mirrors the jansky / jansky-research / jansky-observe conventions: everything goes
# through uv so you get the pinned Python 3.12 environment.

.DEFAULT_GOAL := help

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

setup: ## Install the pinned environment (uv sync)
	uv sync

test: ## Run the test suite
	uv run pytest

cov: ## Tests with coverage (85% floor)
	uv run pytest --cov=jansky_forge --cov-report=term-missing

lint: ## Ruff lint
	uv run ruff check src/ tests/

fmt: ## Ruff format
	uv run ruff format src/ tests/

typecheck: ## Mypy
	uv run mypy

catalog: ## List the catalog (the M0 smoke: does the package actually work?)
	uv run jansky-forge list

audit: ## Catalog provenance audit — must print nothing
	uv run python -c "from jansky_forge import catalog; [print(m) for m in catalog.audit()]"

build: ## Build sdist + wheel into dist/
	uv build

clean: ## Remove caches and build artifacts
	rm -rf .pytest_cache/ .ruff_cache/ .mypy_cache/ dist/ .coverage out/
	find . -type d -name __pycache__ -prune -exec rm -rf {} +

.PHONY: help setup test cov lint fmt typecheck catalog audit build clean
