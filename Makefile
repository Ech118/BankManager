# FROZEN (Step 0). Edited only by the coordinator.
.PHONY: help install-deps install-hooks check-contracts check-ownership check-live secret-scan secret-scan-all gen-mock test

help:
	@echo "make install-deps       install contract-test deps + each partition's requirements.txt"
	@echo "make install-hooks      enable the pre-commit secret scan (run once per clone)"
	@echo "make check-contracts    run contract tests in mock mode (run before EVERY commit/merge)"
	@echo "make check-ownership P=p1|p2|p3|coordinator   verify you only touched your paths"
	@echo "make check-live BM_TEST_TICKER=XXX            live-mode contract check (needs keys)"
	@echo "make secret-scan        scan staged changes    | make secret-scan-all  scan all tracked files"
	@echo "make gen-mock           regenerate fixtures/mock/*.json (coordinator only)"

install-deps:
	python3 -m pip install -r tests/contracts/requirements.txt
	@for d in data calc audit agents orchestrator; do \
	  if [ -f $$d/requirements.txt ]; then python3 -m pip install -r $$d/requirements.txt; fi; \
	done

install-hooks:
	git config core.hooksPath scripts/hooks
	@echo "pre-commit secret scan enabled"

check-contracts:
	BM_MODE=mock BM_LLM=mock python3 -m pytest tests/contracts -q

check-ownership:
	@test -n "$(P)" || (echo "usage: make check-ownership P=p1|p2|p3|coordinator" && exit 2)
	scripts/check_ownership.sh $(P)

check-live:
	@test -n "$(BM_TEST_TICKER)" || (echo "usage: make check-live BM_TEST_TICKER=XXX" && exit 2)
	BM_MODE=live BM_TEST_TICKER=$(BM_TEST_TICKER) python3 -m pytest tests/contracts/test_live.py -q

secret-scan:
	scripts/secret_scan.sh

secret-scan-all:
	scripts/secret_scan.sh --all

gen-mock:
	python3 scripts/gen_mock_fixtures.py

test: check-contracts
