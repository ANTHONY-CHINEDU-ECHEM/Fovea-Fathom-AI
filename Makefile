PY ?= python3
export PYTHONPATH := backend:.

.PHONY: help install install_ml seed serve frontend demo_build ingest ingest_quick ingest_trials build_index \
        test lint format typecheck eval eval_gate eval_live readme_check check up up_local down clean

help:
	@grep -E '^[a-z_]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-14s %s\n", $$1, $$2}'

install: ## Python and interface dependencies
	$(PY) -m pip install -e ".[dev]"
	cd frontend && npm install --no-audit --no-fund

install_ml: ## BGE embeddings, cross encoder, Qdrant and Redis clients
	$(PY) -m pip install -e ".[ml,dev]"

seed: ## Index the verified seed snapshot
	$(PY) -m ingestion.cli seed

serve: ## Run the API on port 8000
	$(PY) -m uvicorn fovea.main:app --reload --port 8000

frontend: ## Run the interface on port 5173
	cd frontend && npm run dev

demo_build: ## Rebuild the standalone browser demo
	$(PY) scripts/build_demo.py

ingest: ## Harvest every source and build the index
	$(PY) -m ingestion.cli run

ingest_quick: ## Capped harvest for development
	$(PY) -m ingestion.cli run --quick

ingest_trials: ## Refresh ClinicalTrials.gov records only
	$(PY) -m ingestion.cli run --only clinicaltrials_gov

build_index: ## Rebuild the index from checkpoints and the seed
	$(PY) -m ingestion.cli build

test: ## Unit, pipeline and API tests
	$(PY) -m pytest

lint: ## Ruff lint and format check
	ruff check . && ruff format --check .

format: ## Apply ruff formatting
	ruff format . && ruff check . --fix

typecheck: ## Mypy and TypeScript
	mypy
	cd frontend && npm run typecheck

eval: ## Offline evaluation report
	$(PY) -m evaluation.harness --offline

eval_gate: ## Offline evaluation with the continuous integration gate
	$(PY) -m evaluation.harness --offline --gate

eval_live: ## Evaluate the live index and configured model
	$(PY) -m evaluation.harness --live

readme_check: ## README style rules
	$(PY) scripts/check_readme_style.py

check: lint typecheck test eval_gate readme_check ## Everything continuous integration runs

up: ## Full stack with Docker
	docker compose up --build -d

up_local: ## Full stack plus a local Ollama model
	docker compose --profile local up --build -d

down:
	docker compose down

clean:
	rm -rf data/index data/raw .pytest_cache .mypy_cache .ruff_cache frontend/dist
