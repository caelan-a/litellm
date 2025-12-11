# LiteLLM Makefile
# Simple Makefile for running tests and basic development tasks

.PHONY: help test test-unit test-integration test-unit-helm lint format install-dev install-proxy-dev install-test-deps install-helm-unittest check-circular-imports check-import-safety

# Default target
help:
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "🚀 VERTEX AI CLAUDE PROXY (Docker-based)"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "  make start          - 🚀 Start proxy + ngrok"
	@echo "  make stop-all       - 🛑 Stop everything"
	@echo "  make restart        - 🔄 Restart everything"
	@echo "  make url            - 📡 Show ngrok URL & Cursor config"
	@echo "  make proxy-status   - 📊 Show service status"
	@echo "  make logs           - 📜 Show proxy logs"
	@echo "  make logs-follow    - 📜 Follow logs in real-time (raw)"
	@echo "  make logs-watch     - 🔍 Watch logs (parsed & highlighted)"
	@echo "  make logs-search pattern=\"term\" - 🔎 Search logs"
	@echo ""
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "☁️  Cloud Deployment"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "  make init-cloud     - 🚀 Initialize GCE VM (one-time setup)"
	@echo "  make deploy         - 🔄 Deploy code updates (preserves data)"
	@echo "  make setup-https    - 🔒 Setup HTTPS with Cloudflare Tunnel"
	@echo "  📖 See DEPLOYMENT.md for details"
	@echo ""
	@echo "📖 First time? Read: VERTEX_CLAUDE_SETUP.md"
	@echo "   (You'll need a free ngrok auth token)"
	@echo ""
	@echo "🐛 Debugging issues? Use: make logs-watch"
	@echo ""
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "📦 Development Commands"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "  make install-dev        - Install development dependencies"
	@echo "  make install-proxy-dev  - Install proxy development dependencies"
	@echo "  make install-test-deps  - Install test dependencies"
	@echo ""
	@echo "  make format             - Apply Black code formatting"
	@echo "  make lint               - Run all linting"
	@echo "  make test               - Run all tests"
	@echo "  make test-unit          - Run unit tests"
	@echo ""
	@echo "For more commands, see the Makefile"

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
PROXY_CONFIG ?= litellm_vertex_claude_config.yaml

.PHONY: proxy-vertex proxy-vertex-debug ngrok ngrok-url proxy-test
.PHONY: proxy-status proxy-stop ngrok-stop stop-all start restart url

# ====================
# 🚀 EASY COMMANDS (Docker-based)
# ====================

# Start everything (proxy + ngrok) in Docker
start:
	@echo "🚀 Starting LiteLLM Proxy + Ngrok (Docker)..."
	@echo ""
	@if [ ! -f ".env" ]; then \
		echo "❌ ERROR: .env file not found!"; \
		echo ""; \
		echo "Create .env file with:"; \
		echo "  NGROK_AUTHTOKEN=your_token_here"; \
		echo ""; \
		echo "Get token from: https://dashboard.ngrok.com/get-started/your-authtoken"; \
		exit 1; \
	fi
	@if ! grep -q "NGROK_AUTHTOKEN=" .env; then \
		echo "❌ ERROR: NGROK_AUTHTOKEN not set in .env file!"; \
		echo ""; \
		echo "Add this line to .env:"; \
		echo "  NGROK_AUTHTOKEN=your_token_here"; \
		exit 1; \
	fi
	@if [ ! -f "$$GOOGLE_APPLICATION_CREDENTIALS" ] && [ ! -f "$$HOME/.config/gcloud/application_default_credentials.json" ]; then \
		echo "⚠️  Warning: Google Cloud credentials not found"; \
		echo "   Run: gcloud auth application-default login"; \
		echo ""; \
	fi
	@docker-compose -f docker-compose.vertex-claude.yml up -d
	@echo ""
	@echo "⏳ Waiting for services to be ready..."
	@sleep 7
	@$(MAKE) -s proxy-status
	@echo ""
	@$(MAKE) -s url

# Stop everything
stop-all:
	@echo "🛑 Stopping LiteLLM Proxy + Ngrok (Docker)..."
	@docker-compose -f docker-compose.vertex-claude.yml down
	@echo "✅ All services stopped"

# Restart everything
restart:
	@echo "🔄 Restarting LiteLLM Proxy + Ngrok (Docker)..."
	@docker-compose -f docker-compose.vertex-claude.yml restart
	@sleep 5
	@$(MAKE) -s url

