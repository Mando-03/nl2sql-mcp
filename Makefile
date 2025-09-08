# Default shell for recipes
SHELL := /bin/sh

# Project variables (override via environment or CLI, e.g., `make publish RESOURCE_GROUP=rg-name`)
APP_NAME ?= jb-demo-nl2sql-mcp
RESOURCE_GROUP ?=
LOCATION ?=
ENVIRONMENT ?=
AZ_SUBSCRIPTION ?=
INGRESS ?= external
TARGET_PORT ?= 8000
ENV_FILE ?= .env

# Container build variables
IMAGE_NAME ?= $(APP_NAME)
IMAGE_TAG ?= local
DOCKERFILE ?= Dockerfile
BUILD_CONTEXT ?= .
HOST_PORT ?= 8000
CONTAINER_NAME ?= $(IMAGE_NAME)

# Always use `uv run` when invoking Python tooling
UV := uv run

.DEFAULT_GOAL := help

.PHONY: help
help: ## Show available make targets
	@printf "\nTargets:\n"
	@awk 'BEGIN {FS":.*##"; OFS="\t"} /^[a-zA-Z0-9_.-]+:.*##/ {printf "  %-18s %s\n", $$1, $$2}' $(MAKEFILE_LIST) | sort
	@printf "\nVariables (override as needed):\n  APP_NAME=%s\n  RESOURCE_GROUP=%s\n  LOCATION=%s\n  ENVIRONMENT=%s\n  AZ_SUBSCRIPTION=%s\n\n" "$(APP_NAME)" "$(RESOURCE_GROUP)" "$(LOCATION)" "$(ENVIRONMENT)" "$(AZ_SUBSCRIPTION)"

.PHONY: clean
clean: ## Remove caches, build artifacts, virtual env, and transient files
	@echo "Cleaning caches and build artifacts..."
	@find . -type d -name '__pycache__' -prune -exec rm -rf {} +
	@find . -type f \( -name '*.pyc' -o -name '*.pyo' -o -name '*~' \) -delete
	@rm -rf .pytest_cache .ruff_cache .mypy_cache .cache .basedpyright .pytype
	@rm -rf build dist .eggs *.egg-info
	@rm -rf .nox .tox
	@rm -rf .venv .uv
	@rm -rf .coverage* coverage.xml htmlcov
	@find . -name '.DS_Store' -type f -delete
	@rm -rf .mcp_cache data/.cache 2>/dev/null || true
	@echo "Clean complete."

.PHONY: format
format: ## Format code with ruff
	$(UV) ruff format .

.PHONY: lint
lint: ## Lint and auto-fix with ruff
	$(UV) ruff check --fix .

.PHONY: typecheck
typecheck: ## Static type check with basedpyright (strict)
	$(UV) basedpyright

.PHONY: test
test: ## Run test suite
	$(UV) pytest -q

.PHONY: quality
quality: format lint typecheck test ## Run the full Quality Gauntlet

.PHONY: preflight
preflight: ## Verify Azure CLI, extension, login, and (optionally) subscription
	@command -v az >/dev/null 2>&1 || { echo "Azure CLI not found. Install from https://aka.ms/azure-cli"; exit 1; }
	@echo "Checking Azure CLI login..."
	@az account show >/dev/null 2>&1 || { echo "Not logged in to Azure. Run: az login"; exit 1; }
	@if [ -n "$(AZ_SUBSCRIPTION)" ]; then \
		echo "Setting subscription: $(AZ_SUBSCRIPTION)"; \
		az account set --subscription "$(AZ_SUBSCRIPTION)"; \
	fi

.PHONY: publish
publish: preflight ## Build from source and deploy with Azure Container Apps
	@echo "Publishing Container App '$(APP_NAME)' from source with ingress $(INGRESS):$(TARGET_PORT)..."
	@az containerapp up -n "$(APP_NAME)" --source . \
		--ingress "$(INGRESS)" --target-port "$(TARGET_PORT)" \
		$(if $(RESOURCE_GROUP),--resource-group "$(RESOURCE_GROUP)",) \
		$(if $(ENVIRONMENT),--environment "$(ENVIRONMENT)",) \
		$(if $(LOCATION),--location "$(LOCATION)",) \
		$(if $(ENV_ARGS),--env-vars $(ENV_ARGS),)
	@echo "Publish complete."

.PHONY: docker
docker: ## Build a local Docker image (tag: $(IMAGE_NAME):$(IMAGE_TAG))
	@echo "Building Docker image '$(IMAGE_NAME):$(IMAGE_TAG)' using $(DOCKERFILE) ..."
	@DOCKER_BUILDKIT=1 docker build -t "$(IMAGE_NAME):$(IMAGE_TAG)" -f "$(DOCKERFILE)" "$(BUILD_CONTEXT)"
	@echo "Image built: $(IMAGE_NAME):$(IMAGE_TAG)"

.PHONY: docker-run
docker-run: ## Run local image with env and port mapping
	@echo "Running Docker image '$(IMAGE_NAME):$(IMAGE_TAG)' as container '$(CONTAINER_NAME)' ..."
	@docker run --rm -it \
		--name "$(CONTAINER_NAME)" \
		--env-file "$(ENV_FILE)" \
		-p "$(HOST_PORT):$(TARGET_PORT)" \
		"$(IMAGE_NAME):$(IMAGE_TAG)"
