SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help

UV      ?= uv
PY      := $(UV) run --frozen python
PYTEST  := $(UV) run --frozen pytest
RUFF    := $(UV) run --frozen ruff
PYRIGHT := $(UV) run --frozen pyright
COMPOSE := docker compose -f deploy/compose.dev.yaml -p skm-dev

# Each xdist worker imports the suite and retains its own schema/AST caches.
# Bound the defaults on shared development hosts; override per invocation.
TEST_WORKERS ?= 4
ARCH_WORKERS ?= 2
PG_WORKERS   ?= 8
E2E_WORKERS  ?= 4
WEB_TEST_WORKERS ?= 4
PROJECTED_HOOK_TESTS := tests/e2e/test_projected_hooks.py
SHUTDOWN_TIMING_TEST := tests/e2e/test_local_lifecycle_shutdown.py::test_serve_cancels_blocked_request_at_grace_deadline

export SKM_DATABASE_URL      ?= postgresql://skm:skm_dev@127.0.0.1:54329/skm_dev
export SKM_TEST_DATABASE_URL ?= postgresql://skm:skm_dev@127.0.0.1:54329/skm_test
export HYPOTHESIS_PROFILE ?= dev

.PHONY: help sync fmt fmt-check lint typecheck arch docs-check test test-affected test-pg test-all e2e evals perf check check-touched check-trailers source-index \
        gen sql-check schema-check schema-lock check-skills web-check web-dev web-build db-up db-down db-reset db-psql db-snapshot doctor

help:  ## list currently defined targets
	@awk -F':.*## ' '/^[a-z-]+:.*## / {printf "  %-14s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

sync:  ## install the locked environment
	$(UV) sync --frozen

fmt:  ## format and autofix
	$(RUFF) format src tests tools
	$(RUFF) check --fix src tests tools

fmt-check:  ## formatting is clean
	$(RUFF) format --check src tests tools

lint:  ## ruff without fixes
	$(RUFF) check src tests tools

typecheck:  ## strict source, basic tests, standard tools
	$(PYRIGHT)
	$(PYRIGHT) --project tools/pyrightconfig.json

arch:  ## architecture rules and fixtures
	$(PYTEST) -q -n $(ARCH_WORKERS) --dist loadfile tests/architecture

test:  ## unit and contract tests without external services
	$(PYTEST) -q -n $(TEST_WORKERS) --dist worksteal --timeout 60 --timeout-method signal -o faulthandler_timeout=60 -m "not pg and not e2e and not evals and not perf" --ignore=tests/architecture

test-affected:  ## local unit and contract subset for changed modules
	$(PY) tools/affected_tests.py --workers $(TEST_WORKERS) --arch-workers $(ARCH_WORKERS) --uv "$(UV)" $(AFFECTED_ARGS)

test-pg:  ## PostgreSQL tests (no tests means failure)
	# Keep the native hook and graceful shutdown deadlines free of xdist contention.
	$(PYTEST) -q -n 0 -m "pg and not perf and not evals" $(PROJECTED_HOOK_TESTS) $(SHUTDOWN_TIMING_TEST)
	$(PYTEST) -q -n $(PG_WORKERS) --dist worksteal -m "pg and not perf and not evals" \
		--ignore=$(PROJECTED_HOOK_TESTS) --deselect=$(SHUTDOWN_TIMING_TEST)

test-all: test test-pg  ## memory and PostgreSQL tests

e2e:  ## Python and Chromium end-to-end scenarios
	# Match the deadline checks used by test-pg.
	$(PYTEST) -q -n 0 -m e2e $(PROJECTED_HOOK_TESTS) $(SHUTDOWN_TIMING_TEST)
	$(PYTEST) -q -n $(E2E_WORKERS) --dist worksteal -m e2e \
		--ignore=$(PROJECTED_HOOK_TESTS) --deselect=$(SHUTDOWN_TIMING_TEST)
	npm --prefix web run e2e

evals:  ## live paid runtime evaluations
	SKM_EVALS=1 $(PYTEST) -q -n 0 tests/evals -m evals --evals-max-usd="$${SKM_EVALS_MAX_USD:-0.50}"

perf:  ## performance measurements
	$(PYTEST) -q -m perf

docs-check:  ## local Markdown files and heading anchors
	$(PY) tools/check_links.py docs README.md

check-skills:  ## skill manifests: roles, SKILL.md, and requires closure
	$(PY) tools/check_skills.py

check: fmt-check lint typecheck test arch docs-check sql-check schema-check check-skills  ## checks available after P01.05.b

check-touched:  ## local diff preflight; affected behavioral tests remain required
	$(PY) tools/check_touched.py

check-trailers:  ## validate published SKM integration commits (TRAILER_REV defaults to HEAD)
	$(PY) tools/check_trailers.py -- $(if $(TRAILER_REV),"$(TRAILER_REV)",HEAD)

source-index:  ## regenerate docs/reference/source-index.md (package map with importing tests)
	$(PY) tools/source_index.py --write

db-up:  ## start dev PostgreSQL and wait for its healthcheck
	$(COMPOSE) up -d --wait

db-down:  ## stop dev PostgreSQL, keeping its named volume
	$(COMPOSE) down

db-reset:  ## recreate only skm_dev and skm_test, including pgcrypto
	$(COMPOSE) exec -T postgres psql -X -U skm -d postgres -v ON_ERROR_STOP=1 \
	  -c "DROP DATABASE IF EXISTS skm_dev WITH (FORCE)" \
	  -c "DROP DATABASE IF EXISTS skm_test WITH (FORCE)" \
	  -f /docker-entrypoint-initdb.d/01-databases.sql

db-psql:  ## psql into the compose's skm_dev database
	$(COMPOSE) exec postgres psql -X -U skm -d skm_dev

db-snapshot:  ## rewrite migrations/schema.snapshot.sql from the fully migrated skm_dev
	$(UV) run --frozen skm db snapshot --write --database-url "$(SKM_DATABASE_URL)"

doctor:  ## development environment checks
	$(PY) tools/doctor.py

gen:  ## generate Python and TypeScript contracts from schemas
	$(PY) tools/gen.py

sql-check:  ## check packaged migration numbering and transaction hygiene offline
	$(PY) tools/check_sql.py

schema-check:  ## generated files and schema compatibility
	$(PY) tools/schema_check.py

schema-lock:  ## update compatible schema snapshots (ALLOW_BREAKING=1 before release only)
	$(PY) tools/schema_check.py --update-lock $(if $(filter 1,$(ALLOW_BREAKING)),--allow-breaking)

web-check:  ## Install, check, and build the web app and verify bundle budgets
	cd web && npm ci --no-audit --no-fund && VITEST_MAX_FORKS=$(WEB_TEST_WORKERS) npm run check && npm run build && npm run budget

web-dev:  ## Run the web development server
	cd web && npm run dev

web-build:  ## Install locked dependencies and build web/dist
	cd web && npm ci --no-audit --no-fund && npm run build
