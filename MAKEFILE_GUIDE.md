# 🛠️ Guia do Makefile - SimplificaPsi

## 🚀 Comandos Principais

### **Desenvolvimento Rápido**

```bash
# Início rápido - build, start, test tudo de uma vez
make quick-start

# Iniciar todos os serviços
make start

# Parar todos os serviços
make stop

# Reiniciar todos os serviços
make restart

# Verificar saúde de todos os serviços
make health
```

### **Testes**

```bash
# Executar todos os testes
make test

# Testar apenas FASE 4 (Gestão de clientes)
make test-phase4

# Testar apenas FASE 2 (Banco de dados)
make test-phase2

# Testar API FastAPI
make test-api

# Testar banco de dados
make test-db

# Testar Redis
make test-redis

# Executar suite completa de testes
make test-all
```

### **Desenvolvimento**

```bash
# Iniciar em modo desenvolvimento (com Docker)
make dev

# Iniciar com debug
make dev-debug

# Iniciar apenas a API
make api

# Ver logs da aplicação
make logs

# Ver logs do banco
make logs-db

# Ver logs do Redis
make logs-redis

# Ver todos os logs
make logs-all
```

### **Banco de Dados**

```bash
# Aplicar migrações
make db-upgrade

# Criar nova migração
make db-migration MESSAGE="descrição da migração"

# Reverter migrações
make db-downgrade

# Resetar banco
make db-reset

# Acessar shell do banco
make db-shell

# Listar tabelas
make db-tables

# Verificar status do banco
make db-status
```

### **Docker**

```bash
# Build da aplicação
make docker-build

# Ver status dos containers
make docker-status

# Acessar shell da aplicação
make docker-shell

# Acessar shell do banco
make docker-shell-db

# Acessar shell do Redis
make docker-shell-redis

# Limpar containers e volumes
make docker-clean
```

### **Qualidade de Código**

```bash
# Verificar formatação
make format-check

# Formatar código
make format

# Linting
make lint

# Verificar tudo (format + lint + test)
make check

# Executar pre-commit
make pre-commit
```

### **Utilitários**

```bash
# Ver status do projeto
make status

# Ver dependências
make deps

# Ver árvore de dependências
make deps-tree

# Limpar arquivos temporários
make clean

# Acessar shell Python
make shell
```

## 🎯 Fluxo de Desenvolvimento Recomendado

### **1. Primeira vez no projeto:**

```bash
make quick-start
```

### **2. Desenvolvimento diário:**

```bash
# Iniciar serviços
make start

# Verificar se está tudo funcionando
make health

# Fazer alterações no código...

# Testar alterações
make test-phase4

# Ver logs se necessário
make logs
```

### **3. Antes de fazer commit:**

```bash
# Verificar qualidade do código
make check

# Executar todos os testes
make test-all
```

### **4. Debugging:**

```bash
# Ver logs específicos
make logs-app

# Acessar shell da aplicação
make docker-shell

# Acessar banco de dados
make db-shell
```

## 🔧 Comandos Específicos do SimplificaPsi

### **Testes por Fase:**

- `make test-phase2` - Testa banco de dados e infraestrutura
- `make test-phase4` - Testa gestão de clientes
- `make test-api` - Testa API FastAPI
- `make test-all` - Executa todos os testes

### **Funcionalidades de Cliente:**

- `make client-test` - Testa funcionalidades de cliente
- `make test-phase4` - Testa schemas, serviços e agentes de cliente

### **Monitoramento:**

- `make health` - Verifica saúde de todos os serviços
- `make status` - Mostra status completo do projeto
- `make docker-status` - Status dos containers Docker

## 📊 Exemplos de Uso

### **Desenvolvimento de nova feature:**

```bash
# 1. Iniciar ambiente
make start

# 2. Verificar se está funcionando
make health

# 3. Desenvolver feature...

# 4. Testar
make test-phase4

# 5. Ver logs se necessário
make logs-app
```

### **Debug de problema:**

```bash
# 1. Ver status geral
make status

# 2. Verificar saúde
make health

# 3. Ver logs específicos
make logs-app

# 4. Acessar shell se necessário
make docker-shell
```

### **Preparação para commit:**

```bash
# 1. Verificar formatação
make format-check

# 2. Executar linting
make lint

# 3. Executar todos os testes
make test-all

# 4. Se tudo OK, fazer commit
```

## 🎉 Comandos Mais Usados

| Comando            | Descrição                    | Uso Frequente |
| ------------------ | ---------------------------- | ------------- |
| `make start`       | Iniciar todos os serviços    | ⭐⭐⭐⭐⭐    |
| `make stop`        | Parar todos os serviços      | ⭐⭐⭐⭐⭐    |
| `make test-phase4` | Testar gestão de clientes    | ⭐⭐⭐⭐⭐    |
| `make health`      | Verificar saúde dos serviços | ⭐⭐⭐⭐      |
| `make logs`        | Ver logs da aplicação        | ⭐⭐⭐⭐      |
| `make status`      | Status do projeto            | ⭐⭐⭐        |
| `make quick-start` | Início rápido completo       | ⭐⭐⭐        |

## 🚨 Troubleshooting

### **Se os containers não iniciarem:**

```bash
make docker-clean
make docker-build
make start
```

### **Se os testes falharem:**

```bash
make health
make test-db
make test-redis
make test-api
```

### **Se a API não responder:**

```bash
make logs-app
make docker-shell
# Dentro do container: uv run python -c "from app.main import app"
```

---

**🎯 Com o Makefile, você tem controle total sobre o SimplificaPsi com comandos simples e intuitivos!**
