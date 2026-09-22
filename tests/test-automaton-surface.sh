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

# 7. advance with no trigger: quiescent at the wait state (exit 0, no-op)
out=$(DSYS_HOME="$T/h1" $CLI automaton advance --flow-run "$RUN" 2>/dev/null); c=$?
[ $c -eq 0 ] && echo "$out" | grep -q "state=running transitions_taken=0" && ok "7a advance no-trigger quiescent" \
  || bad "7a advance (exit=$c out=$out)"


# 7g. unhandled trigger: no transition wins -> abort + a fixed-template
# automaton-exception disclosure is minted (spec §7), nothing faked
out=$(DSYS_HOME="$T/h1" $CLI automaton advance --flow-run "$RUN" --trigger external 2>/dev/null); c=$?
[ $c -eq 0 ] && echo "$out" | grep -q "state=aborted" && ok "7g unhandled trigger aborts" \
  || bad "7g unhandled (exit=$c out=$out)"
D=$(python3 -c "
import json,glob
for f in glob.glob(\"$T/h1/var/disclosures/dl-*.json\"):
    d=json.load(open(f))
    if d.get('flow_run_id')=='$RUN': print(f); break")
[ -n "$D" ] && python3 - "$D" <<'EOF'
import json,sys
d = json.load(open(sys.argv[1]))
assert d["kind"] == "automaton-exception", d
assert d["status"] == "open", d
assert d["trigger"] == "external", d
assert isinstance(d["seq"], int) and d["seq"] >= 1, d
# the fixed template: the four facts, no prose, no judgment
lines = d["text"].splitlines()
assert lines == [l for l in lines if l], d["text"]
keys = [l.split(":")[0] for l in lines]
assert keys == ["flow_id", "flow_run_id", "state_id", "trigger"], d["text"]
print("disclosure ok")
EOF
[ $? -eq 0 ] && [ -n "$D" ] && ok "7h disclosure minted (fixed template)" || bad "7h disclosure"
out=$(DSYS_HOME="$T/h1" $CLI automaton replay --flow-run "$RUN" 2>/dev/null); c=$?
[ $c -eq 0 ] && echo "$out" | grep -q "transcript valid" && ok "7i abort replay valid" \
  || bad "7i abort replay (exit=$c out=$out)"

# fresh open run for the timer drive (init-flow is idempotent on its
# initiation inputs, so drop the aborted run's record first)
rm "$T/h1/var/runs/$RUN.json"
RUN=$(DSYS_HOME="$T/h1" $CLI automaton init-flow --flow flow-release-monitor 2>/dev/null | sed 's/^flow run //; s/ .*//')

# 7b. advance --trigger timer: drives idle->checking; the task state's
# run-book names a production tool with no implementation in this build —
# the executor records the missing tool loudly as the child's failure,
# the child aborts via its retry:3 policy, the flow takes run_aborted
# to its failed end state. Nothing faked; everything on the record.
out=$(DSYS_HOME="$T/h1" $CLI automaton advance --flow-run "$RUN" --trigger timer 2>/dev/null); c=$?
[ $c -eq 0 ] && echo "$out" | grep -q "state=aborted transitions_taken=2" && ok "7b drive to failed end state" \
  || bad "7b drive (exit=$c out=$out)"
CHILD=$(python3 -c "import json,glob; fs=[f for f in glob.glob('$T/h1/var/runs/*.json') if json.load(open(f)).get('kind')=='run']; print(__import__('json').load(open(fs[0]))['run_id'])")
python3 - "$T/h1/var/runs/$CHILD.json" <<'EOF'
import json,sys
d = json.load(open(sys.argv[1]))
kinds = [e["kind"] for e in d["events"]]
assert d["state"] == "aborted", d["state"]
assert kinds.count("step_started") == 3 and kinds.count("step_failed") == 3, kinds
sf = [e for e in d["events"] if e["kind"] == "step_failed"][0]
assert "unknown tool 'tool-fetch-feed'" in sf["payload"]["error"], sf["payload"]
print("child record ok")
EOF
[ $? -eq 0 ] && ok "7c child recorded the missing tool loudly" || bad "7c child record"

# 7d. replay the child: transcript valid (never reinvokes tools)
out=$(DSYS_HOME="$T/h1" $CLI automaton replay --run "$CHILD" 2>/dev/null); c=$?
[ $c -eq 0 ] && echo "$out" | grep -q "transcript valid" && ok "7d child replay valid" \
  || bad "7d child replay (exit=$c out=$out)"

# 7e. advance a closed flow run: no-op
out=$(DSYS_HOME="$T/h1" $CLI automaton advance --flow-run "$RUN" --trigger timer 2>&1); c=$?
[ $c -eq 0 ] && echo "$out" | grep -q "already closed" && ok "7e closed flow no-op" \
  || bad "7e closed flow (exit=$c out=$out)"

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

# 7j. flow-level tamper: delete a transition -> replay exit 5
python3 - "$T/h1/var/runs/$RUN.json" <<'EOF'
import json,sys
p = sys.argv[1]; d = json.load(open(p))
d["events"] = d["events"][1:]
open(p, "w").write(json.dumps(d, indent=2))
EOF
out=$(DSYS_HOME="$T/h1" $CLI automaton replay --flow-run "$RUN" 2>&1); c=$?
[ $c -eq 5 ] && ok "7j tampered flow replay exit 5" || bad "7j flow tamper (exit=$c out=$out)"

# 13+. run-level surface: init / advance / replay --run (executor §§4-10)
mkhome "$T/h6" full

# 13. init a run-book run, then idempotent re-init
out=$(DSYS_HOME="$T/h6" $CLI automaton init --runbook fx-pass --ctx '{"go": true}' 2>/dev/null); c=$?
[ $c -eq 0 ] && echo "$out" | grep -q initiated && ok "13 init ok" || bad "13 init (exit=$c out=$out)"
RID=$(echo "$out" | sed 's/^run //; s/ .*//')
out=$(DSYS_HOME="$T/h6" $CLI automaton init --runbook fx-pass --ctx '{"go": true}' 2>/dev/null); c=$?
[ $c -eq 0 ] && echo "$out" | grep -q "already bound" && ok "14 re-init idempotent" || bad "14 re-init (exit=$c out=$out)"

# 15. unknown run-book refused
DSYS_HOME="$T/h6" $CLI automaton init --runbook bogus 2>&1 | grep -q "unknown run-book"
[ $? -eq 0 ] && ok "15 unknown run-book refused" || bad "15 unknown run-book"

# 16. advance to completion
out=$(DSYS_HOME="$T/h6" $CLI automaton advance --run "$RID" 2>/dev/null); c=$?
[ $c -eq 0 ] && echo "$out" | grep -q "state=completed steps_advanced=2" && ok "16 advance completes" \
  || bad "16 advance (exit=$c out=$out)"

# 17. replay valid; 18. advance closed is a no-op
out=$(DSYS_HOME="$T/h6" $CLI automaton replay --run "$RID" 2>/dev/null); c=$?
[ $c -eq 0 ] && echo "$out" | grep -q "transcript valid" && ok "17 replay valid" || bad "17 replay (exit=$c out=$out)"
out=$(DSYS_HOME="$T/h6" $CLI automaton advance --run "$RID" 2>&1); c=$?
[ $c -eq 0 ] && echo "$out" | grep -q "already closed" && ok "18 closed run no-op" || bad "18 closed (exit=$c out=$out)"

# 19. zero-step run-book completes vacuously
out=$(DSYS_HOME="$T/h6" $CLI automaton init --runbook fx-zero 2>/dev/null | sed 's/^run //; s/ .*//')
out2=$(DSYS_HOME="$T/h6" $CLI automaton advance --run "$out" 2>/dev/null); c=$?
[ $c -eq 0 ] && echo "$out2" | grep -q "state=completed steps_advanced=0" && ok "19 zero-step vacuous" \
  || bad "19 zero-step (exit=$c out=$out2)"

# 20. parked: guard false is "not yet" — sticky quiescence, then --external unparks
RIDP=$(DSYS_HOME="$T/h6" $CLI automaton init --runbook fx-parked 2>/dev/null | sed 's/^run //; s/ .*//')
out=$(DSYS_HOME="$T/h6" $CLI automaton advance --run "$RIDP" 2>/dev/null); c=$?
[ $c -eq 0 ] && echo "$out" | grep -q "state=open" && ok "20a parked, run stays open" || bad "20a parked (exit=$c out=$out)"
out=$(DSYS_HOME="$T/h6" $CLI automaton advance --run "$RIDP" 2>/dev/null); c=$?
[ $c -eq 0 ] && echo "$out" | grep -q "events_appended=0" && ok "20b quiescence sticky (no duplicate parked)" \
  || bad "20b sticky (exit=$c out=$out)"
out=$(DSYS_HOME="$T/h6" $CLI automaton advance --run "$RIDP" --external wake --payload '{"open": true}' 2>/dev/null); c=$?
[ $c -eq 0 ] && echo "$out" | grep -q "state=completed" && ok "20c external unparks" || bad "20c unpark (exit=$c out=$out)"

# 21. failure policies: skip / abort / retry:2
RIDS=$(DSYS_HOME="$T/h6" $CLI automaton init --runbook fx-fail-skip --on-step-failure skip 2>/dev/null | sed 's/^run //; s/ .*//')
out=$(DSYS_HOME="$T/h6" $CLI automaton advance --run "$RIDS" 2>/dev/null)
echo "$out" | grep -q "state=completed" && ok "21a skip completes" || bad "21a skip (out=$out)"
RIDA=$(DSYS_HOME="$T/h6" $CLI automaton init --runbook fx-fail-abort 2>/dev/null | sed 's/^run //; s/ .*//')
out=$(DSYS_HOME="$T/h6" $CLI automaton advance --run "$RIDA" 2>/dev/null)
echo "$out" | grep -q "state=aborted" && ok "21b abort aborts" || bad "21b abort (out=$out)"
RIDR=$(DSYS_HOME="$T/h6" $CLI automaton init --runbook fx-retry-abort --on-step-failure retry:2 2>/dev/null | sed 's/^run //; s/ .*//')
DSYS_HOME="$T/h6" $CLI automaton advance --run "$RIDR" >/dev/null 2>&1
n=$(python3 -c "import json; d=json.load(open('$T/h6/var/runs/$RIDR.json')); print([e['kind'] for e in d['events']].count('step_started'))")
[ "$n" = "2" ] && ok "21c retry:2 attempts twice then aborts" || bad "21c retry (started=$n)"

# 22. malformed tool result (C1): normalized failure, never into ctx
RIDM=$(DSYS_HOME="$T/h6" $CLI automaton init --runbook fx-malformed 2>/dev/null | sed 's/^run //; s/ .*//')
out=$(DSYS_HOME="$T/h6" $CLI automaton advance --run "$RIDM" 2>/dev/null); c=$?
[ $c -eq 0 ] && echo "$out" | grep -q "state=aborted" || bad "22a malformed aborts (exit=$c out=$out)"
python3 - "$T/h6/var/runs/$RIDM.json" <<'EOF'
import json,sys
d = json.load(open(sys.argv[1]))
sf = [e for e in d["events"] if e["kind"] == "step_failed"][0]
assert sf["payload"]["malformed"] is True, sf["payload"]
assert "'ok' is str" in sf["payload"]["error"], sf["payload"]
print("c1 ok")
EOF
[ $? -eq 0 ] && ok "22 malformed normalized (C1)" || bad "22 malformed"

# 23. structural tamper of an OPEN run: replay exit 5, advance refuses
RIDT=$(DSYS_HOME="$T/h6" $CLI automaton init --runbook fx-pass --ctx '{"go": true, "case": "tamper"}' 2>/dev/null | sed 's/^run //; s/ .*//')
DSYS_HOME="$T/h6" $CLI automaton advance --run "$RIDT" --max-steps 1 >/dev/null 2>&1
python3 - "$T/h6/var/runs/$RIDT.json" <<'EOF'
import json,sys
p = sys.argv[1]; d = json.load(open(p))
assert d["state"] == "open", d["state"]
d["events"] = [e for e in d["events"] if e["kind"] != "step_started"]
open(p, "w").write(json.dumps(d, indent=2))
EOF
out=$(DSYS_HOME="$T/h6" $CLI automaton replay --run "$RIDT" 2>&1); c=$?
[ $c -eq 5 ] && echo "$out" | grep -q "seq gap" && ok "23a tampered replay exit 5" || bad "23a tamper replay (exit=$c out=$out)"
DSYS_HOME="$T/h6" $CLI automaton advance --run "$RIDT" 2>&1 | grep -q "refusing to extend"
[ $? -eq 0 ] && ok "23b advance refuses a tampered log" || bad "23b advance tampered"

# 24. lock contention: a second invoker fails fast (exit 1, lease-busy)
RIDL=$(DSYS_HOME="$T/h6" $CLI automaton init --runbook fx-pass --ctx '{"go": true, "case": "lock"}' 2>/dev/null | sed 's/^run //; s/ .*//')
python3 -c 'import fcntl,sys,time; f=open(sys.argv[1],"a+b"); fcntl.flock(f.fileno(), fcntl.LOCK_EX); time.sleep(4)' \
  "$T/h6/var/runs/$RIDL.json" &
HOLDER=$!; sleep 0.5
out=$(DSYS_HOME="$T/h6" $CLI automaton advance --run "$RIDL" 2>&1); c=$?
wait $HOLDER
[ $c -eq 1 ] && echo "$out" | grep -q "lease-busy" && ok "24 lock contention fail-fast" \
  || bad "24 lock (exit=$c out=$out)"

# 25. resource bound: --max-steps trips without semantic effect
out=$(DSYS_HOME="$T/h6" $CLI automaton advance --run "$RIDL" --max-steps 1 2>/dev/null); c=$?
[ $c -eq 0 ] && echo "$out" | grep -q "state=open steps_advanced=1" && ok "25a bound trips, step recorded" \
  || bad "25a bound (exit=$c out=$out)"
out=$(DSYS_HOME="$T/h6" $CLI automaton advance --run "$RIDL" 2>/dev/null); c=$?
[ $c -eq 0 ] && echo "$out" | grep -q "state=completed" && ok "25b resume after bound completes" \
  || bad "25b resume (exit=$c out=$out)"

# 26. dangling step_started (C2, simulated crash): replay valid, advance recovers
RIDC=$(DSYS_HOME="$T/h6" $CLI automaton init --runbook fx-pass --ctx '{"go": true, "case": "crash"}' 2>/dev/null | sed 's/^run //; s/ .*//')
python3 - "$T/h6/var/runs/$RIDC.json" <<'EOF'
import json,sys
p = sys.argv[1]; d = json.load(open(p))
d["events"] = [d["events"][0],
               {"seq": 1, "kind": "step_started",
                "payload": {"step_seq": 0, "tool": "noop"}}]
open(p, "w").write(json.dumps(d, indent=2))
EOF
out=$(DSYS_HOME="$T/h6" $CLI automaton replay --run "$RIDC" 2>/dev/null); c=$?
[ $c -eq 0 ] && echo "$out" | grep -q "transcript valid" && ok "26a dangling step_started is valid (C2)" \
  || bad "26a C2 (exit=$c out=$out)"
out=$(DSYS_HOME="$T/h6" $CLI automaton advance --run "$RIDC" 2>/dev/null); c=$?
[ $c -eq 0 ] && echo "$out" | grep -q "state=completed" && ok "26b crash recovery re-invokes and completes" \
  || bad "26b recovery (exit=$c out=$out)"

# 27. bad policy and bad ctx are usage errors
DSYS_HOME="$T/h6" $CLI automaton init --runbook fx-pass --on-step-failure bogus 2>&1 | grep -q "bad failure policy"
[ $? -eq 0 ] && ok "27a bad policy refused" || bad "27a bad policy"
DSYS_HOME="$T/h6" $CLI automaton init --runbook fx-pass --ctx '[1]' 2>&1 | grep -q "must be a JSON object"
[ $? -eq 0 ] && ok "27b non-object ctx refused" || bad "27b bad ctx"

echo "--- $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
