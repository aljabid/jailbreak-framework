
.PHONY: help install test test-fast lint format security benchmark health build clean run-mock report verify scan-image sbom docs local-acceptance

UV := uv
PYTHON := .venv/bin/python

help:
	@echo ""
	@echo "  LLM Jailbreak Automation Framework"
	@echo ""
	@echo "  make install      Install all dependencies"
	@echo "  make test         Run full test suite with coverage"
	@echo "  make test-fast    Run tests without coverage"
	@echo "  make lint         Run Ruff and MyPy"
	@echo "  make format       Run Ruff formatter"
	@echo "  make security     Run source and dependency security scans"
	@echo "  make benchmark    Run evaluator and scoring quality gates"
	@echo "  make health       Run mock-profile readiness diagnostics"
	@echo "  make build        Build and inspect the wheel"
	@echo "  make verify       Run the complete offline release gate"
	@echo "  make scan-image   Scan the image without networked inventory access"
	@echo "  make sbom         Generate a CycloneDX image SBOM offline"
	@echo "  make docs         Validate maintained documentation"
	@echo "  make local-acceptance  Exercise a loopback Ollama deployment"
	@echo "  make run-mock     Run experiment in mock mode (no API key)"
	@echo "  make report       Generate report from existing results"
	@echo "  make clean        Remove generated files"
	@echo ""

install:
	$(UV) sync --locked --extra dev --extra reporting
	@echo "Dependencies installed"

test:
	$(PYTHON) -m pytest tests/ -v --tb=short \
		--cov=core --cov=strategies --cov=models --cov=utils \
		--cov-report=term-missing \
		--cov-report=html:reports/coverage

test-fast:
	$(PYTHON) -m pytest tests/ -v --tb=short -p no:cov

lint:
	.venv/bin/ruff check .
	.venv/bin/mypy application core domain evaluation models observability \
		persistence policy strategies utils scripts/local_acceptance.py \
		scripts/check_docs.py scripts/import_external_prompts.py main.py
	$(PYTHON) -m compileall -q application core domain evaluation models \
		observability persistence policy strategies utils main.py

format:
	$(PYTHON) -m ruff format application core domain evaluation models \
		observability persistence policy strategies utils tests main.py

security:
	.venv/bin/bandit -r application core domain evaluation models \
		observability persistence policy strategies utils main.py -ll
	.venv/bin/pip-audit --local

benchmark:
	$(PYTHON) main.py benchmark-evaluator
	$(PYTHON) main.py benchmark-scoring

health:
	$(PYTHON) main.py health --profile mock

build:
	$(UV) lock --check
	$(PYTHON) -m build --no-isolation

verify:
	./scripts/verify_release.sh

scan-image:
	./scripts/scan_image.sh jailbreak-framework:readiness

sbom:
	./scripts/generate_sbom.sh jailbreak-framework:readiness

docs:
	$(PYTHON) scripts/check_docs.py

local-acceptance:
	$(PYTHON) scripts/local_acceptance.py

run-mock:
	$(PYTHON) main.py run --mock

run-mock-single:
	$(PYTHON) main.py run --mock --strategy roleplay --count 3

report:
	$(PYTHON) main.py report --format all

list-strategies:
	$(PYTHON) main.py list-strategies

test-connection:
	$(PYTHON) main.py test-connection --mock

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	find . -name "*.pyo" -delete 2>/dev/null || true
	rm -rf .pytest_cache/ .coverage htmlcov/ reports/coverage/
	rm -f outputs/logs.txt outputs/logs.jsonl
	@echo "Cleaned"
