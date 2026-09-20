#!/bin/sh
# install.sh — deploy the dsys CLI tree from a source directory.
#
# POSIX sh. No root/sudo, no network calls outside acquisition.
# Non-interactive by default; the single exception is
# --accretion-require-authorization, an explicit operator preference
# (installer-spec §13) that prompts before committing an accretion
# snapshot — and refuses rather than prompts when stdin is not a
# terminal.
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
  --release TAG         acquire release TAG from github.com/pltrinh1122/dsys-repo
                        (mutually exclusive with --from; network used for
                        acquisition only — everything after unpack is offline)
  --release-sha256 HEX  pin the expected tarball hash out-of-band (fleet use);
                        must agree with the release's published checksum
  --home DIR            install target (default: \${DSYS_HOME:-\$HOME/.dsys})
  --core DIR            architecture package source
                        (default: <src>/core/package)
  --overwrite           set up a FRESH accretion repo: an existing repo at
                        the accretion path is moved aside to
                        <path>.bak-<utc-ts>/ (never deleted), then a new
                        repo is initialized. Default (no flag) is resume:
                        continue the existing repo's history.
  --accretion-path DIR  override the accretion repo path
                        (default: /var/daccretion/<instance>;
                        config accretion.path; flags > config > default)
  --no-accretion        skip the accretion repo entirely this run
  --accretion-require-authorization
                        commit authority = operator: prompt before each
                        accretion snapshot commit; refuse (before any tree
                        mutation) on decline or non-terminal stdin.
                        Default is standing authorization (auto-commit).
  --help                print this help and exit
EOF
}

PROFILE="full"
SRC=""
FROM_GIVEN=""
RELEASE=""
RELEASE_SHA256=""
INSTALL_HOME=""
CORE_DIR=""
OVERWRITE=""
ACCRETION_PATH_FLAG=""
NO_ACCRETION=""
ACCRETION_REQUIRE_AUTH=""

while [ "$#" -gt 0 ]; do
  case "$1" in
    --profile)
      [ "$#" -ge 2 ] || { echo "error: --profile needs a value" >&2; exit 1; }
      PROFILE="$2"; shift 2 ;;
    --profile=*) PROFILE="${1#--profile=}"; shift ;;
    --from)
      [ "$#" -ge 2 ] || { echo "error: --from needs a value" >&2; exit 1; }
      SRC="$2"; FROM_GIVEN="1"; shift 2 ;;
    --from=*) SRC="${1#--from=}"; FROM_GIVEN="1"; shift ;;
    --release)
      [ "$#" -ge 2 ] || { echo "error: --release needs a value" >&2; exit 1; }
      RELEASE="$2"; shift 2 ;;
    --release=*) RELEASE="${1#--release=}"; shift ;;
    --release-sha256)
      [ "$#" -ge 2 ] || { echo "error: --release-sha256 needs a value" >&2; exit 1; }
      RELEASE_SHA256="$2"; shift 2 ;;
    --release-sha256=*) RELEASE_SHA256="${1#--release-sha256=}"; shift ;;
    --home)
      [ "$#" -ge 2 ] || { echo "error: --home needs a value" >&2; exit 1; }
      INSTALL_HOME="$2"; shift 2 ;;
    --home=*) INSTALL_HOME="${1#--home=}"; shift ;;
    --core)
      [ "$#" -ge 2 ] || { echo "error: --core needs a value" >&2; exit 1; }
      CORE_DIR="$2"; shift 2 ;;
    --core=*) CORE_DIR="${1#--core=}"; shift ;;
    --overwrite) OVERWRITE="1"; shift ;;
    --accretion-path)
      [ "$#" -ge 2 ] || { echo "error: --accretion-path needs a value" >&2; exit 1; }
      ACCRETION_PATH_FLAG="$2"; shift 2 ;;
    --accretion-path=*) ACCRETION_PATH_FLAG="${1#--accretion-path=}"; shift ;;
    --no-accretion) NO_ACCRETION="1"; shift ;;
    --accretion-require-authorization) ACCRETION_REQUIRE_AUTH="1"; shift ;;
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

