# Auralynq — Talk to Your Data. Podman-first, local at $0.
.DEFAULT_GOAL := help
SHELL := /usr/bin/env bash

# Use uv if present, else fall back to python -m venv + pip.
UV := $(shell command -v uv 2>/dev/null)
VENV := .venv
PY := $(VENV)/bin/python
PYTEST := $(VENV)/bin/pytest
RUFF := $(VENV)/bin/ruff
MYPY := $(VENV)/bin/mypy

# Resolve the Podman Compose command lazily inside stack targets.
COMPOSE = $$(./scripts/check_container_runtime.sh)
COMPOSE_FILE := compose.yml

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------- setup -----
.PHONY: setup
setup: ## Create venv and install dev + light deps (no heavy ML stack)
ifeq ($(UV),)
	python3 -m venv $(VENV)
	$(PY) -m pip install -U pip
	$(PY) -m pip install -e ".[dev,ingest,eval]"
else
	uv venv $(VENV)
	uv pip install --python $(PY) -e ".[dev,ingest,eval]"
endif
	@echo "✓ setup complete. Activate with: source $(VENV)/bin/activate"

.PHONY: setup-all
setup-all: ## Install ALL extras (heavy: embeddings, voice, vector, agent, telemetry, mcp)
ifeq ($(UV),)
	$(PY) -m pip install -e ".[all,dev]"
else
	uv pip install --python $(PY) -e ".[all,dev]"
endif

# ----------------------------------------------------------- containers -----
.PHONY: runtime-check
runtime-check: ## Verify Podman Compose is available
	@echo "Using: $$(./scripts/check_container_runtime.sh)"

.PHONY: stack-build
stack-build: ## Build container images via Podman Compose
	$(COMPOSE) -f $(COMPOSE_FILE) build

.PHONY: images
images: ## Build versioned images (X.Y.Z, X.Y, git-sha, latest) + OCI labels
	./scripts/build_images.sh

.PHONY: push
push: ## Push versioned images to the registry (GHCR; needs `registry login`)
	./scripts/push_images.sh

.PHONY: version
version: ## Print the resolved image version + tags
	@bash -c 'source scripts/image_env.sh; echo "version: $$AURALYNQ_VERSION"; echo "tags   : $$(image_tags)"; echo "registry: $$AURALYNQ_REGISTRY/$$AURALYNQ_IMAGE_NAMESPACE"'

.PHONY: stack-up
stack-up: ## Start Qdrant, API, worker, web UI, Phoenix (hardened ordering)
	./scripts/stack_up.sh

.PHONY: stack-down
stack-down: ## Stop the stack
	$(COMPOSE) -f $(COMPOSE_FILE) down

.PHONY: stack-logs
stack-logs: ## Tail stack logs
	$(COMPOSE) -f $(COMPOSE_FILE) logs -f

.PHONY: start
start: ## Run locally on 172.24.50.21:2002 (ports 2002/2004-2010)
	./scripts/run_local.sh start

.PHONY: stop
stop: ## Stop the local run
	./scripts/run_local.sh stop

.PHONY: restart
restart: ## Restart the local run
	./scripts/run_local.sh restart

.PHONY: status
status: ## Show local run container status
	./scripts/run_local.sh status

# ----------------------------------------------------------------- data -----
.PHONY: data
data: ## Download sample text + voice datasets (no paid keys)
	$(PY) scripts/download_data.py --sample

.PHONY: data-full
data-full: ## Download full datasets
	$(PY) scripts/download_data.py --full

.PHONY: index
index: ## Build vector index + knowledge graph from ingested data
	$(PY) -m auralynq.cli index --input data/corpus

# ------------------------------------------------------------- run/demo -----
.PHONY: run
run: ## Ask a sample question end-to-end (CLI)
	$(PY) -m auralynq.cli ask "What is Auralynq and how does PathRAG work?"

.PHONY: serve
serve: ## Start the FastAPI backend
	$(PY) -m auralynq.cli serve

.PHONY: mcp
mcp: ## Start the auralynq-mcp server (stdio)
	$(PY) -m auralynq.mcp_server.server

.PHONY: demo
demo: ## Reproducible end-to-end demo (ingest -> index -> ask, text + voice)
	$(PY) scripts/demo.py

# --------------------------------------------------------------- quality ----
.PHONY: test
test: ## Run the test suite
	$(PYTEST)

.PHONY: coverage
coverage: ## Run tests with coverage (core threshold enforced)
	$(PYTEST) --cov=auralynq --cov-report=term-missing --cov-report=xml \
		--cov-fail-under=80 \
		tests/

.PHONY: lint
lint: ## Ruff lint + format check
	$(RUFF) check auralynq tests scripts
	$(RUFF) format --check auralynq tests scripts

.PHONY: fmt
fmt: ## Auto-format with ruff
	$(RUFF) check --fix auralynq tests scripts
	$(RUFF) format auralynq tests scripts

.PHONY: typecheck
typecheck: ## mypy type check
	$(MYPY) auralynq

.PHONY: name-audit
name-audit: ## Verify consistent Auralynq naming across the repo
	$(PY) scripts/name_audit.py

# ----------------------------------------------------------- eval/bench -----
.PHONY: eval
eval: ## Run evaluation harness, write reports/
	$(PY) -m auralynq.cli eval --report

.PHONY: bench
bench: ## Benchmark Qdrant recall/latency/memory trade-offs
	$(PY) -m auralynq.cli bench --report

# --------------------------------------------------------------- misc -------
.PHONY: clean
clean: ## Remove caches and build artifacts
	rm -rf .pytest_cache .ruff_cache .mypy_cache htmlcov .coverage coverage.xml build dist
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
