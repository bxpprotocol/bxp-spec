# Developer shortcuts. `make check` runs everything CI runs (except Docker).
.PHONY: install lint test conformance typecheck check run security docs build clean \
        release-dry ci-local generate-vectors openapi openapi-check citation-check \
        validate-spec docs-guard check-dataset pages pages-check feed data-page \
        site-artifacts site site-audit version-bump help

# Where the published website lives, for `make pages`.
PAGES_OUT ?= ../bxpprotocol.github.io

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
	@$(MAKE) docs-guard
	@$(MAKE) validate-spec
	@$(MAKE) openapi-check
	@$(MAKE) build
	@echo ""
	@echo "ci-local complete. Also run 'make pages && make feed && make site-audit'"
	@echo "to refresh and verify the website, then push bxp-spec and bxpprotocol.github.io."

generate-vectors:   ## Regenerate conformance golden vectors
	$(PYTHON) conformance/generate_vectors.py

openapi:            ## Regenerate the committed OpenAPI contract
	$(PYTHON) scripts/export_openapi.py

openapi-check:      ## Fail if the committed OpenAPI contract is stale
	@$(PYTHON) scripts/export_openapi.py >/dev/null
	@git diff --quiet -- openapi.json openapi.yaml \
		&& echo "openapi contract up to date" \
		|| (echo "openapi.json/openapi.yaml are stale - run 'make openapi' and commit" && exit 1)

citation-check:     ## Validate CITATION.cff and the version references agree
	@$(PYTHON) scripts/check_docs.py

check-dataset:      ## Validate the published sample dataset against the SDK validator
	@$(PYTHON) scripts/check_dataset.py

validate-spec:      ## Validate SPEC.md structure, TOC, and internal anchors
	@grep -q "^# BXP Technical Specification" SPEC.md
	@$(PYTHON) scripts/build_spec_toc.py --check
	@$(PYTHON) scripts/check_anchors.py SPEC.md README.md CHANGELOG.md CONTRIBUTING.md SECURITY.md
	@test $$(ls conformance/vectors/*.bxp | wc -l) -eq 17 && echo "✓ 17 conformance vectors"

docs-guard:         ## Fence balance, version agreement, HRI labelling, anchors
	@$(PYTHON) scripts/check_docs.py
	@$(PYTHON) scripts/check_anchors.py SPEC.md README.md CHANGELOG.md CONTRIBUTING.md SECURITY.md docs/api_documentation.md docs/developer_guide.md

pages:              ## Regenerate the website reference pages from source
	@$(PYTHON) scripts/build_reference_pages.py --out $(PAGES_OUT)

pages-check:        ## Fail if the website reference pages are stale
	@$(PYTHON) scripts/build_reference_pages.py --out $(PAGES_OUT) >/dev/null
	@git diff --quiet -- '*.html' \
		&& echo "reference pages up to date" \
		|| (echo "reference pages are stale - run 'make pages' and commit" && exit 1)

feed:               ## Regenerate the release Atom feed
	@$(PYTHON) scripts/build_feed.py --out $(PAGES_OUT)

data-page:          ## Regenerate the sample-dataset page
	@$(PYTHON) scripts/build_data_page.py --out $(PAGES_OUT)

site-artifacts:     ## Copy openapi, dataset, postman, llms-full, .nojekyll to the site
	@$(PYTHON) scripts/build_site_artifacts.py --out $(PAGES_OUT)

site:               ## Regenerate everything published to the website
	@$(MAKE) pages
	@$(MAKE) data-page
	@$(MAKE) feed
	@$(MAKE) site-artifacts
	@echo ""
	@echo "Website regenerated. Run 'make site-audit' before committing."

site-audit:         ## Check published site for dead links and missing metadata
	@$(PYTHON) scripts/audit_site.py

version-bump:       ## Show current version from git tags
	@git describe --tags --abbrev=0 2>/dev/null || echo "v0.0.0 (no tags)"

help:               ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'