# Get the ngrok URL and show config
url:
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "📡 NGROK PUBLIC URL:"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@URL=$$(curl -s http://localhost:4040/api/tunnels 2>/dev/null | python3 -c "import sys, json; data = json.load(sys.stdin); print(data['tunnels'][0]['public_url'] if data.get('tunnels') else '')" 2>/dev/null); \
	if [ -z "$$URL" ]; then \
		echo "❌ Ngrok not running or URL not available"; \
		echo "   Run 'make start' to start services"; \
	else \
		echo ""; \
		echo "🌐 Public URL: $$URL"; \
		echo ""; \
		echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"; \
		echo "🔧 CURSOR CONFIGURATION:"; \
		echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"; \
		echo ""; \
		echo "  API Base URL:  $$URL/v1"; \
		echo "  API Key:       (any value works)"; \
		echo ""; \
		echo "  Available Models:"; \
		echo "    • claude-sonnet-4.5"; \
		echo "    • claude-4.5-sonnet"; \
		echo "    • claude-4.5-sonnet-thinking"; \
		echo "    • claude-opus-4.5"; \
		echo "    • claude-4.5-opus"; \
		echo "    • claude-4.5-opus-thinking"; \
		echo ""; \
		echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"; \
		echo "📋 QUICK TEST:"; \
		echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"; \
		echo ""; \
		echo "  curl $$URL/v1/chat/completions \\"; \
		echo "    -H 'Content-Type: application/json' \\"; \
		echo "    -d '{"; \
		echo "      \"model\": \"claude-sonnet-4.5\","; \
		echo "      \"messages\": [{\"role\": \"user\", \"content\": \"Hi\"}]"; \
		echo "    }'"; \
		echo ""; \
		echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"; \
	fi

# Show status of all services
proxy-status:
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "📊 SERVICE STATUS (Docker)"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo ""
	@docker-compose -f docker-compose.vertex-claude.yml ps
	@echo ""
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo ""
	@echo "💡 Quick commands:"
	@echo "   make start        - Start everything"
	@echo "   make stop-all     - Stop everything"
	@echo "   make restart      - Restart everything"
	@echo "   make url          - Show ngrok URL & config"
	@echo "   make logs         - Show proxy logs"
	@echo "   make logs-follow  - Follow logs in real-time"

# Show proxy logs
logs:
	@echo "📜 Proxy logs (last 50 lines):"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@docker-compose -f docker-compose.vertex-claude.yml logs --tail=50 litellm-proxy

# Show ngrok logs
logs-ngrok:
	@echo "📜 Ngrok logs:"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@docker-compose -f docker-compose.vertex-claude.yml logs ngrok

# Follow logs in real-time
logs-follow:
	@docker-compose -f docker-compose.vertex-claude.yml logs -f

# Watch proxy logs with intelligent parsing (recommended)
logs-watch:
	@echo "🔍 Starting intelligent log watcher..."
	@python3 parse_proxy_logs.py

# Search logs for specific pattern
logs-search:
	@if [ -z "$(pattern)" ]; then \
		echo "Usage: make logs-search pattern=\"your search term\""; \
		echo "Example: make logs-search pattern=\"thinking\""; \
	else \
		docker-compose -f docker-compose.vertex-claude.yml logs litellm-proxy | grep -i "$(pattern)"; \
	fi

# ====================
# 📝 ORIGINAL COMMANDS (kept for manual control)
# ====================

# Run the proxy with Vertex AI Claude config
proxy-vertex:
	@echo "Starting LiteLLM proxy for Vertex AI Claude on port $(PROXY_PORT)..."
	poetry run litellm --config $(PROXY_CONFIG) --port $(PROXY_PORT)

# Run the proxy with debug logging
proxy-vertex-debug:
	@echo "Starting LiteLLM proxy for Vertex AI Claude on port $(PROXY_PORT) with debug logging..."
	poetry run litellm --config $(PROXY_CONFIG) --port $(PROXY_PORT) --detailed_debug

# Start ngrok and display the URL
ngrok:
	@echo "Starting ngrok tunnel on port $(NGROK_PORT)..."
	@echo "Press Ctrl+C to stop ngrok"
	ngrok http $(NGROK_PORT)

# Get ngrok URL (requires ngrok to be running with API enabled)
ngrok-url:
	@echo "Fetching ngrok public URL..."
	@curl -s http://localhost:4040/api/tunnels | python3 -c "import sys, json; tunnels=json.load(sys.stdin)['tunnels']; print(tunnels[0]['public_url'] if tunnels else 'No tunnels found. Is ngrok running?')" 2>/dev/null || echo "ngrok API not available. Make sure ngrok is running."

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

#------------------------------------------------------------#
# Cloud Deployment (GCE VM)
#------------------------------------------------------------#

init-cloud:  ## Initialize GCE VM (one-time setup)
	@echo "🚀 Initializing cloud infrastructure..."
	@echo ""
	@./deploy_vm.sh

deploy:  ## Deploy code updates to cloud VM (preserves PostgreSQL data)
	@echo "🔄 Deploying updates to cloud..."
	@echo ""
	@./update_vm.sh

setup-https:  ## Setup HTTPS with Cloudflare Tunnel (quick & free)
	@echo "🔒 Setting up HTTPS..."
	@echo ""
	@./setup_https.sh