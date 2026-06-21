# =============================================================================
# SIMPLIFICAPSI - MAKEFILE
# =============================================================================

.PHONY: help setup install dev test lint format clean build docker-up docker-down docker-build docker-logs

# =============================================================================
# VARIABLES
# =============================================================================
PYTHON := python3.11
UV := uv
DOCKER_COMPOSE := docker compose
DOCKER := docker
API_PORT := 8000
API_PREFIX := /api/v1
DEV_USER_ID := 550e8400-e29b-41d4-a716-446655440000

# =============================================================================
# HELP
# =============================================================================
help: ## Show this help message
	@echo "SimplificaPsi - Sistema de Agentes AI"
	@echo "====================================="
	@echo ""
	@echo "Available commands:"
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# =============================================================================
# SETUP & INSTALLATION
# =============================================================================
setup: ## Setup inicial do projeto com uv
	@echo "🚀 Setting up SimplificaPsi project..."
	@$(UV) sync
	@$(UV) run pre-commit install
	@echo "✅ Setup completed!"

install: ## Instalar dependências com uv sync
	@echo "📦 Installing dependencies..."
	@$(UV) sync
	@echo "✅ Dependencies installed!"

add: ## Adicionar dependência (usage: make add PACKAGE=package_name)
	@echo "➕ Adding package: $(PACKAGE)"
	@$(UV) add $(PACKAGE)
	@echo "✅ Package added!"

add-dev: ## Adicionar dependência de desenvolvimento (usage: make add-dev PACKAGE=package_name)
	@echo "➕ Adding dev package: $(PACKAGE)"
	@$(UV) add --dev $(PACKAGE)
	@echo "✅ Dev package added!"

remove: ## Remover dependência (usage: make remove PACKAGE=package_name)
	@echo "➖ Removing package: $(PACKAGE)"
	@$(UV) remove $(PACKAGE)
	@echo "✅ Package removed!"

# =============================================================================
# DEVELOPMENT
# =============================================================================
dev: ## Rodar em modo desenvolvimento com Docker
	@echo "🔥 Starting development server with Docker..."
	@$(DOCKER_COMPOSE) up -d
	@echo "✅ Services started! API available at http://localhost:8000"
	@echo "📋 Use 'make logs' to see logs or 'make stop' to stop services"

dev-debug: ## Rodar em modo desenvolvimento com debug
	@echo "🐛 Starting development server with debug..."
	@$(DOCKER_COMPOSE) up -d
	@$(DOCKER_COMPOSE) exec app uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 --log-level debug

start: ## Iniciar todos os serviços
	@echo "🚀 Starting all services..."
	@$(DOCKER_COMPOSE) up -d
	@echo "✅ All services started!"

stop: ## Parar todos os serviços
	@echo "🛑 Stopping all services..."
	@$(DOCKER_COMPOSE) down
	@echo "✅ All services stopped!"

restart: ## Reiniciar todos os serviços
	@echo "🔄 Restarting all services..."
	@$(DOCKER_COMPOSE) down
	@$(DOCKER_COMPOSE) up -d
	@echo "✅ All services restarted!"

# =============================================================================
# LOCAL DEV (infra no Docker, app rodando local com uv — melhor p/ debugar o agente)
# =============================================================================
infra: ## Subir APENAS postgres + redis (sem app)
	@echo "🧱 Starting infra (postgres + redis)..."
	@$(DOCKER_COMPOSE) up -d postgres redis
	@echo "✅ Infra up. Postgres:5432  Redis:6379"

infra-stop: ## Parar a infra
	@$(DOCKER_COMPOSE) stop postgres redis

migrate: ## Aplicar migrações Alembic (local, contra a infra)
	@echo "🗄️ Applying migrations..."
	@$(UV) run alembic upgrade head

seed: ## Semear o usuário de dev fixo
	@echo "🌱 Seeding dev user..."
	@$(UV) run python scripts/seed_dev.py

run: ## Rodar a API localmente com reload
	@echo "🚀 uvicorn local em http://localhost:$(API_PORT)"
	@$(UV) run uvicorn app.main:app --host 0.0.0.0 --port $(API_PORT) --reload

bootstrap: ## Setup completo p/ dev local: infra + migrate + seed
	@make infra
	@sleep 3
	@make migrate
	@make seed
	@echo "🎉 Pronto. Rode 'make run' e depois 'make chat MSG=\"oi\"'."

chat: ## Enviar uma mensagem ao agente (usage: make chat MSG="cadastra a Maria Silva, ...")
	@curl -s -X POST http://localhost:$(API_PORT)$(API_PREFIX)/agent/message \
		-H "Content-Type: application/json" \
		-d '{"user_id": "$(DEV_USER_ID)", "message": "$(MSG)"}' | python3 -m json.tool

psql: ## Shell psql na infra
	@$(DOCKER_COMPOSE) exec postgres psql -U simplificapsi -d simplificapsi_dev