# --- accretion repo resolution (installer-spec §13) ---
# precedence: --accretion-path > etc/config.yaml accretion.path >
#   /var/daccretion/<instance>. commit authority: --accretion-require-
#   authorization > config accretion.commit_authority > standing.
cfg_accretion_value() { # $1 = key (path|commit_authority); prints value or empty
  _cfg="$INSTALL_HOME/etc/config.yaml"
  [ -f "$_cfg" ] || return 0
  awk -v key="$1" '
    /^accretion:/ { in_acc=1; next }
    /^[^[:space:]#]/ { in_acc=0 }
    in_acc && $1 == key ":" {
      v=$0; sub(/^[^:]*:[[:space:]]*/, "", v); print v; exit
    }
  ' "$_cfg"
}
INSTANCE_NAME=$(basename "$INSTALL_HOME")
if [ -n "$ACCRETION_PATH_FLAG" ]; then
  ACCRETION_PATH="$ACCRETION_PATH_FLAG"
else
  _cfg_path=$(cfg_accretion_value "path")
  if [ -n "$_cfg_path" ]; then
    ACCRETION_PATH="$_cfg_path"
  else
    ACCRETION_PATH="/var/daccretion/$INSTANCE_NAME"
  fi
fi
ACCRETION_PATH="${ACCRETION_PATH%/}"
if [ -n "$ACCRETION_REQUIRE_AUTH" ]; then
  ACCRETION_AUTH="operator"
else
  _cfg_auth=$(cfg_accretion_value "commit_authority")
  case "$_cfg_auth" in
    operator) ACCRETION_AUTH="operator" ;;
    *) ACCRETION_AUTH="standing" ;;
  esac
fi
ACCRETION_ENABLED="1"
ACCRETION_SKIP_REASON=""
ACCRETION_MODE=""   # fresh | resume — set by accretion_setup

tmpdir=""
reltmp=""
cleanup() {
  if [ -n "$tmpdir" ] && [ -d "$tmpdir" ]; then rm -rf "$tmpdir"; fi
  if [ -n "$reltmp" ] && [ -d "$reltmp" ]; then rm -rf "$reltmp"; fi
}
trap cleanup EXIT

fail() { # $1 = step label, $2 = reason
  echo "FAILED [$1]: $2" >&2
  exit 1
}

# --- accretion repo (installer-spec §13) ---
# Separate git dir, work-tree = install home, every command pathspec-
# scoped to the accreted set (etc + var, minus any cache directory).
# Local only: no remote is ever configured, nothing is ever pushed.
# NOTE: git pathspecs are interpreted relative to cwd, so every git
# invocation below runs with cwd = install home.
ACCRETION_GITDIR="$ACCRETION_PATH/.git"

agit() { # run git against the accretion repo from the install home
  ( cd "$INSTALL_HOME" && git --git-dir="$ACCRETION_GITDIR" \
      --work-tree="$INSTALL_HOME" "$@" )
}

agit_accreted() { # agit limited to the accreted set: etc + var, minus
                  # any cache directory (var/cache, var/runner/cache, …).
                  # Pathspecs are quoted literals — never glob-expanded
                  # by the shell (F-A3's cousin: an expanded pathspec
                  # would silently invert the exclusion).
                  # Callers pass only flags/subcommand; the -- separator
                  # lives here, exactly once.
  agit "$@" -- etc var ':(exclude,glob)**/cache' ':(exclude,glob)**/cache/**'
}

accretion_disable() { # $1 = reason; warn and continue without accretion
  echo "    warning: accretion disabled: $1 (install continues)" >&2
  ACCRETION_ENABLED="0"
  ACCRETION_SKIP_REASON="$1"
}

accretion_setup() {
  # Establishes the repo (init/resume/overwrite). Never fails the install.
  if [ "$NO_ACCRETION" = "1" ]; then
    accretion_disable "--no-accretion given"
    return 0
  fi
  if ! command -v git >/dev/null 2>&1; then
    accretion_disable "git not on PATH"
    return 0
  fi
  if [ -e "$ACCRETION_PATH" ] && [ ! -d "$ACCRETION_PATH" ]; then
    accretion_disable "$ACCRETION_PATH exists and is not a directory"
    return 0
  fi
  if ! mkdir -p "$ACCRETION_PATH" 2>/dev/null; then
    accretion_disable "cannot create $ACCRETION_PATH (not writable)"
    return 0
  fi
  if [ "$OVERWRITE" = "1" ] && [ -d "$ACCRETION_GITDIR" ]; then
    _bak="${ACCRETION_PATH}.bak-$(date -u +%Y%m%dT%H%M%SZ)"
    mv "$ACCRETION_PATH" "$_bak" \
      || { accretion_disable "cannot move aside $ACCRETION_PATH"; return 0; }
    mkdir -p "$ACCRETION_PATH" \
      || { accretion_disable "cannot recreate $ACCRETION_PATH"; return 0; }
    echo "    accretion: existing repo moved aside to $_bak (--overwrite)"
  fi
  if [ -d "$ACCRETION_GITDIR" ]; then
    ACCRETION_MODE="resume"
    echo "    accretion: resuming repo at $ACCRETION_PATH"
  else
    git init -q -b main "$ACCRETION_PATH" 2>/dev/null \
      || { accretion_disable "git init failed at $ACCRETION_PATH"; return 0; }
    agit config core.worktree "$INSTALL_HOME" \
      || { accretion_disable "git config failed"; return 0; }
    agit config user.name "dsys-accretion"
    agit config user.email "dsys-accretion@localhost"
    ACCRETION_MODE="fresh"
    echo "    accretion: initialized fresh repo at $ACCRETION_PATH"
  fi
}

