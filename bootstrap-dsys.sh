#!/usr/bin/env bash
# bootstrap-dsys.sh — thin bootstrap for an empty directory.
# Fetches the author-agent tree, then hands off to make (the real framework).
# This script contains no install logic; that lives in the tree's Makefile.
#
# Get it and run it:
#   curl -O https://raw.githubusercontent.com/pltrinh1122/dsys-repo/build/half1/bootstrap-dsys.sh
#   bash bootstrap-dsys.sh
# Then:
#   cd dsys && make run
set -euo pipefail

REPO="https://github.com/pltrinh1122/dsys-repo.git"
BRANCH="build/half1"

if [ -f "./dsys/Makefile" ]; then
  echo "using existing tree: ./dsys"
elif [ ! -d "./dsys" ]; then
  command -v git >/dev/null 2>&1 || {
    echo "FAIL: git not found (needed to fetch the tree)" >&2; exit 1; }
  echo "cloning $BRANCH..."
  git clone --depth 1 --branch "$BRANCH" "$REPO" dsys
else
  echo "FAIL: ./dsys exists but has no Makefile (not a dsys tree?)" >&2
  exit 1
fi

cd dsys
command -v make >/dev/null 2>&1 || {
  echo "FAIL: make not found (the tree's build interface is make)" >&2; exit 1; }
exec make install
