#!/usr/bin/env bash
# install-author-agent.sh — one-shot fetch, setup + verification for the Half 1 build:
#   author-agent loop (DR-CMD-083/084), channels (DR-CMD-085/087),
#   containment (DR-CMD-086/088).
#
# Usage: put this script anywhere and run it:
#   bash install-author-agent.sh
# If ./core/package/author_agent.py exists, the current directory is used as
# the tree. Otherwise the script fetches the tree itself — no manual download:
#   DSYS_TARBALL=/path/to/tree.tar.gz   use a local tarball instead of downloading
#   DSYS_TARBALL_URL=https://...         override the download URL
#
# What it does, in order:
#   0. obtains the tree (cwd, local tarball, or download)
#   1. checks python3 (>= 3.10) and pip
#   2. installs pydantic on the host python if missing (pinned to the verified version)
#   3. bootstraps the contained venv (~/.dsys/author-venv, hash-pinned; override with AUTHOR_VENV_DIR)
#   4. runs all four golden batteries and asserts the exact expected counts
#   5. smoke-tests the channel CLI (read-only)
# Idempotent: safe to re-run. Logs go to <tree>/install-logs/.
set -u

# --- 0. obtain the tree -------------------------------------------------------
# Default snapshot URL. NOTE: hosted snapshot, expires 2026-09-28 ~21:59 UTC;
# for a durable source use a commit+push (operator's call) and override via DSYS_TARBALL_URL.
DEFAULT_TARBALL_URL="https://muse.ai/files/1244451505423837/930574683074339/vlw6w0zey8ouy0oz1df6idqn/dsys-half1-20260926.tar.gz"

if [ -f "./core/package/author_agent.py" ]; then
  ROOT="$(pwd)"
  printf 'using tree in current directory: %s\n' "$ROOT"
else
  FETCH_DIR="$(pwd)"
  # Prefer a git clone of the build branch (public repo, no auth needed).
  if command -v git >/dev/null 2>&1; then
    printf 'cloning build branch build/half1...\n'
    if git clone --depth 1 --branch build/half1 \
        https://github.com/pltrinh1122/dsys-repo.git "$FETCH_DIR/dsys" 2>"$FETCH_DIR/clone.log"; then
      ROOT="$FETCH_DIR/dsys"
      printf 'tree ready: %s\n' "$ROOT"
    else
      printf 'git clone failed (see %s/clone.log); falling back to tarball\n' "$FETCH_DIR"
    fi
  fi
  if [ -z "${ROOT:-}" ]; then
  TARBALL="${DSYS_TARBALL:-}"
  if [ -z "$TARBALL" ]; then
    URL="${DSYS_TARBALL_URL:-$DEFAULT_TARBALL_URL}"
    if ! command -v curl >/dev/null 2>&1; then
      printf 'FAIL: tree not in ./ and curl not found (cannot download). Set DSYS_TARBALL=/path/to/tree.tar.gz\n' >&2
      exit 1
    fi
    TARBALL="$FETCH_DIR/dsys-tree.tar.gz"
    printf 'downloading tree snapshot...\n  %s\n' "$URL"
    if ! curl -fL --retry 3 -o "$TARBALL" "$URL"; then
      printf 'FAIL: download failed. Set DSYS_TARBALL or DSYS_TARBALL_URL.\n' >&2
      exit 1
    fi
  elif [ ! -f "$TARBALL" ]; then
    printf 'FAIL: DSYS_TARBALL=%s not found\n' "$TARBALL" >&2
    exit 1
  fi
  printf 'extracting tree...\n'
  if ! tar -xzf "$TARBALL" -C "$FETCH_DIR"; then
    printf 'FAIL: could not extract %s\n' "$TARBALL" >&2
    exit 1
  fi
  if [ -f "$FETCH_DIR/dsys/core/package/author_agent.py" ]; then
    ROOT="$FETCH_DIR/dsys"
  else
    printf 'FAIL: extracted tree has no dsys/core/package/author_agent.py (bad tarball?)\n' >&2
    exit 1
  fi
  printf 'tree ready: %s\n' "$ROOT"
  fi
fi

cd "$ROOT"
LOGDIR="$ROOT/install-logs"
mkdir -p "$LOGDIR"

FAILED=0
step()  { printf '\n==> %s\n' "$*"; }
ok()    { printf 'PASS: %s\n' "$*"; }
fail()  { printf 'FAIL: %s\n' "$*"; FAILED=1; }

# --- 1. preconditions -------------------------------------------------------
step "1/5 preconditions"
ok "tree root: $ROOT"

if ! command -v python3 >/dev/null 2>&1; then
  fail "python3 not found on PATH"
  printf 'RESULT: preconditions failed — install skipped\n'
  exit 1
