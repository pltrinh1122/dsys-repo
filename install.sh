#!/bin/sh
# install.sh — deploy the dsys CLI tree from a source directory.
#
# POSIX sh. No root/sudo, no interactive prompts, no network calls.
#
# Idempotency (operational convergence, not byte-identity): install(p) is a
# pure function of (dist, p, operator-owned material). Re-running with the
# same profile, or switching profiles, converges the tree regardless of
# history: lib/dsys/install_tree.py triages every install-owned file not in
# the profile's owned set — pristine files are removed, mutated/unknown
# files are quarantined to var/quarantine/<ts>/ with a record (never
# silently destroyed). etc/config.yaml is never clobbered; var/state and
# var/log are never deleted. installed_at changes every run and
# __pycache__ regenerates — both excluded from the equality.
set -eu

CLI_VERSION="0.1.0"
INSTALLER_VERSION="1.0.0"

usage() {
  cat <<EOF
usage: install.sh [options]

  --profile base|full   install profile (default: full)
  --from DIR            source tree (default: this script's directory)
  --home DIR            install target (default: \${DSYS_HOME:-\$HOME/.dsys})
  --core DIR            architecture package source
                        (default: <src>/core/package)
  --help                print this help and exit
EOF
}

PROFILE="full"
SRC=""
INSTALL_HOME=""
CORE_DIR=""

while [ "$#" -gt 0 ]; do
  case "$1" in
    --profile)
      [ "$#" -ge 2 ] || { echo "error: --profile needs a value" >&2; exit 1; }
      PROFILE="$2"; shift 2 ;;
    --profile=*) PROFILE="${1#--profile=}"; shift ;;
    --from)
      [ "$#" -ge 2 ] || { echo "error: --from needs a value" >&2; exit 1; }
      SRC="$2"; shift 2 ;;
    --from=*) SRC="${1#--from=}"; shift ;;
    --home)
      [ "$#" -ge 2 ] || { echo "error: --home needs a value" >&2; exit 1; }
      INSTALL_HOME="$2"; shift 2 ;;
    --home=*) INSTALL_HOME="${1#--home=}"; shift ;;
    --core)
      [ "$#" -ge 2 ] || { echo "error: --core needs a value" >&2; exit 1; }
      CORE_DIR="$2"; shift 2 ;;
    --core=*) CORE_DIR="${1#--core=}"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "error: unknown argument: $1" >&2; usage >&2; exit 1 ;;
  esac
done

[ "$PROFILE" = "base" ] || [ "$PROFILE" = "full" ] \
  || { echo "error: --profile must be base|full (got '$PROFILE')" >&2; exit 1; }

if [ -z "$SRC" ]; then
  SRC=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
fi
if [ -z "$INSTALL_HOME" ]; then
  INSTALL_HOME="${DSYS_HOME:-$HOME/.dsys}"
fi
INSTALL_HOME="${INSTALL_HOME%/}"
if [ -z "$CORE_DIR" ]; then
  CORE_DIR="$SRC/core/package"
fi

tmpdir=""
cleanup() {
  if [ -n "$tmpdir" ] && [ -d "$tmpdir" ]; then rm -rf "$tmpdir"; fi
}
trap cleanup EXIT

fail() { # $1 = step label, $2 = reason
  echo "FAILED [$1]: $2" >&2
  exit 1
}

echo "==> [1/7] preflight (profile=$PROFILE)"
command -v python3 >/dev/null 2>&1 \
  || fail "1/7 preflight" "python3 not on PATH"
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' \
  || fail "1/7 preflight" "python3 < 3.10"
[ -f "$CORE_DIR/schema.py" ] \
  || fail "1/7 preflight" "no schema.py in --core $CORE_DIR"
[ -f "$SRC/bin/dsys" ] \
  || fail "1/7 preflight" "no bin/dsys in --from $SRC"
[ -f "$SRC/etc/config.yaml" ] \
  || fail "1/7 preflight" "no etc/config.yaml in --from $SRC"