accretion_dirty_paths() { # prints porcelain status of accreted set (may be empty)
  [ "$ACCRETION_ENABLED" = "1" ] || return 0
  agit_accreted status --porcelain 2>/dev/null || true
}

accretion_request_authorization() { # $1 = label; 0 = authorized
  if [ ! -t 0 ]; then
    echo "FAILED [accretion]: commit authority is 'operator' but stdin is not a terminal — refusing" >&2
    echo "    dirty accreted paths:" >&2
    accretion_dirty_paths | head -20 >&2
    return 1
  fi
  printf '    accretion: uncommitted changes (%s). Commit snapshot before installing? [y/N] ' "$1"
  read -r _ans
  case "$_ans" in
    [yY]*) return 0 ;;
    *) echo "    accretion: declined by operator" >&2; return 1 ;;
  esac
}

accretion_snapshot() { # $1 = message; commits if dirty (0 ok, 1 = refused)
  [ "$ACCRETION_ENABLED" = "1" ] || return 0
  [ -d "$INSTALL_HOME/etc" ] || [ -d "$INSTALL_HOME/var" ] || return 0
  # Dirtiness is checked on the work-tree BEFORE staging, so a
  # declined operator authorization leaves the index untouched.
  if [ -z "$(accretion_dirty_paths)" ]; then
    echo "    accretion: nothing to commit ($1)"
    return 0
  fi
  if [ "$ACCRETION_AUTH" = "operator" ]; then
    accretion_request_authorization "$1" || return 1
  fi
  agit_accreted add >/dev/null 2>&1 \
    || { echo "    warning: accretion add failed ($1)" >&2; return 0; }
  agit_accreted commit --quiet -m "$1" >/dev/null 2>&1 \
    || { echo "    warning: accretion commit failed ($1)" >&2; return 0; }
  echo "    accretion: committed ($1)"
  return 0
}

accretion_json() { # prints the manifest's accretion object
  if [ "$ACCRETION_ENABLED" = "1" ]; then
    python3 -c 'import json,sys; print(json.dumps({"enabled": True, "path": sys.argv[1], "commit_authority": sys.argv[2], "mode": sys.argv[3]}))' \
      "$ACCRETION_PATH" "$ACCRETION_AUTH" "$ACCRETION_MODE"
  else
    python3 -c 'import json,sys; print(json.dumps({"enabled": False, "path": sys.argv[1], "reason": sys.argv[2]}))' \
      "$ACCRETION_PATH" "$ACCRETION_SKIP_REASON"
  fi
}

if [ -n "$RELEASE" ] && [ -n "$FROM_GIVEN" ]; then
  echo "error: --release and --from are mutually exclusive" >&2
  exit 1
fi

echo "==> [0/7] acquire source"
if [ -n "$RELEASE" ]; then
  # Network is used here and only here (F-I1): acquisition may need
  # network; deployment is offline given the unpacked dist. The
  # release's own code takes over below -- this tree's release.py is
  # only the courier.
  echo "    release $RELEASE from github.com/pltrinh1122/dsys-repo"
  [ -f "$SRC/lib/dsys/release.py" ] \
    || fail "0/7 acquire" "no lib/dsys/release.py in invoking tree $SRC"
  reltmp=$(mktemp -d) || fail "0/7 acquire" "mktemp -d"
  set -- fetch "$RELEASE" "$reltmp"
  if [ -n "$RELEASE_SHA256" ]; then set -- "$@" --sha256 "$RELEASE_SHA256"; fi
  SRC=$(python3 "$SRC/lib/dsys/release.py" "$@") \
    || fail "0/7 acquire" "release fetch failed"
  echo "    verified and unpacked to $SRC"
  tarball_hash=$(sha256sum "$reltmp/dsys-$RELEASE.tar.gz" | cut -d' ' -f1) \
    || fail "0/7 acquire" "sha256sum tarball"
  SOURCE_JSON=$(python3 -c \
    'import json,sys; print(json.dumps({"mode":"release","tag":sys.argv[1],"tarball_sha256":sys.argv[2]}))' \
    "$RELEASE" "$tarball_hash")
