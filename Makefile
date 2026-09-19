# FROZEN (Step 0). Edited only by the coordinator.
.PHONY: help setup install-deps install-hooks lint test test-contracts mock-run \
        db-up db-down gen-schema gen-mock check-ownership check-live \
        secret-scan secret-scan-all

PY ?= python

help:
	@echo "make setup              install deps + the pre-commit secret scan (once per clone)"
	@echo "make lint               ruff check"
	@echo "make test-contracts     shared contract suite (run before EVERY commit/merge)"
	@echo "make test               lint + contracts + every partition's unit tests"
	@echo "make mock-run           end-to-end run in mock mode"
	@echo "make gen-schema         regenerate schema/*.json from schema/contracts/"
	@echo "make gen-mock           regenerate fixtures/mock/* (coordinator only)"
	@echo "make db-up | db-down    local Postgres for MODE=live"
	@echo "make check-ownership P=p1|p2|p3|coordinator   verify you only touched your paths"
	@echo "make check-live BM_TEST_TICKER=XXX            live-mode contract check (needs keys)"
	@echo "make secret-scan        scan staged changes | make secret-scan-all  scan all tracked files"

setup: install-deps install-hooks
	@echo ""
	@echo "Ready. Everything runs offline in MODE=mock against the fictional company ACME."
	@echo "Next: make test-contracts"

install-deps:
	$(PY) -m pip install -r tests/contracts/requirements.txt
	$(PY) -m pip install ruff
	@for d in schema/contracts data mcp_server calc agents; do \
	  if [ -f $$d/requirements.txt ]; then \
	    echo "installing $$d/requirements.txt"; \
	    $(PY) -m pip install -r $$d/requirements.txt || \
	      echo "  (skipped: $$d deps are not needed until that partition goes live)"; \
	  fi; \
	done

install-hooks:
	git config core.hooksPath scripts/hooks
	@echo "pre-commit secret scan enabled"

lint:
	$(PY) -m ruff check .

test-contracts:
	MODE=mock LLM_MODE=mock $(PY) -m pytest tests/contracts -q

test: lint test-contracts
	MODE=mock LLM_MODE=mock $(PY) -m pytest \
	  data/tests calc/tests audit/tests agents/tests orchestrator/tests tests/e2e -q

mock-run:
	@MODE=mock LLM_MODE=mock $(PY) -c "import sys; sys.path.insert(0, '.'); \
	from orchestrator import api; v = api.run_analysis('ACME'); \
	print(); \
	print('  MOCK RUN - fictional company ACME, not real market data'); \
	print('  ' + '-' * 62); \
	print('  verdict      ', v['card']['verdict']); \
	print('  thesis       ', v['card']['thesis'][:60] + '...'); \
	print('  P(beat S&P)  ', v['card']['p_beat_sp500_5y'], '(3-5y)'); \
	print('  scores       ', v['card']['scores']); \
	print(); \
	print('  NOT IMPLEMENTED: this is the Step 0 stub. It returns the ACME'); \
	print('  verdict fixture without running the pipeline. The real'); \
	print('  orchestrator lands in roadmap Step 1 (docs/roadmap.md).'); \
	print()"

gen-schema:
	$(PY) scripts/gen_schema.py

gen-mock:
	$(PY) scripts/gen_mock_fixtures.py

db-up:
	@command -v docker >/dev/null 2>&1 || { echo "docker not found; install it or point DATABASE_URL at your own Postgres"; exit 1; }
	docker run -d --name bankmanager-db -p 5432:5432 \
	  -e POSTGRES_USER=bankmanager -e POSTGRES_PASSWORD=bankmanager \
	  -e POSTGRES_DB=bankmanager postgres:16
	@echo "Postgres up. MODE=mock does not need it."

db-down:
	-docker rm -f bankmanager-db

check-ownership:
	@test -n "$(P)" || (echo "usage: make check-ownership P=p1|p2|p3|coordinator" && exit 2)
	scripts/check_ownership.sh $(P)

check-live:
	@test -n "$(BM_TEST_TICKER)" || (echo "usage: make check-live BM_TEST_TICKER=XXX" && exit 2)
	MODE=live BM_TEST_TICKER=$(BM_TEST_TICKER) $(PY) -m pytest tests/contracts/test_live.py -q

secret-scan:
	scripts/secret_scan.sh

secret-scan-all:
	scripts/secret_scan.sh --all
