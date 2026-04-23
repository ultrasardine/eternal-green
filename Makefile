# Eternal-Green Makefile
# Development tasks for the anti-idle application

.PHONY: help install run tray test lint clean icon build dmg dist

# Default target
.DEFAULT_GOAL := help

##@ General

help: ## Display this help message
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make \033[36m<target>\033[0m\n"} /^[a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2 } /^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) } ' $(MAKEFILE_LIST)

##@ Development

install: ## Install project dependencies using UV
	uv sync --all-extras

run: ## Run the eternal-green CLI application
	uv run eternal-green

tray: ## Run the eternal-green system tray application
	uv run eternal-green-tray

##@ Testing

test: ## Run all tests with pytest
	uv run pytest tests/ -v

##@ Code Quality

lint: ## Run code quality checks (ruff)
	uv run ruff check eternal_green/ tests/

##@ Distribution (macOS)

icon: ## Generate macOS .icns app icon
	uv run python scripts/create_icns.py

build: icon ## Build macOS .app bundle with PyInstaller
	uv run pyinstaller eternal_green.spec --noconfirm

dmg: build ## Create distributable DMG from .app bundle
	bash scripts/build_dmg.sh

dist: dmg ## Full distribution build (icon + app + DMG)
	@echo "Distribution complete. Check dist/ for outputs."

##@ Cleanup

clean: ## Remove build artifacts and cache files
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	rm -rf .pytest_cache/
	rm -rf .hypothesis/
	rm -rf __pycache__/
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type f -name "*.pyo" -delete 2>/dev/null || true