ls "$SRC"/lib/dsys/*.py >/dev/null 2>&1 \
  || fail "1/7 preflight" "no lib/dsys/*.py in --from $SRC"
[ -f "$SRC/lib/dsys/manifest.py" ] \
  || fail "1/7 preflight" "no lib/dsys/manifest.py in --from $SRC"
[ -f "$SRC/lib/dsys/install_tree.py" ] \
  || fail "1/7 preflight" "no lib/dsys/install_tree.py in --from $SRC"
if [ "$PROFILE" = "full" ]; then
  [ -f "$SRC/lib/dsys/roles.py" ] \
    || fail "1/7 preflight" "no lib/dsys/roles.py in --from $SRC (needed for full profile)"
  for r in cos operator auditor; do
    [ -f "$SRC/roles/$r/role.yaml" ] \
      || fail "1/7 preflight" "no roles/$r/role.yaml in --from $SRC (needed for full profile)"
  done
  ls "$SRC"/share/scenarios/*.py >/dev/null 2>&1 \
    || fail "1/7 preflight" "no share/scenarios/*.py in --from $SRC (needed for full profile)"
fi

echo "==> [2/7] create venv"
if [ -d "$INSTALL_HOME/venv" ]; then
  rm -rf "$INSTALL_HOME/venv" \
    || fail "2/7 create venv" "cannot remove existing venv at $INSTALL_HOME/venv"
fi
python3 -m venv --system-site-packages "$INSTALL_HOME/venv" \
  || fail "2/7 create venv" "python3 -m venv failed"
"$INSTALL_HOME/venv/bin/python" -c 'import pydantic; print("    venv python ok; pydantic", pydantic.VERSION)' \
  || fail "2/7 create venv" "venv python cannot import pydantic (host must provide it)"

echo "==> [3/7] converge tree (profile=$PROFILE)"
if [ "$PROFILE" = "full" ]; then
  for r in cos operator auditor; do
    python3 "$SRC/lib/dsys/roles.py" seal "$SRC/roles/$r" >/dev/null \
      || fail "3/7 converge tree" "seal roles/$r"
  done
fi
mkdir -p "$INSTALL_HOME/var/state" "$INSTALL_HOME/var/log" "$INSTALL_HOME/var/cache" \
  || fail "3/7 converge tree" "mkdir var dirs"
python3 "$SRC/lib/dsys/install_tree.py" converge \
  "$INSTALL_HOME" "$PROFILE" "$SRC" "$CORE_DIR" "$INSTALLER_VERSION" \
  || fail "3/7 converge tree" "install_tree.py converge failed"
if [ -f "$INSTALL_HOME/etc/config.yaml" ]; then
  echo "    etc/config.yaml exists — keeping operator config (never clobbered)"
else
  mkdir -p "$INSTALL_HOME/etc" \
    || fail "3/7 converge tree" "mkdir etc"
  cp "$SRC/etc/config.yaml" "$INSTALL_HOME/etc/config.yaml" \
    || fail "3/7 converge tree" "cp etc/config.yaml"
fi

echo "==> [4/7] write manifest"
python3 "$SRC/lib/dsys/manifest.py" write \
  "$INSTALL_HOME" "$PROFILE" "$CLI_VERSION" "$INSTALLER_VERSION" \
  || fail "4/7 write manifest" "manifest.py write failed"

echo "==> [5/7] symlink"
if [ "$INSTALL_HOME" = "$HOME/.dsys" ] && [ -d "$HOME/.local/bin" ]; then
  ln -sf "$INSTALL_HOME/bin/dsys" "$HOME/.local/bin/dsys" \
    || fail "5/7 symlink" "ln -sf failed"
  echo "    symlinked ~/.local/bin/dsys -> $INSTALL_HOME/bin/dsys"
else
  echo "    skipping symlink (home is $INSTALL_HOME); add to PATH:"
  echo "    export PATH=\"$INSTALL_HOME/bin:\$PATH\""
fi

echo "==> [6/7] self-test"
export DSYS_HOME="$INSTALL_HOME"
"$INSTALL_HOME/bin/dsys" --version \
  || fail "6/7 self-test" "dsys --version"
"$INSTALL_HOME/bin/dsys" doctor \
  || fail "6/7 self-test" "dsys doctor (expected exit 0)"
tmpdir=$(mktemp -d) \
  || fail "6/7 self-test" "mktemp -d"
"$INSTALL_HOME/bin/dsys" state init --seed golden --out "$tmpdir/g.json" \
  || fail "6/7 self-test" "dsys state init --seed golden"
"$INSTALL_HOME/bin/dsys" referee validate --state "$tmpdir/g.json" \
  || fail "6/7 self-test" "dsys referee validate (expected exit 0)"

echo "==> [7/7] done"
echo ""
echo "dsys installed: $INSTALL_HOME (profile: $PROFILE, cli $CLI_VERSION, installer $INSTALLER_VERSION)"
echo "note: the venv uses --system-site-packages — pydantic is inherited from"
echo "      the host, not vendored. Zero network, zero duplication; a future"
echo "      release may vendor wheels with --require-hashes instead."
