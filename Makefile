# Makefile — install / run interface for the Half 1 author-agent tree
# (author-agent loop DR-CMD-083/084, channels DR-CMD-085/087,
#  containment DR-CMD-086/088).
#
# Empty-directory flow:
#   curl -O https://raw.githubusercontent.com/pltrinh1122/dsys-repo/build/half1/bootstrap-dsys.sh
#   bash bootstrap-dsys.sh   # clones the tree, runs make install
#   cd dsys && make run
#
# (From a checkout you can also run make directly.)
#   make install    # python/venv checks, golden batteries, CLI smoke
#                   # -> writes install-receipt.json
#   make run        # end-to-end loop + batteries x2 + determinism
#                   # -> pasteable telemetry block for chat verification
#   make infer      # Half 2 inference-service demo (stub-backed claude)
#                   # -> pasteable telemetry block for chat verification
#
# make run / make infer refuse unless make install has completed
# (install-receipt.json).

SHELL := /bin/bash
.SHELLFLAGS := -euo pipefail -c

ROOT := $(CURDIR)
RECEIPT := $(ROOT)/install-receipt.json

.PHONY: help install run infer clean

help:
	@printf 'targets:\n'
	@printf '  install   verify the tree (venv, golden batteries, CLI smoke)\n'
	@printf '  run       execute end-to-end + gather pasteable telemetry\n'
	@printf '  infer     Half 2 inference-service demo + telemetry\n'
	@printf '  clean     remove install-receipt.json and install-logs/\n'

install:
	python3 $(ROOT)/scripts/install_author_agent.py

run:
	@test -f "$(RECEIPT)" || { printf 'FAIL: installer has not executed in this tree.\n  missing: %s\nRun `make install` first.\n' "$(RECEIPT)" >&2; exit 1; }
	python3 $(ROOT)/scripts/run_author_agent.py

infer:
	@test -f "$(RECEIPT)" || { printf 'FAIL: installer has not executed in this tree.\n  missing: %s\nRun `make install` first.\n' "$(RECEIPT)" >&2; exit 1; }
	python3 $(ROOT)/scripts/run_infer_demo.py

clean:
	rm -rf "$(ROOT)/install-logs" "$(RECEIPT)"
