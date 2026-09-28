# Developer shortcuts. `make check` runs everything CI runs (except Docker).
.PHONY: install lint test conformance typecheck check run

install:            ## Install Python + TypeScript dev dependencies
	pip install -r reference-server/requirements.txt -r requirements-dev.txt
	cd sdk/typescript && npm ci

lint:               ## Lint all Python
	ruff check .

typecheck:          ## Type-check the TypeScript SDK
	cd sdk/typescript && npm run typecheck

test:               ## All unit/integration tests (Python + TypeScript)
	python -m pytest reference-server/tests sdk/python/tests integrations/tests -q
	cd sdk/typescript && npm test

conformance:        ## Golden-vector checks for both language implementations
	python conformance/verify_python.py
	cd sdk/typescript && npm run conformance

check: lint typecheck test conformance   ## Everything CI checks

run:                ## Start the reference node on :5000
	cd reference-server && python server.py
