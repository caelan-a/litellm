# LiteLLM Makefile
# Simple Makefile for running tests and basic development tasks

.PHONY: help test test-unit test-integration test-unit-helm lint format install-dev install-proxy-dev install-test-deps install-helm-unittest check-circular-imports check-import-safety

# Default target
help:
	@echo "Available commands:"
	@echo "  make install-dev        - Install development dependencies"
	@echo "  make install-proxy-dev  - Install proxy development dependencies"
	@echo "  make install-dev-ci     - Install dev dependencies (CI-compatible, pins OpenAI)"
	@echo "  make install-proxy-dev-ci - Install proxy dev dependencies (CI-compatible)"
	@echo "  make install-test-deps  - Install test dependencies"
	@echo "  make install-helm-unittest - Install helm unittest plugin"
	@echo "  make format             - Apply Black code formatting"
	@echo "  make format-check       - Check Black code formatting (matches CI)"
	@echo "  make lint               - Run all linting (Ruff, MyPy, Black check, circular imports, import safety)"
	@echo "  make lint-ruff          - Run Ruff linting only"
	@echo "  make lint-mypy          - Run MyPy type checking only"
	@echo "  make lint-black         - Check Black formatting (matches CI)"
	@echo "  make check-circular-imports - Check for circular imports"
	@echo "  make check-import-safety - Check import safety"
	@echo "  make test               - Run all tests"
	@echo "  make test-unit          - Run unit tests (tests/test_litellm)"
	@echo "  make test-integration   - Run integration tests"
	@echo "  make test-unit-helm     - Run helm unit tests"

# Installation targets
install-dev:
	poetry install --with dev

install-proxy-dev:
	poetry install --with dev,proxy-dev --extras proxy

# CI-compatible installations (matches GitHub workflows exactly)
install-dev-ci:
	pip install openai==2.8.0
	poetry install --with dev
	pip install openai==2.8.0

install-proxy-dev-ci:
	poetry install --with dev,proxy-dev --extras proxy
	pip install openai==2.8.0

install-test-deps: install-proxy-dev
	poetry run pip install "pytest-retry==1.6.3"
	poetry run pip install pytest-xdist
	cd enterprise && poetry run pip install -e . && cd ..

install-helm-unittest:
	helm plugin install https://github.com/helm-unittest/helm-unittest --version v0.4.4 || echo "ignore error if plugin exists"

# Formatting
format: install-dev
	cd litellm && poetry run black . && cd ..

format-check: install-dev
	cd litellm && poetry run black --check . && cd ..

# Linting targets
lint-ruff: install-dev
	cd litellm && poetry run ruff check . && cd ..

lint-mypy: install-dev
	poetry run pip install types-requests types-setuptools types-redis types-PyYAML
	cd litellm && poetry run mypy . --ignore-missing-imports && cd ..

lint-black: format-check

check-circular-imports: install-dev
	cd litellm && poetry run python ../tests/documentation_tests/test_circular_imports.py && cd ..

check-import-safety: install-dev
	poetry run python -c "from litellm import *" || (echo '🚨 import failed, this means you introduced unprotected imports! 🚨'; exit 1)

# Combined linting (matches test-linting.yml workflow)
lint: format-check lint-ruff lint-mypy check-circular-imports check-import-safety

# Testing targets
test:
	poetry run pytest tests/

test-unit: install-test-deps
	poetry run pytest tests/test_litellm -x -vv -n 4

test-integration:
	poetry run pytest tests/ -k "not test_litellm"

test-unit-helm: install-helm-unittest
	helm unittest -f 'tests/*.yaml' deploy/charts/litellm-helm

# LLM Translation testing targets
test-llm-translation: install-test-deps
	@echo "Running LLM translation tests..."
	@python .github/workflows/run_llm_translation_tests.py

test-llm-translation-single: install-test-deps
	@echo "Running single LLM translation test file..."
	@if [ -z "$(FILE)" ]; then echo "Usage: make test-llm-translation-single FILE=test_filename.py"; exit 1; fi
	@mkdir -p test-results
	poetry run pytest tests/llm_translation/$(FILE) \
		--junitxml=test-results/junit.xml \
		-v --tb=short --maxfail=100 --timeout=300

# =============================================================================
# Vertex AI Claude Proxy Targets
# =============================================================================

PROXY_PORT ?= 45678
NGROK_PORT ?= $(PROXY_PORT)

.PHONY: proxy-vertex proxy-vertex-debug ngrok ngrok-url proxy-test

# Run the proxy with Vertex AI Claude config
proxy-vertex:
	@echo "Starting LiteLLM proxy for Vertex AI Claude on port $(PROXY_PORT)..."
	poetry run litellm --config litellm_vertex_claude_config.yaml --port $(PROXY_PORT)

# Run the proxy with debug logging
proxy-vertex-debug:
	@echo "Starting LiteLLM proxy for Vertex AI Claude on port $(PROXY_PORT) with debug logging..."
	poetry run litellm --config litellm_vertex_claude_config.yaml --port $(PROXY_PORT) --detailed_debug

# Start ngrok and display the URL
ngrok:
	@echo "Starting ngrok tunnel on port $(NGROK_PORT)..."
	@echo "Press Ctrl+C to stop ngrok"
	ngrok http $(NGROK_PORT)

# Get ngrok URL (requires ngrok to be running with API enabled)
ngrok-url:
	@echo "Fetching ngrok public URL..."
	@curl -s http://localhost:4040/api/tunnels | python3 -c "import sys, json; tunnels=json.load(sys.stdin)['tunnels']; print(tunnels[0]['public_url'] if tunnels else 'No tunnels found. Is ngrok running?')" 2>/dev/null || echo "ngrok API not available. Make sure ngrok is running."

# Start ngrok in background and print URL
ngrok-start:
	@echo "Starting ngrok in background on port $(NGROK_PORT)..."
	@ngrok http $(NGROK_PORT) > /dev/null 2>&1 &
	@sleep 2
	@echo "Ngrok URL:"
	@curl -s http://localhost:4040/api/tunnels | python3 -c "import sys, json; tunnels=json.load(sys.stdin)['tunnels']; print(tunnels[0]['public_url'] if tunnels else 'Failed to get URL')" 2>/dev/null || echo "Failed to get ngrok URL"

# Test the proxy
proxy-test:
	@echo "Testing Vertex AI Claude proxy..."
	python test_vertex_claude.py --proxy-url http://localhost:$(PROXY_PORT)

# Full setup: install, run proxy in background, start ngrok
proxy-setup:
	@echo "=== Vertex AI Claude Proxy Setup ==="
	@echo "1. Make sure GOOGLE_APPLICATION_CREDENTIALS is set"
	@echo "2. Run 'make proxy-vertex-debug' in one terminal"
	@echo "3. Run 'make ngrok' in another terminal"
	@echo "4. Run 'make proxy-test' to verify"
	@echo ""
	@echo "For Cursor IDE configuration:"
	@echo "  - API Base: <ngrok-url>/v1"
	@echo "  - API Key: sk-litellm-cursor-proxy"
	@echo "  - Model: claude-sonnet-4.5 or claude-opus-4.5"