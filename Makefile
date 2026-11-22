.PHONY: help format format-all lint typecheck test test-all check hooks demo walkthrough
.DEFAULT_GOAL := help
help: ## list these targets
	@awk -F ':.*## ' '/^[a-z-]+:.*## / {printf "make %-12s %s\n", $$1, $$2}' $(MAKEFILE_LIST)
# Scoped on purpose: only the files you name are rewritten.
format: ## fix and format the given files: make format FILES="src/a.py tests/test_a.py"
	@test -n "$(FILES)" || { echo 'usage: make format FILES="path ..."  (whole tree: make format-all)'; exit 2; }
	uv run --locked ruff check --fix $(FILES)
	uv run --locked ruff format $(FILES)
format-all: ## maintenance: fix and format the whole tree (commit it on its own)
	uv run --locked ruff check --fix src tests notebooks
	uv run --locked ruff format src tests notebooks
lint: ## lint, check formatting and check the notebook
	uv run --locked ruff check src tests notebooks
	uv run --locked ruff format --check src tests notebooks
	uv run --locked marimo check --strict notebooks/walkthrough.py
typecheck: ## run mypy
	uv run --locked mypy
test: ## run the tests with coverage, without the slow ones
	uv run --locked pytest -q -n 4 --cov
test-all: ## run every test, the slow ones too (as CI does)
	uv run --locked pytest -q -n 4 --cov -m ''
# Separate recursive calls keep this order under make -j: a failed cheap check
# stops before the tests start.
check: ## all local quality gates
	$(MAKE) lint
	$(MAKE) typecheck
	$(MAKE) test
hooks: ## install the git hooks
	uv run --locked pre-commit install
demo: ## run the hold-out check on a synthetic city (no crash data needed)
	uv run --locked python -m bike_safety_ca.checks.holdout --synthetic
walkthrough: ## open the walkthrough notebook on the demo city (real streets, made-up crashes)
	uv run --locked marimo edit notebooks/walkthrough.py
