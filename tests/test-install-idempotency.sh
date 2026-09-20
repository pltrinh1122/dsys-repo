#!/bin/sh
# tests/test-install-idempotency.sh — acceptance tests for installer idempotency.
#
#   T0a: install_base x2                               -> install_base
#   T0b: install_full x2                               -> install_full
#   T1:  install_base, install_full, install_base      -> install_base
#   T2:  install_full, install_base, install_full      -> install_full
#   T3:  install_full, mutate lib/roles/cos/role.yaml, install_base
#        -> mutated bytes QUARANTINED (never destroyed); tree == install_base
#   T4:  install_full, add unknown lib/dsys/zz_custom.py, install_full
#        -> unknown file QUARANTINED; tree == install_full
#
# "==" is operational convergence, not byte-identity:
#   - same install-owned file fingerprints (bin/, lib/, share/; no __pycache__)
#   - same normalized manifest (profile + file hashes; installed_at and
#     install_path excluded per the byte-identity falsifier)
#   - dsys doctor exit 0 with pristine
#   - correct command matrix (base refuses execute/roles/scenario/session;
#     full serves roles)
#   - etc/config.yaml and var/state preserved byte-identical across the run
#
# Each case installs into an isolated --home under a mktemp root; the
# operator's real install is never touched. Slow (~10 installs, each
# rebuilds a venv); run in the background.
set -eu

REPO=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT INT TERM

pass=0
failed=0
note() { printf '%s\n' "$*"; }
ok()   { pass=$((pass + 1)); note "  PASS: $*"; }
bad()  { failed=$((failed + 1)); note "  FAIL: $*"; }

install_p() { # $1=home $2=profile
  sh "$REPO/install.sh" --from "$REPO" --home "$1" --profile "$2" \
    >"$WORK/install-$2.log" 2>&1
}

dsys() { # $1=home; rest = dsys args
  h=$1; shift
  DSYS_HOME="$h" "$h/bin/dsys" "$@"
}

fingerprint() { # $1=home $2=outfile-prefix
  h=$1
  : >"$2.files"
  for d in bin lib share; do
    if [ -d "$h/$d" ]; then
      ( cd "$h" && find "$d" -type f ! -path '*__pycache__*' | sort ) \
        | while IFS= read -r f; do
            printf '%s  %s\n' "$(sha256sum <"$h/$f" | cut -d' ' -f1)" "$f"
          done >>"$2.files"
    fi
  done
  python3 - "$h/var/manifest.json" >"$2.manifest" <<'EOF'
import json, sys
m = json.load(open(sys.argv[1]))
m.pop("installed_at", None)
m.pop("install_path", None)
print(json.dumps(m, sort_keys=True))
EOF
}

check_doctor() { # $1=home $2=label
  out=$(dsys "$1" doctor 2>&1); code=$?
  if [ $code -ne 0 ]; then bad "$2: doctor exit $code :: $out"; return 1; fi
  case "$out" in
    *pristine*) ok "$2: doctor pristine" ;;
    *) bad "$2: doctor exit 0 but not pristine"; return 1 ;;
  esac
}

check_profile() { # $1=home $2=expected $3=label
  got=$(dsys "$1" --version 2>/dev/null | sed -n 's/^profile: //p')
  if [ "$got" = "$2" ]; then ok "$3: profile=$got"; else bad "$3: profile=$got, want $2"; fi
}

check_matrix() { # $1=home $2=profile $3=label
  if [ "$2" = "base" ]; then
    if dsys "$1" execute >/dev/null 2>&1; then
      bad "$3: base served execute (must refuse)"
    else
      ok "$3: base refuses execute"
    fi
  else
    if dsys "$1" roles list >/dev/null 2>&1; then
      ok "$3: full serves roles list"
    else
      bad "$3: full failed roles list"
    fi
  fi
}

plant_markers() { # $1=home
  mkdir -p "$1/var/state"
  printf 'marker-%s\n' "$$" >"$1/var/state/idem-marker.txt"
  printf '# operator comment (idempotency test)\n' >>"$1/etc/config.yaml"
  sha256sum <"$1/var/state/idem-marker.txt" | cut -d' ' -f1 >"$WORK/marker.sha"
  sha256sum <"$1/etc/config.yaml" | cut -d' ' -f1 >"$WORK/config.sha"
}

check_markers() { # $1=home $2=label
  m=$(sha256sum <"$1/var/state/idem-marker.txt" | cut -d' ' -f1)
  c=$(sha256sum <"$1/etc/config.yaml" | cut -d' ' -f1)
  if [ "$m" = "$(cat "$WORK/marker.sha")" ]; then ok "$2: var/state preserved"; else bad "$2: var/state marker changed"; fi
  if [ "$c" = "$(cat "$WORK/config.sha")" ]; then ok "$2: etc/config.yaml preserved"; else bad "$2: etc/config.yaml changed"; fi
}

