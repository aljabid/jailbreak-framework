#!/usr/bin/env sh
set -eu

project_root="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$project_root"

UV_CACHE_DIR="${UV_CACHE_DIR:-${TMPDIR:-/tmp}/jbf-uv-cache}"
export UV_CACHE_DIR

.venv/bin/uv lock --check
.venv/bin/ruff check .
.venv/bin/mypy \
    application core domain evaluation models observability persistence \
    policy strategies utils scripts/local_acceptance.py scripts/check_docs.py \
    scripts/import_external_prompts.py main.py
.venv/bin/python -m compileall -q \
    application core domain evaluation models observability persistence \
    policy strategies utils main.py
.venv/bin/bandit -q -ll -r \
    application core domain evaluation models observability persistence \
    policy strategies utils main.py
.venv/bin/pytest tests \
    --cov=application --cov=core --cov=domain --cov=evaluation \
    --cov=models --cov=observability --cov=persistence --cov=policy \
    --cov=strategies --cov=utils \
    --cov-report=term --cov-fail-under=75 -q
.venv/bin/python main.py benchmark-evaluator
.venv/bin/python main.py benchmark-scoring
.venv/bin/python main.py health --profile mock
.venv/bin/python scripts/check_docs.py
.venv/bin/python -m build --no-isolation
docker compose config -q
