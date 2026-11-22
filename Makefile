.PHONY: help format lint typecheck test check hooks demo walkthrough
.DEFAULT_GOAL := help
help: ## list these targets
	@awk -F ':.*## ' '/^[a-z-]+:.*## / {printf "make %-12s %s\n", $$1, $$2}' $(MAKEFILE_LIST)
format: ## apply safe lint fixes and format
	uv run --locked ruff check --fix src tests notebooks
	uv run --locked ruff format src tests notebooks
lint: ## lint and check formatting
	uv run --locked ruff check src tests notebooks
	uv run --locked ruff format --check src tests notebooks
typecheck: ## run mypy
	uv run --locked mypy
test: ## run the tests with coverage
	uv run --locked pytest -q --cov
check: lint typecheck test ## all local quality gates
hooks: ## install the git hooks
	uv run --locked pre-commit install
demo: ## run the hold-out check on a synthetic city (no crash data needed)
	uv run --locked python -m bike_safety_ca.checks.holdout --synthetic
walkthrough: ## open the walkthrough notebook on the demo city (real streets, made-up crashes)
	uv run --locked marimo edit notebooks/walkthrough.py
