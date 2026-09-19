#!/bin/sh
# install.sh — deploy the dsys CLI tree from a source directory.
#
# POSIX sh. No root/sudo, no interactive prompts, no network calls.
# Idempotent: re-running rebuilds the venv and replaces the tree, but
# never clobbers etc/config.yaml and never deletes var/state or var/log.
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

echo "==> [1/8] preflight (profile=$PROFILE)"
command -v python3 >/dev/null 2>&1 \
  || fail "1/8 preflight" "python3 not on PATH"
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' \
  || fail "1/8 preflight" "python3 < 3.10"
[ -f "$CORE_DIR/schema.py" ] \
  || fail "1/8 preflight" "no schema.py in --core $CORE_DIR"
[ -f "$SRC/bin/dsys" ] \
  || fail "1/8 preflight" "no bin/dsys in --from $SRC"
[ -f "$SRC/etc/config.yaml" ] \
  || fail "1/8 preflight" "no etc/config.yaml in --from $SRC"
ls "$SRC"/lib/dsys/*.py >/dev/null 2>&1 \
  || fail "1/8 preflight" "no lib/dsys/*.py in --from $SRC"
[ -f "$SRC/lib/dsys/manifest.py" ] \
  || fail "1/8 preflight" "no lib/dsys/manifest.py in --from $SRC"
if [ "$PROFILE" = "full" ]; then
  [ -f "$SRC/lib/dsys/roles.py" ] \
    || fail "1/8 preflight" "no lib/dsys/roles.py in --from $SRC (needed for full profile)"
  for r in cos operator auditor; do
    [ -f "$SRC/roles/$r/role.yaml" ] \
      || fail "1/8 preflight" "no roles/$r/role.yaml in --from $SRC (needed for full profile)"
  done
  ls "$SRC"/share/scenarios/*.py >/dev/null 2>&1 \
    || fail "1/8 preflight" "no share/scenarios/*.py in --from $SRC (needed for full profile)"
fi

echo "==> [2/8] create venv"
if [ -d "$INSTALL_HOME/venv" ]; then
  rm -rf "$INSTALL_HOME/venv" \
    || fail "2/8 create venv" "cannot remove existing venv at $INSTALL_HOME/venv"
fi
python3 -m venv --system-site-packages "$INSTALL_HOME/venv" \
  || fail "2/8 create venv" "python3 -m venv failed"
"$INSTALL_HOME/venv/bin/python" -c 'import pydantic; print("    venv python ok; pydantic", pydantic.VERSION)' \
  || fail "2/8 create venv" "venv python cannot import pydantic (host must provide it)"

echo "==> [3/8] lay down tree"
mkdir -p "$INSTALL_HOME/bin" "$INSTALL_HOME/lib/dsys" "$INSTALL_HOME/lib/core/package" \
  "$INSTALL_HOME/etc" "$INSTALL_HOME/var/state" "$INSTALL_HOME/var/log" \
  "$INSTALL_HOME/var/cache" "$INSTALL_HOME/share/scenarios" \
  || fail "3/8 lay down tree" "mkdir failed"
cp "$SRC/bin/dsys" "$INSTALL_HOME/bin/dsys" \
  || fail "3/8 lay down tree" "cp bin/dsys"
chmod +x "$INSTALL_HOME/bin/dsys" \
  || fail "3/8 lay down tree" "chmod bin/dsys"
cp "$SRC"/lib/dsys/*.py "$INSTALL_HOME/lib/dsys/" \
  || fail "3/8 lay down tree" "cp lib/dsys/*.py"
for f in __init__ __main__ schema validators views golden_run; do
  cp "$CORE_DIR/$f.py" "$INSTALL_HOME/lib/core/package/$f.py" \
    || fail "3/8 lay down tree" "cp $f.py from --core"
done
if [ -f "$INSTALL_HOME/etc/config.yaml" ]; then
  echo "    etc/config.yaml exists — keeping operator config (never clobbered)"
else
  cp "$SRC/etc/config.yaml" "$INSTALL_HOME/etc/config.yaml" \
    || fail "3/8 lay down tree" "cp etc/config.yaml"
fi

echo "==> [4/8] profile: $PROFILE"
if [ "$PROFILE" = "full" ]; then
  for r in cos operator auditor; do
    python3 "$SRC/lib/dsys/roles.py" seal "$SRC/roles/$r" >/dev/null \
      || fail "4/8 profile" "seal roles/$r"
  done
  rm -rf "$INSTALL_HOME/lib/roles" \
    || fail "4/8 profile" "cannot clear $INSTALL_HOME/lib/roles"
  mkdir -p "$INSTALL_HOME/lib/roles" \
    || fail "4/8 profile" "mkdir lib/roles"
  for r in cos operator auditor; do
    cp -r "$SRC/roles/$r" "$INSTALL_HOME/lib/roles/$r" \
      || fail "4/8 profile" "cp roles/$r"
  done
  rm -rf "$INSTALL_HOME/share/scenarios" \
    || fail "4/8 profile" "cannot clear $INSTALL_HOME/share/scenarios"
  mkdir -p "$INSTALL_HOME/share/scenarios" \
    || fail "4/8 profile" "mkdir share/scenarios"
  cp "$SRC"/share/scenarios/*.py "$INSTALL_HOME/share/scenarios/" \
    || fail "4/8 profile" "cp share/scenarios/*.py"
else
  # full -> base reinstalls downgrade cleanly
  rm -rf "$INSTALL_HOME/lib/roles" "$INSTALL_HOME/share/scenarios" \
    || fail "4/8 profile" "cannot strip full-profile dirs"
fi

echo "==> [5/8] write manifest"
python3 "$SRC/lib/dsys/manifest.py" write \
  "$INSTALL_HOME" "$PROFILE" "$CLI_VERSION" "$INSTALLER_VERSION" \
  || fail "5/8 write manifest" "manifest.py write failed"

echo "==> [6/8] symlink"
if [ "$INSTALL_HOME" = "$HOME/.dsys" ] && [ -d "$HOME/.local/bin" ]; then
  ln -sf "$INSTALL_HOME/bin/dsys" "$HOME/.local/bin/dsys" \
    || fail "6/8 symlink" "ln -sf failed"
  echo "    symlinked ~/.local/bin/dsys -> $INSTALL_HOME/bin/dsys"
else
  echo "    skipping symlink (home is $INSTALL_HOME); add to PATH:"
  echo "    export PATH=\"$INSTALL_HOME/bin:\$PATH\""
fi

echo "==> [7/8] self-test"
export DSYS_HOME="$INSTALL_HOME"
"$INSTALL_HOME/bin/dsys" --version \
  || fail "7/8 self-test" "dsys --version"
"$INSTALL_HOME/bin/dsys" doctor \
  || fail "7/8 self-test" "dsys doctor (expected exit 0)"
tmpdir=$(mktemp -d) \
  || fail "7/8 self-test" "mktemp -d"
"$INSTALL_HOME/bin/dsys" state init --seed golden --out "$tmpdir/g.json" \
  || fail "7/8 self-test" "dsys state init --seed golden"
"$INSTALL_HOME/bin/dsys" referee validate --state "$tmpdir/g.json" \
  || fail "7/8 self-test" "dsys referee validate (expected exit 0)"

echo "==> [8/8] done"
echo ""
echo "dsys installed: $INSTALL_HOME (profile: $PROFILE, cli $CLI_VERSION, installer $INSTALLER_VERSION)"
echo "note: the venv uses --system-site-packages — pydantic is inherited from"
echo "      the host, not vendored. Zero network, zero duplication; a future"
echo "      release may vendor wheels with --require-hashes instead."
