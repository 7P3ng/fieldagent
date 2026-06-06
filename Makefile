.PHONY: help test lint typecheck eval-dry eval-live fetch-cuad web-build clean

help:
	@echo "FieldAgent targets:"
	@echo "  make test       - run the unit test suite (no network, no paid calls)"
	@echo "  make lint       - ruff check"
	@echo "  make typecheck  - mypy"
	@echo "  make eval-dry   - reproduce headline tables from committed fixtures (zero cost)"
	@echo "  make eval-live  - LIVE eval (requires FIELDAGENT_LIVE=1 + DeepSeek key; prints cost first)"
	@echo "  make fetch-cuad - download + checksum CUAD_v1.json into evals/benchmark/raw/ (gitignored)"
	@echo "  make web-build  - static-export the demo to web/out"

test:
	.venv/bin/python -m pytest

lint:
	.venv/bin/ruff check core fieldagent evals cli tests

typecheck:
	.venv/bin/mypy core fieldagent evals cli

eval-dry:
	.venv/bin/python evals/run_eval.py --target deepseek

eval-live:
	FIELDAGENT_LIVE=1 .venv/bin/python evals/run_eval.py --target deepseek

fetch-cuad:
	.venv/bin/python evals/benchmark/fetch_cuad.py

web-build:
	cd web && npm run build

clean:
	rm -f *.db traces.db
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
