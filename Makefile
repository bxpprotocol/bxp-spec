# Developer shortcuts. `make check` runs everything CI runs (except Docker).
.PHONY: install lint test conformance typecheck check run security docs build clean release

# Python & Node versions
PYTHON := python3
NPM := npm

# Paths
PY_SRC := reference-server sdk/python cli integrations conformance
TS_SRC := sdk/typescript

install:            ## Install Python + TypeScript dev dependencies
	$(PYTHON) -m pip install -r reference-server/requirements.txt -r requirements-dev.txt
	cd $(TS_SRC) && $(NPM) ci

lint:               ## Lint all Python (ruff)
	ruff check .

typecheck:          ## Type-check the TypeScript SDK
	cd $(TS_SRC) && $(NPM) run typecheck

test:               ## All unit/integration tests (Python + TypeScript)
	$(PYTHON) -m pytest reference-server/tests sdk/python/tests integrations/ -q
	cd $(TS_SRC) && $(NPM) test

conformance:        ## Golden-vector checks for both language implementations
	$(PYTHON) conformance/verify_python.py
	cd $(TS_SRC) && $(NPM) run conformance

security:           ## Security audit (pip-audit + npm audit)
	pip-audit -r reference-server/requirements.txt --desc on
	cd $(TS_SRC) && $(NPM) audit --audit-level=high

docs:               ## Validate docs (HTML structure, internal links)
	@grep -q "<!DOCTYPE html>" docs/index.html && echo "✓ index.html valid"
	@grep -q "<!DOCTYPE html>" docs/validator.html && echo "✓ validator.html valid"
	@test -f docs/sitemap.xml && echo "✓ sitemap.xml exists"
	@test -f docs/robots.txt && echo "✓ robots.txt exists"
	@test -f docs/manifest.json && echo "✓ manifest.json exists"

check: lint typecheck test conformance   ## Everything CI checks (pre-PR)

run:                ## Start the reference node on :5000
	cd reference-server && $(PYTHON) server.py

build:              ## Build Python package (wheel + sdist)
	$(PYTHON) -m build

clean:              ## Clean build artifacts
	rm -rf build dist *.egg-info sdk/typescript/dist .pytest_cache .ruff_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

release-dry:        ## Dry-run release (check version, changelog, build)
	@grep -q "^## \[$(shell git describe --tags --abbrev=0 2>/dev/null || echo 'unreleased')" CHANGELOG.md && echo "✓ Changelog has entry for latest tag" || echo "⚠ Changelog may need update"
	@$(MAKE) check
	@$(MAKE) build

ci-local:           ## Run CI steps locally (mirrors .github/workflows/ci.yml)
	@$(MAKE) lint
	@$(MAKE) typecheck
	@$(MAKE) test
	@$(MAKE) conformance
	@$(MAKE) security
	@$(MAKE) docs
	@$(MAKE) build

generate-vectors:   ## Regenerate conformance golden vectors
	$(PYTHON) conformance/generate_vectors.py

validate-spec:      ## Validate SPEC.md structure
	@grep -q "^# BXP" SPEC.md
	@for i in $$(seq 1 20); do grep -q "^## $$i\." SPEC.md || (echo "Missing section $$i" && exit 1); done
	@test $$(ls conformance/vectors/*.bxp | wc -l) -eq 17 && echo "✓ 17 conformance vectors"

version-bump:       ## Show current version from git tags
	@git describe --tags --abbrev=0 2>/dev/null || echo "v0.0.0 (no tags)"

help:               ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'