else
  SOURCE_JSON=$(python3 -c \
    'import json,sys; print(json.dumps({"mode":"local","path":sys.argv[1]}))' \
    "$SRC")
fi

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
[ -f "$SRC/components.json" ] \
  || fail "1/7 preflight" "no components.json in --from $SRC"
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
# Accretion brackets the tree mutation (installer-spec §13): snapshot
# pre-install state before converge touches anything, post-install
# state after the manifest is written. Resume is the default;
# --overwrite re-initializes (the old repo is moved aside, never
# deleted). In operator-authority mode a declined snapshot refuses
# the install here, before any mutation.
accretion_setup
accretion_snapshot "dsys accretion: pre-install snapshot (installer $INSTALLER_VERSION, profile $PROFILE, mode $ACCRETION_MODE)" \
  || fail "3/7 converge tree" "accretion snapshot refused (commit authority: $ACCRETION_AUTH)"
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
# components.json is carried VERBATIM into the manifest: the installer
# authors nothing about components and maintains nothing — it is a
# courier from dist metadata to the manifest, where `dsys doctor`
# reads it to report per-component status. The accretion object is
# provenance of the same kind: where the journal lives, not a claim
# about its contents.
ACCRETION_JSON=$(accretion_json) \
  || fail "4/7 write manifest" "accretion_json failed"
python3 "$SRC/lib/dsys/manifest.py" write \
  "$INSTALL_HOME" "$PROFILE" "$CLI_VERSION" "$INSTALLER_VERSION" \
  "$SRC/components.json" "$SOURCE_JSON" "$ACCRETION_JSON" \
  || fail "4/7 write manifest" "manifest.py write failed"
accretion_snapshot "dsys accretion: post-install snapshot (installer $INSTALLER_VERSION, profile $PROFILE)" \
  || fail "4/7 write manifest" "accretion snapshot refused (commit authority: $ACCRETION_AUTH)"

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
if [ "$PROFILE" = "full" ]; then
  # runner smoke test (installer-spec section 5): carried-identity
  # fixture — derivation reachable, toolchain pin verifies,
  # output hash == input hash.
  printf 'carried-identity-fixture' > "$tmpdir/fixture.bin" \
    || fail "6/7 self-test" "write derive fixture"
  fhash=$(sha256sum "$tmpdir/fixture.bin" | cut -d' ' -f1) \
    || fail "6/7 self-test" "sha256sum derive fixture"
  cat > "$tmpdir/derivation-manifest.json" <<EOF \
    || fail "6/7 self-test" "write derivation manifest fixture"
{"derivation": "identity", "toolchain": {"name": "runner", "version": "$CLI_VERSION"}, "inputs": [{"path": "$tmpdir/fixture.bin", "sha256": "$fhash"}], "params": {}}
EOF
  "$INSTALL_HOME/bin/dsys" derive --manifest "$tmpdir/derivation-manifest.json" \
      --out "$tmpdir/drv" \
    || fail "6/7 self-test" "dsys derive --manifest (expected exit 0)"
  ohash=$(sha256sum "$tmpdir/drv/output.bin" | cut -d' ' -f1) \
    || fail "6/7 self-test" "sha256sum derivation output"
  [ "$ohash" = "$fhash" ] \
    || fail "6/7 self-test" "derive smoke test: output hash != input hash"
fi

echo "==> [7/7] done"
echo ""
echo "dsys installed: $INSTALL_HOME (profile: $PROFILE, cli $CLI_VERSION, installer $INSTALLER_VERSION)"
echo "note: the venv uses --system-site-packages — pydantic is inherited from"
echo "      the host, not vendored. Zero network, zero duplication; a future"
echo "      release may vendor wheels with --require-hashes instead."