redis: ## redis-cli na infra
	@$(DOCKER_COMPOSE) exec redis redis-cli

# =============================================================================
# TESTING (pytest local via uv)
# =============================================================================
test: ## Executar toda a suíte (unit + integration)
	@echo "🧪 Running pytest..."
	@$(UV) run pytest

test-unit: ## Apenas testes unitários
	@$(UV) run pytest tests/unit/ -v

test-integration: ## Apenas testes de integração
	@$(UV) run pytest tests/integration/ -v

test-cov: ## Testes com cobertura (HTML + terminal)
	@$(UV) run pytest --cov=app --cov-report=html --cov-report=term -v

test-db: ## Testar conexão com o banco
	@$(DOCKER_COMPOSE) exec postgres psql -U simplificapsi -d simplificapsi_dev -c "SELECT 'Database connected!' as status;"

test-redis: ## Testar conexão com Redis
	@$(DOCKER_COMPOSE) exec redis redis-cli ping

# =============================================================================
# CODE QUALITY
# =============================================================================
lint: ## Linting e formatação
	@echo "🔍 Running linting..."
	@$(UV) run ruff check app/ tests/
	@$(UV) run mypy app/

format: ## Formatar código
	@echo "🎨 Formatting code..."
	@$(UV) run black app/ tests/
	@$(UV) run ruff format app/ tests/
	@$(UV) run isort app/ tests/

format-check: ## Verificar formatação sem alterar
	@echo "🔍 Checking code format..."
	@$(UV) run black --check app/ tests/
	@$(UV) run ruff format --check app/ tests/
	@$(UV) run isort --check-only app/ tests/

# =============================================================================
# DATABASE
# =============================================================================
db-upgrade: ## Aplicar migrações do banco
	@echo "🗄️ Upgrading database..."
	@$(DOCKER_COMPOSE) exec app uv run alembic upgrade head

db-downgrade: ## Reverter migrações do banco
	@echo "🗄️ Downgrading database..."
	@$(DOCKER_COMPOSE) exec app uv run alembic downgrade -1

db-migration: ## Criar nova migração (usage: make db-migration MESSAGE="description")
	@echo "🗄️ Creating migration: $(MESSAGE)"
	@$(DOCKER_COMPOSE) exec app uv run alembic revision --autogenerate -m "$(MESSAGE)"

db-reset: ## Resetar banco de dados
	@echo "🗄️ Resetting database..."
	@$(DOCKER_COMPOSE) exec app uv run alembic downgrade base
	@$(DOCKER_COMPOSE) exec app uv run alembic upgrade head

db-shell: ## Acessar shell do banco de dados
	@echo "🗄️ Accessing database shell..."
	@$(DOCKER_COMPOSE) exec postgres psql -U simplificapsi -d simplificapsi_dev

db-tables: ## Listar tabelas do banco
	@echo "🗄️ Listing database tables..."
	@$(DOCKER_COMPOSE) exec postgres psql -U simplificapsi -d simplificapsi_dev -c "\dt simplificapsi.*"

db-status: ## Verificar status do banco
	@echo "🗄️ Checking database status..."
	@$(DOCKER_COMPOSE) exec postgres psql -U simplificapsi -d simplificapsi_dev -c "SELECT 'Database is healthy!' as status;"

# =============================================================================
# DOCKER
# =============================================================================
docker-up: ## Subir containers Docker
	@echo "🐳 Starting Docker containers..."
	@$(DOCKER_COMPOSE) up -d

docker-down: ## Parar containers Docker
	@echo "🐳 Stopping Docker containers..."
	@$(DOCKER_COMPOSE) down

docker-build: ## Build da aplicação
	@echo "🐳 Building Docker image..."
	@$(DOCKER_COMPOSE) build app

docker-logs: ## Ver logs dos containers
	@echo "🐳 Showing Docker logs..."
	@$(DOCKER_COMPOSE) logs -f

docker-logs-app: ## Ver logs apenas da aplicação
	@echo "🐳 Showing app logs..."
	@$(DOCKER_COMPOSE) logs -f app

docker-shell: ## Acessar shell do container da aplicação
	@echo "🐳 Accessing app container shell..."
	@$(DOCKER_COMPOSE) exec app bash

docker-shell-db: ## Acessar shell do banco de dados
	@echo "🐳 Accessing database shell..."
	@$(DOCKER_COMPOSE) exec postgres psql -U simplificapsi -d simplificapsi_dev

docker-shell-redis: ## Acessar shell do Redis
	@echo "🐳 Accessing Redis shell..."
	@$(DOCKER_COMPOSE) exec redis redis-cli

docker-status: ## Verificar status dos containers
	@echo "🐳 Docker containers status:"
	@$(DOCKER_COMPOSE) ps