fi
PYVER="$(python3 -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')"
PYOK="$(python3 -c 'import sys; print("yes" if sys.version_info >= (3, 10) else "no")')"
if [ "$PYOK" = "yes" ]; then ok "python3 $PYVER (>= 3.10)"; else fail "python3 $PYVER < 3.10 (need >= 3.10)"; fi

if ! python3 -m pip --version >/dev/null 2>&1; then
  fail "pip not available for python3 (try: python3 -m ensurepip)"
else
  ok "pip available"
fi

# --- 2. host pydantic --------------------------------------------------------
step "2/5 host pydantic"
if python3 -c 'import pydantic' 2>/dev/null; then
  ok "pydantic $(python3 -c 'import pydantic; print(pydantic.VERSION)') already installed"
else
  printf 'installing pydantic==2.13.5 (verified version; needs network)...\n'
  if python3 -m pip install "pydantic==2.13.5" >"$LOGDIR/pip-pydantic.log" 2>&1; then
    ok "pydantic installed"
  else
    fail "pip install pydantic failed (network?) — see $LOGDIR/pip-pydantic.log"
  fi
fi

# --- 3. contained venv (harness-managed; ratified J-C1) -----------------------
step "3/5 contained venv"
if [ "$FAILED" -ne 0 ]; then
  fail "skipped: earlier step failed"
else
  if python3 -c "
import os, sys
sys.path.insert(0, '.')
from core.package.author_contain import ensure_venv, venv_fingerprint
from pathlib import Path
d = os.environ.get('AUTHOR_VENV_DIR')
py = ensure_venv(Path(d) if d else None)
print('venv python:', py)
print('fingerprint:', venv_fingerprint(py))
" >"$LOGDIR/ensure-venv.log" 2>&1; then
    ok "contained venv ready ($(grep 'venv python:' "$LOGDIR/ensure-venv.log" | cut -d' ' -f3-))"
  else
    fail "ensure_venv failed — see $LOGDIR/ensure-venv.log"
  fi
fi

# --- 4. golden batteries ------------------------------------------------------
step "4/5 golden batteries"
run_battery() { # name, expect_grep, command...
  local name="$1"; local expect="$2"; shift 2
  if [ "$FAILED" -ne 0 ]; then fail "$name skipped (earlier failure)"; return; fi
  if "$@" >"$LOGDIR/$name.log" 2>&1 && grep -q "$expect" "$LOGDIR/$name.log"; then
    ok "$name ($expect)"
  else
    fail "$name (expected '$expect') — see $LOGDIR/$name.log"
    tail -5 "$LOGDIR/$name.log"
  fi
}
run_battery factory  "passed cases: 183"  python3 -m core.package.factory_golden_run
run_battery channels '"ok": true'          python3 -m core.package.author_channels_golden_run
run_battery author   '"ok": true'          python3 -m core.package.author_agent_golden_run
run_battery contain  "6/6 passed"           python3 core/package/author_contain_golden_run.py
# factory contract also requires zero violations
if grep -q '"violations": \[\]' "$LOGDIR/factory.log" 2>/dev/null; then
  ok "factory: 0 violations"
elif [ -f "$LOGDIR/factory.log" ]; then
  fail "factory violations non-empty — see $LOGDIR/factory.log"
fi

# --- 5. CLI smoke (read-only) --------------------------------------------------
step "5/5 channel CLI smoke (read-only)"
if [ "$FAILED" -ne 0 ]; then
  fail "skipped: earlier failure"
else
  if [ "$(python3 -m core.package.author_channels pending 2>/dev/null)" = "[]" ]; then
    ok "pending -> []"
  else
    fail "pending did not return []"
  fi
  if python3 -m core.package.author_channels report --commission commission-001 2>/dev/null | grep -q '"all_green": true'; then
    ok "report commission-001 -> diagnostics all green"
  else
    fail "report commission-001 not all green"
  fi
fi

# --- summary -------------------------------------------------------------------
printf '\n'
if [ "$FAILED" -eq 0 ]; then
  printf 'RESULT: all green — install verified.\n'
  printf '  tree           : %s\n' "$ROOT"
  printf '  contained venv : %s (override: AUTHOR_VENV_DIR=... ./install-author-agent.sh)\n' "${AUTHOR_VENV_DIR:-$HOME/.dsys/author-venv}"
  printf '  drive the loop: cd %s && python3 -m core.package.author_channels commission --brief "..." --acceptance "a;b" --disposition-ref "..."\n' "$ROOT"
  printf '                  python3 -m core.package.author_channels drive\n'
  printf '                  python3 -m core.package.author_channels report --commission <id>\n'
  printf '  spec           : doc/d1-d7-author-agent-spec.md (ratified DR-CMD-084)\n'
  printf '  logs           : %s\n' "$LOGDIR"
  exit 0
else
  printf 'RESULT: FAILED — see %s (send the failing log back)\n' "$LOGDIR"
  exit 1
fi
