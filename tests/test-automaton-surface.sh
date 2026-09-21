#!/bin/bash
# test-automaton-surface.sh — the dsys automaton flow-drive surface
# (cli-interface-spec §3.7; enforcement home for I-26/I-27).
#
# Builds throwaway install homes under $TMPDIR and drives the CLI through
# them via DSYS_HOME. Every case asserts an exit code; refusals must name
# their reason and a refused initiation must write no run record.
set -u
REPO="$(cd "$(dirname "$0")/.." && pwd)"
CLI="python3 $REPO/lib/dsys/cli.py"
UUID="11111111-2222-4333-8444-555555555555"
PASS=0; FAIL=0

ok()   { PASS=$((PASS+1)); echo "ok   $1"; }
bad()  { FAIL=$((FAIL+1)); echo "FAIL $1"; }

# mkhome <dir> <profile> [identity] — a test install home; when identity is
# given the home is "minted": manifest accretion_repo.identity + repo
# dsys.repo-id match, config accretion.path points at the repo.
mkhome() {
  local d="$1" profile="$2" ident="${3:-}"
  rm -rf "$d"; mkdir -p "$d/var" "$d/etc"
  if [ -n "$ident" ]; then
    printf '{"install_path": "%s", "profile": "%s", "accretion_repo": {"identity": "%s"}}' \
      "$d" "$profile" "$ident" > "$d/var/manifest.json"
    git init -q -b main "$d/accr"
    git --git-dir="$d/accr/.git" config dsys.repo-id "$ident"
    printf 'accretion:\n  path: %s/accr\n' "$d" > "$d/etc/config.yaml"
  else
    printf '{"install_path": "%s", "profile": "%s"}' "$d" "$profile" > "$d/var/manifest.json"
  fi
}

T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT

# 1. init-flow success, then idempotent re-init
mkhome "$T/h1" full "$UUID"
out=$(DSYS_HOME="$T/h1" $CLI automaton init-flow --flow flow-release-monitor 2>/dev/null); c=$?
[ $c -eq 0 ] && echo "$out" | grep -q initiated && ok "1 init-flow ok" || bad "1 init-flow (exit=$c out=$out)"
RUN=$(ls "$T/h1/var/runs" | sed 's/.json//')
out=$(DSYS_HOME="$T/h1" $CLI automaton init-flow --flow flow-release-monitor 2>/dev/null); c=$?
[ $c -eq 0 ] && echo "$out" | grep -q "already bound" && ok "2 re-init idempotent" || bad "2 re-init (exit=$c out=$out)"

# 2b. run record shape
python3 - "$T/h1/var/runs/$RUN.json" <<'EOF'
import json,sys
d = json.load(open(sys.argv[1]))
assert d["state"] == "running" and d["current_state_id"] == "urm-idle", d
assert d["acquisition"]["path_source"] == "config", d["acquisition"]
assert d["events"] == [], d
print("record ok")
EOF
[ $? -eq 0 ] && ok "2b run record shape" || bad "2b run record shape"

# 3. unknown flow
DSYS_HOME="$T/h1" $CLI automaton init-flow --flow bogus 2>&1 | grep -q "unknown flow"
[ $? -eq 0 ] && ok "3 unknown flow refused" || bad "3 unknown flow"

# 4. un-minted manifest: fail fast, no run written
mkhome "$T/h2" full
git init -q -b main "$T/h2/accr"
printf 'accretion:\n  path: %s/accr\n' "$T/h2" > "$T/h2/etc/config.yaml"
out=$(DSYS_HOME="$T/h2" $CLI automaton init-flow --flow flow-release-monitor 2>&1); c=$?
[ $c -eq 1 ] && echo "$out" | grep -q "no accretion_repo.identity" \
  && [ ! -d "$T/h2/var/runs" ] && ok "4 un-minted fail-fast, nothing written" \
  || bad "4 un-minted (exit=$c out=$out)"

# 5. wrong repo-id: fail fast
mkhome "$T/h3" full "$UUID"
git --git-dir="$T/h3/accr/.git" config dsys.repo-id "99999999-9999-4999-8999-999999999999"
out=$(DSYS_HOME="$T/h3" $CLI automaton init-flow --flow flow-release-monitor 2>&1); c=$?
[ $c -eq 1 ] && echo "$out" | grep -q "does not match" && ok "5 wrong identity fail-fast" \
  || bad "5 wrong identity (exit=$c out=$out)"

# 6. base profile
mkhome "$T/h4" base
DSYS_HOME="$T/h4" $CLI automaton init-flow --flow flow-release-monitor 2>&1 | grep -q "not available in the base profile"
[ $? -eq 0 ] && ok "6 base profile refused" || bad "6 base profile"

# 7. advance: honest refusal (drive execution not implemented)
out=$(DSYS_HOME="$T/h1" $CLI automaton advance --flow-run "$RUN" 2>&1); c=$?
[ $c -eq 1 ] && echo "$out" | grep -q "refusing rather than faking" && ok "7 advance honest refusal" \
  || bad "7 advance (exit=$c out=$out)"

# 8. advance unknown run
DSYS_HOME="$T/h1" $CLI automaton advance --flow-run fr-deadbeefdeadbeef 2>&1 | grep -q "unknown flow run"
[ $? -eq 0 ] && ok "8 advance unknown run" || bad "8 advance unknown run"

# 9. replay: transcript valid
out=$(DSYS_HOME="$T/h1" $CLI automaton replay --flow-run "$RUN" 2>/dev/null); c=$?
[ $c -eq 0 ] && echo "$out" | grep -q "transcript valid" && ok "9 replay valid" \
  || bad "9 replay (exit=$c out=$out)"

# 10. rebind under a bound run: advance refuses, re-init refuses
git --git-dir="$T/h1/accr/.git" config dsys.repo-id "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
out=$(DSYS_HOME="$T/h1" $CLI automaton advance --flow-run "$RUN" 2>&1); c=$?
[ $c -eq 1 ] && echo "$out" | grep -q "no longer valid" && ok "10a advance post-hoc invalid" \
  || bad "10a advance post-hoc (exit=$c out=$out)"
DSYS_HOME="$T/h1" $CLI automaton init-flow --flow flow-release-monitor 2>&1 | grep -q "does not match"
[ $? -eq 0 ] && ok "10b re-init post-hoc invalid" || bad "10b re-init post-hoc"
git --git-dir="$T/h1/accr/.git" config dsys.repo-id "$UUID"  # restore

# 11. flag > config precedence
mkhome "$T/h5" full "$UUID"
git init -q -b main "$T/h5/repoB" && git --git-dir="$T/h5/repoB/.git" config dsys.repo-id "$UUID"
DSYS_HOME="$T/h5" $CLI automaton init-flow --flow flow-release-monitor --accretion-path "$T/h5/repoB" >/dev/null 2>&1
src=$(python3 -c "import json,glob; print(json.load(open(glob.glob('$T/h5/var/runs/*.json')[0]))['acquisition']['path_source'])")
[ "$src" = "flag" ] && ok "11 flag > config" || bad "11 precedence (got $src)"

# 12. json envelope
out=$(DSYS_HOME="$T/h1" $CLI --format json automaton replay --flow-run "$RUN" 2>/dev/null)
echo "$out" | python3 -c "import json,sys; d=json.load(sys.stdin); assert d['data']['valid'] is True and d['exit_code']==0, d" \
  && ok "12 json envelope" || bad "12 json envelope"

echo "--- $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