docker-clean: ## Limpar containers e volumes
	@echo "🐳 Cleaning Docker containers and volumes..."
	@$(DOCKER_COMPOSE) down -v
	@$(DOCKER) system prune -f
	@echo "✅ Docker cleanup completed!"

# =============================================================================
# PRODUCTION
# =============================================================================
build: ## Build da aplicação
	@echo "🏗️ Building application..."
	@$(UV) run python -m build

build-prod: ## Build para produção
	@echo "🏗️ Building for production..."
	@$(DOCKER_COMPOSE) -f docker-compose.prod.yml build

deploy: ## Deploy para produção
	@echo "🚀 Deploying to production..."
	@$(DOCKER_COMPOSE) -f docker-compose.prod.yml up -d

# =============================================================================
# UTILITIES
# =============================================================================
clean: ## Limpeza de arquivos temporários
	@echo "🧹 Cleaning temporary files..."
	@find . -type f -name "*.pyc" -delete
	@find . -type d -name "__pycache__" -delete
	@find . -type d -name "*.egg-info" -exec rm -rf {} +
	@find . -type f -name ".coverage" -delete
	@find . -type d -name "htmlcov" -exec rm -rf {} +
	@find . -type d -name ".pytest_cache" -exec rm -rf {} +
	@find . -type d -name ".mypy_cache" -exec rm -rf {} +
	@echo "✅ Cleanup completed!"

logs: ## Ver logs da aplicação
	@echo "📋 Showing application logs..."
	@$(DOCKER_COMPOSE) logs -f app

logs-db: ## Ver logs do banco de dados
	@echo "📋 Showing database logs..."
	@$(DOCKER_COMPOSE) logs -f postgres

logs-redis: ## Ver logs do Redis
	@echo "📋 Showing Redis logs..."
	@$(DOCKER_COMPOSE) logs -f redis

logs-all: ## Ver logs de todos os serviços
	@echo "📋 Showing all logs..."
	@$(DOCKER_COMPOSE) logs -f

shell: ## Acessar shell Python
	@echo "🐍 Starting Python shell..."
	@$(UV) run python

check: ## Verificar tudo (lint, format, test)
	@echo "🔍 Running all checks..."
	@make format-check
	@make lint
	@make test

pre-commit: ## Executar pre-commit em todos os arquivos
	@echo "🔍 Running pre-commit on all files..."
	@$(UV) run pre-commit run --all-files

# =============================================================================
# SIMPLIFICAPSI SPECIFIC
# =============================================================================
health: ## Verificar saúde de todos os serviços
	@echo "🏥 Checking SimplificaPsi health..."
	@echo "=================================="
	@echo "🐳 Docker containers:"
	@$(DOCKER_COMPOSE) ps
	@echo ""
	@echo "🌐 API Health:"
	@curl -s http://localhost:8000/health || echo "❌ API not responding"
	@echo ""
	@echo "🗄️ Database Health:"
	@$(DOCKER_COMPOSE) exec postgres psql -U simplificapsi -d simplificapsi_dev -c "SELECT 'Database OK' as status;" 2>/dev/null || echo "❌ Database not responding"
	@echo ""
	@echo "🔴 Redis Health:"
	@$(DOCKER_COMPOSE) exec redis redis-cli ping 2>/dev/null || echo "❌ Redis not responding"
	@echo "✅ Health check completed!"

api: ## Iniciar apenas a API (sem outros serviços)
	@echo "🚀 Starting API only..."
	@$(DOCKER_COMPOSE) up -d postgres redis
	@$(DOCKER_COMPOSE) exec app uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

quick-start: ## Início rápido (dev local): bootstrap + testes
	@echo "⚡ Quick start - SimplificaPsi..."
	@make bootstrap
	@make test
	@echo "🎉 Quick start completed! Rode 'make run'."

# =============================================================================
# DEVELOPMENT HELPERS
# =============================================================================
status: ## Mostrar status do projeto
	@echo "📊 SimplificaPsi Project Status:"
	@echo "================================"
	@echo "Python version: $$($(PYTHON) --version)"
	@echo "UV version: $$($(UV) --version)"
	@echo "Docker version: $$($(DOCKER) --version)"
	@echo "Docker Compose version: $$($(DOCKER_COMPOSE) --version)"
	@echo ""
	@echo "Docker containers:"
	@$(DOCKER_COMPOSE) ps
	@echo ""
	@echo "Git status:"
	@git status --short
	@echo ""
	@echo "API status:"
	@curl -s http://localhost:8000/health 2>/dev/null || echo "API not running"

deps: ## Mostrar dependências
	@echo "📦 Project Dependencies:"
	@echo "========================"
	@$(UV) show

deps-tree: ## Mostrar árvore de dependências
	@echo "🌳 Dependency Tree:"
	@echo "==================="
	@$(UV) tree

# =============================================================================
# DEFAULT TARGET
# =============================================================================
.DEFAULT_GOAL := help
