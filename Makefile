# heyspace-discord — common commands.
# Usage: make <target> [m="migration message"]
#
# Examples:
#   make up
#   make logs
#   make migration m="add course thumbnail"
#   make upgrade

COMPOSE := docker compose
BOT     := $(COMPOSE) run --rm bot

# Postgres creds (override on the CLI or via .env if you changed them).
PG_USER ?= postgres
PG_DB   ?= heyspace

.DEFAULT_GOAL := help

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

# --- lifecycle ---------------------------------------------------------------

.PHONY: build
build: ## Build (or rebuild) the bot image
	$(COMPOSE) build bot

.PHONY: up
up: ## Start db + bot in the background (rebuilds if needed)
	$(COMPOSE) up -d --build

.PHONY: down
down: ## Stop and remove containers
	$(COMPOSE) down

.PHONY: restart
restart: ## Recreate the bot with current code (picks up bot.py / lib / config changes)
	$(COMPOSE) up -d --force-recreate bot

.PHONY: logs
logs: ## Follow the bot logs
	$(COMPOSE) logs -f bot

.PHONY: ps
ps: ## Show container status
	$(COMPOSE) ps

# --- database / migrations ---------------------------------------------------

.PHONY: migration
migration: ## Autogenerate a migration:  make migration m="message"
ifndef m
	$(error Provide a message: make migration m="describe change")
endif
	$(BOT) alembic revision --autogenerate -m "$(m)"

.PHONY: upgrade
upgrade: ## Apply all pending migrations
	$(BOT) alembic upgrade head

.PHONY: downgrade
downgrade: ## Roll back the most recent migration
	$(BOT) alembic downgrade -1

.PHONY: history
history: ## Show migration history
	$(BOT) alembic history --indicate-current

.PHONY: psql
psql: ## Open a psql shell in the db container
	$(COMPOSE) exec db psql -U $(PG_USER) -d $(PG_DB)

# --- dev ---------------------------------------------------------------------

.PHONY: shell
shell: ## Open a shell in a throwaway bot container
	$(BOT) bash

# ruff is a dev-only dependency (not in the image), so run it locally via Poetry.
.PHONY: lint
lint: ## Lint with ruff (local: poetry install first)
	poetry run ruff check src

.PHONY: format
format: ## Format with ruff (local: poetry install first)
	poetry run ruff format src