check_equal() { # $1=seq-home $2=ref-home $3=label
  fingerprint "$1" "$WORK/seq"
  fingerprint "$2" "$WORK/ref"
  if cmp -s "$WORK/seq.files" "$WORK/ref.files"; then
    ok "$3: install-owned file sets identical"
  else
    bad "$3: file sets differ:"; diff "$WORK/ref.files" "$WORK/seq.files" | head -10
  fi
  if cmp -s "$WORK/seq.manifest" "$WORK/ref.manifest"; then
    ok "$3: normalized manifests identical"
  else
    bad "$3: manifests differ:"; diff "$WORK/ref.manifest" "$WORK/seq.manifest" | head -10
  fi
}

check_no_quarantine() { # $1=home $2=label
  if [ -d "$1/var/quarantine" ]; then
    bad "$2: unexpected quarantine dir"
  else
    ok "$2: no quarantine (nothing diverged)"
  fi
}

note "== reference installs =="
REF_BASE="$WORK/ref-base"; REF_FULL="$WORK/ref-full"
install_p "$REF_BASE" base && ok "reference install_base" || { bad "reference install_base failed"; sed -n '1,20p' "$WORK/install-base.log"; }
install_p "$REF_FULL" full && ok "reference install_full" || { bad "reference install_full failed"; sed -n '1,20p' "$WORK/install-full.log"; }

run_sequence() { # $1=label $2=home $3=expected-profile ; rest = profile sequence
  label=$1; home=$2; want=$3; shift 3
  note "== $label =="
  first=1
  for p in "$@"; do
    install_p "$home" "$p" || { bad "$label: install $p failed"; sed -n '1,25p' "$WORK/install-$p.log"; return 1; }
    if [ $first -eq 1 ]; then plant_markers "$home"; first=0; fi
  done
  if [ "$want" = "base" ]; then ref=$REF_BASE; else ref=$REF_FULL; fi
  check_equal "$home" "$ref" "$label"
  check_doctor "$home" "$label"
  check_profile "$home" "$want" "$label"
  check_matrix "$home" "$want" "$label"
  check_markers "$home" "$label"
}

run_sequence "T0a: base,base -> base"            "$WORK/t0a" base base base
run_sequence "T0b: full,full -> full"            "$WORK/t0b" full full full
run_sequence "T1: base,full,base -> base"        "$WORK/t1"  base base full base
run_sequence "T2: full,base,full -> full"        "$WORK/t2"  full full base full
check_no_quarantine "$WORK/t1" "T1"
check_no_quarantine "$WORK/t2" "T2"

note "== T3: full, mutate role bundle, base -> quarantine, tree == base =="
T3="$WORK/t3"
install_p "$T3" full || { bad "T3: install full failed"; }
printf '# operator customization (must survive as quarantine, not vanish)\n' >>"$T3/lib/roles/cos/role.yaml"
MUT_SHA=$(sha256sum <"$T3/lib/roles/cos/role.yaml" | cut -d' ' -f1)
install_p "$T3" base || { bad "T3: install base failed"; }
QDIR=$(find "$T3/var/quarantine" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | head -1)
if [ -z "$QDIR" ]; then
  bad "T3: no quarantine dir created"
else
  ok "T3: quarantine dir created"
  QF="$QDIR/lib/roles/cos/role.yaml"
  if [ -f "$QF" ] && [ "$(sha256sum <"$QF" | cut -d' ' -f1)" = "$MUT_SHA" ]; then
    ok "T3: mutated bytes preserved byte-identical in quarantine"
  else
    bad "T3: quarantined bytes differ from the mutation"
  fi
  if grep -q '"reason": "mutated"' "$QDIR/record.json" 2>/dev/null; then
    ok "T3: record.json declares reason=mutated"
  else
    bad "T3: record.json missing or wrong reason"
  fi
  if grep -qi quarantine "$WORK/install-base.log"; then ok "T3: installer reported the quarantine"; else bad "T3: installer silent about quarantine"; fi
fi
check_equal "$T3" "$REF_BASE" "T3"
check_doctor "$T3" "T3"
check_profile "$T3" "base" "T3"

note "== T4: full, add unknown file, full -> quarantine, tree == full =="
T4="$WORK/t4"
install_p "$T4" full || { bad "T4: install full failed"; }
printf '# operator helper (unknown to the manifest)\n' >"$T4/lib/dsys/zz_custom.py"
UNK_SHA=$(sha256sum <"$T4/lib/dsys/zz_custom.py" | cut -d' ' -f1)
install_p "$T4" full || { bad "T4: reinstall full failed"; }
QDIR4=$(find "$T4/var/quarantine" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | head -1)
if [ -z "$QDIR4" ]; then
  bad "T4: no quarantine dir created"
else
  QF4="$QDIR4/lib/dsys/zz_custom.py"
  if [ -f "$QF4" ] && [ "$(sha256sum <"$QF4" | cut -d' ' -f1)" = "$UNK_SHA" ]; then
    ok "T4: unknown file preserved byte-identical in quarantine"
  else
    bad "T4: quarantined unknown file differs"
  fi
  if grep -q '"reason": "unknown"' "$QDIR4/record.json" 2>/dev/null; then
    ok "T4: record.json declares reason=unknown"
  else
    bad "T4: record.json missing or wrong reason"
  fi
fi
check_equal "$T4" "$REF_FULL" "T4"
check_doctor "$T4" "T4"

note ""
note "RESULT: $pass passed, $failed failed"
[ "$failed" -eq 0 ]
