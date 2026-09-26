#!/usr/bin/env bash
# run-author-agent.sh — execute the author-agent end-to-end and gather
# pasteable telemetry for verification in chat.
#
# What it does:
#   1. LIVE LOOP: in a FRESH scratch root (mirroring the specified replay in
#      author_agent_golden_run._replay): pending -> commission ->
#      record-authoring-session + stage-profile + stage-build-request
#      (ambient/Harness side, J1-ii: mechanical here — reuses the live,
#      verified registrar profile bytes verbatim; no new authoring, no
#      inference) -> drive (contained build) -> report -> pending.
#      The live tree's journal is never touched by the loop.
#   2. DIAGNOSTICS: the four golden batteries (factory, channels, author,
#      containment), each run TWICE; outputs hashed and compared to prove
#      deterministic replay.
#   3. Prints a compact telemetry block between
#      === BEGIN AUTHOR-AGENT TELEMETRY === / === END AUTHOR-AGENT TELEMETRY ===
#      Paste that block back into chat. Full logs stay in the temp dir
#      printed after the block.
#
# Verification contract (what the verifier checks in the pasted block):
#   - tree.git_commit matches the expected build/half1 head
#   - every exit code is 0
#   - tallies: factory "passed cases: 183", channels/author '"ok": true',
#     containment "6/6 passed"
#   - determinism=IDENTICAL on all four batteries
#   - live loop: commission admitted, session+profile+build-request staged,
#     drive builds registrar, report ok, pending drained to 0
#   - verdict: PASS
set -u

SCRIPT_V="run-author-agent.sh v1"
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT" || { echo "FAIL: cannot cd to $ROOT" >&2; exit 1; }
[ -f "core/package/author_agent.py" ] || { echo "FAIL: not an author-agent tree: $ROOT" >&2; exit 1; }

# --- python: contained venv if present, else python3 (needs pydantic) ---
PY=""
if [ -n "${AUTHOR_VENV_DIR:-}" ] && [ -x "$AUTHOR_VENV_DIR/bin/python" ]; then
  PY="$AUTHOR_VENV_DIR/bin/python"
elif [ -x "$HOME/.dsys/author-venv/bin/python" ]; then
  PY="$HOME/.dsys/author-venv/bin/python"
else
  PY="python3"
fi
if ! "$PY" -c "import pydantic, sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" 2>/dev/null; then
  echo "FAIL: $PY lacks pydantic or python>=3.10 (run install-author-agent.sh first)" >&2
  exit 1
fi

TS="$(date -u +%Y%m%dT%H%M%SZ)"
TDIR="$(mktemp -d "${TMPDIR:-/tmp}/author-telemetry-XXXXXX")"
CID="telemetry-${TS}"
LOOP_ROOT="$TDIR/loop-root"   # fresh authoring root per run; live journal untouched
AGENT="registrar"             # demo agent (DR-CMD-083 J4)

sha() { sha256sum "$1" | cut -d' ' -f1; }
now_s() { date +%s; }

# --- env telemetry ---
GIT_INFO="not-a-git-tree"
if git -C "$ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  GIT_INFO="branch=$(git -C "$ROOT" branch --show-current 2>/dev/null || echo '?')@$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo '?')"
fi
HOST="$(hostname 2>/dev/null || echo unknown)"
PYV="$("$PY" -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')"
PDV="$("$PY" -c 'import pydantic; print(pydantic.VERSION)' 2>/dev/null || echo unknown)"

# --- step runner: run_step <name> <outfile> <cmd...> ---
FAIL_REASONS=""
run_step() {
  local name="$1" out="$2"; shift 2
  local t0 t1
  t0=$(now_s)
  "$@" >"$out" 2>&1
  local code=$?
  t1=$(now_s)
  printf '%s|%s|%s|%s' "$code" "$((t1 - t0))" "$(sha "$out")" "$out" >"$TDIR/step-$name.meta"
  if [ "$code" -ne 0 ]; then
    FAIL_REASONS="${FAIL_REASONS}${FAIL_REASONS:+; }step '$name' exit=$code"
  fi
  return 0
}
step_meta() { cat "$TDIR/step-$1.meta"; }  # code|secs|sha|file

json_count() { # count of commission ids in a pending JSON array file
  "$PY" -c "import json,sys; print(len(json.load(open(sys.argv[1]))))" "$1" 2>/dev/null || echo "?"
}

# --- LIVE LOOP (fresh scratch root; mirrors author_agent_golden_run._replay) ---
mkdir -p "$LOOP_ROOT"
CH_ARGS=(--root "$LOOP_ROOT")
run_step "pending.before" "$TDIR/pending-before.json" "$PY" -m core.package.author_channels "${CH_ARGS[@]}" pending
PEND_BEFORE="$(json_count "$TDIR/pending-before.json")"

run_step "commission" "$TDIR/commission.json" "$PY" -m core.package.author_channels "${CH_ARGS[@]}" commission \
  --id "$CID" \
  --brief "telemetry self-check: drive the registrar demo agent through the governed loop" \
  --acceptance "verdict record staged;report readable" \
  --disposition-ref "telemetry-run $TS"
COMM_ID="$( "$PY" -c "import json,sys; print(json.load(open('$TDIR/commission.json')).get('commission_id','?'))" 2>/dev/null || echo '?')"

# Ambient/Harness-side staging (J1-ii stigmergic invocation), mirroring the
# specified replay: record the authoring session, pin the live verified
# registrar profile bytes, bind them to this commission as a build-request.
# Mechanical here — the bytes are reused verbatim, no new authoring.
run_step "stage" "$TDIR/stage.json" "$PY" - "$LOOP_ROOT" "$CID" <<'EOF'
import json, sys
from pathlib import Path
from core.package import author_agent as aa
root, cid = Path(sys.argv[1]), sys.argv[2]
live = Path("core/package/authored")
aa.record_authoring_session(root, cid, "registrar",
                            {k: True for k in aa.CHECKLIST},
                            note="telemetry")
src = (live / "registrar.py").read_text()
prof = aa.stage_authored_profile(
    root, "registrar", src,
    rationale="telemetry: verified registrar bytes reused verbatim",
    commission_id=cid)
req = aa.stage_build_request(root, "registrar", cid)
print(json.dumps({"agent": "registrar",
                  "staged_profile_sha256": prof["sha256"],
                  "build_request_seq": req["seq"]}))
EOF

run_step "drive" "$TDIR/drive.json" "$PY" -m core.package.author_channels "${CH_ARGS[@]}" drive
# The drive must actually build the demo agent (not no-op).
BUILT="$("$PY" -c "
import json
d = json.load(open('$TDIR/drive.json'))
print(' '.join(d.get('built', [])))" 2>/dev/null)"
case " $BUILT " in
  *" $AGENT "*) ;;
  *) FAIL_REASONS="${FAIL_REASONS}${FAIL_REASONS:+; }drive built nothing (built: [$BUILT])" ;;
esac
run_step "report" "$TDIR/report.json" "$PY" -m core.package.author_channels "${CH_ARGS[@]}" report --commission "$CID"
run_step "pending.after" "$TDIR/pending-after.json" "$PY" -m core.package.author_channels "${CH_ARGS[@]}" pending
PEND_AFTER="$(json_count "$TDIR/pending-after.json")"

if [ "$PEND_AFTER" != "0" ]; then
  FAIL_REASONS="${FAIL_REASONS}${FAIL_REASONS:+; }queue not drained (pending after=$PEND_AFTER, want 0)"
fi

# --- DIAGNOSTICS x2 ---
# Normalization for determinism comparison: the containment battery names
# its per-run scratch dirs with a counter (contain-0054, ...) by design.
# Verdicts are deterministic; the scratch names are not. Strip them before
# hashing so the comparison tests verdict determinism, not scratch naming.
norm() { sed -E 's/\(contain-[0-9]+\)/(contain-N)/g' "$1"; }
run_battery_twice() { # <name> <tally-grep> <cmd...>
  local name="$1" tally="$2"; shift 2
  run_step "${name}.r1" "$TDIR/${name}-r1.log" "$@"
  run_step "${name}.r2" "$TDIR/${name}-r2.log" "$@"
  local det="DIFFERENT"
  [ "$(norm "$TDIR/${name}-r1.log" | sha256sum | cut -d' ' -f1)" = \
    "$(norm "$TDIR/${name}-r2.log" | sha256sum | cut -d' ' -f1)" ] && det="IDENTICAL"
  local tg="missing"
  grep -q "$tally" "$TDIR/${name}-r1.log" 2>/dev/null && grep -q "$tally" "$TDIR/${name}-r2.log" 2>/dev/null && tg="found"
  printf '%s|%s' "$det" "$tg" >"$TDIR/battery-$name.meta"
  if [ "$det" != "IDENTICAL" ]; then
    FAIL_REASONS="${FAIL_REASONS}${FAIL_REASONS:+; }battery '$name' not deterministic"
  fi
  if [ "$tg" != "found" ]; then
    FAIL_REASONS="${FAIL_REASONS}${FAIL_REASONS:+; }battery '$name' tally '$tally' not found"
  fi
}
run_battery_twice "factory"  "passed cases: 183" "$PY" -m core.package.factory_golden_run
run_battery_twice "channels" '"ok": true'        "$PY" -m core.package.author_channels_golden_run
run_battery_twice "author"   '"ok": true'        "$PY" -m core.package.author_agent_golden_run
run_battery_twice "contain"  "6/6 passed"        "$PY" core/package/author_contain_golden_run.py

VERDICT="PASS"
[ -n "$FAIL_REASONS" ] && VERDICT="FAIL"

# --- pasteable block ---
block_line() { # <name>
  local m det tg
  m="$(step_meta "$1")"
  printf '%s: exit=%s secs=%s sha256=%s\n' "$1" "$(cut -d'|' -f1 <<<"$m")" "$(cut -d'|' -f2 <<<"$m")" "$(cut -d'|' -f3 <<<"$m")"
}
battery_line() { # <name> <tally>
  local r1 r2 m det tg
  r1="$(step_meta "$1.r1")"; r2="$(step_meta "$1.r2")"; m="$(cat "$TDIR/battery-$1.meta")"
  det="$(cut -d'|' -f1 <<<"$m")"; tg="$(cut -d'|' -f2 <<<"$m")"
  printf '%s: r1_exit=%s r2_exit=%s tally[%s]=%s determinism=%s r1_sha=%s r2_sha=%s\n' \
    "$1" "$(cut -d'|' -f1 <<<"$r1")" "$(cut -d'|' -f1 <<<"$r2")" "$2" "$tg" "$det" \
    "$(cut -d'|' -f3 <<<"$r1")" "$(cut -d'|' -f3 <<<"$r2")"
}

{
printf '=== BEGIN AUTHOR-AGENT TELEMETRY ===\n'
printf 'script: %s\n' "$SCRIPT_V"
printf 'utc: %s\n' "$TS"
printf 'host: %s\n' "$HOST"
printf 'tree: %s\n' "$ROOT"
printf 'tree.git: %s\n' "$GIT_INFO"
printf 'python: %s (pydantic %s)\n' "$PYV" "$PDV"
printf '[live-loop]\n'
printf 'loop.root: scratch (fresh per run; live journal untouched)\n'
block_line "pending.before"; printf 'pending.before.count=%s\n' "$PEND_BEFORE"
block_line "commission"; printf 'commission.id=%s\n' "$COMM_ID"
block_line "stage"; printf 'stage.agent=%s\n' "$AGENT"
block_line "drive"; printf 'drive.built=%s\n' "$BUILT"
block_line "report"
block_line "pending.after"; printf 'pending.after.count=%s\n' "$PEND_AFTER"
printf '[diagnostics x2]\n'
printf 'note: determinism hashed on scratch-name-normalized output (per-run scratch counters excluded by design)\n'
battery_line "factory" "passed cases: 183"
battery_line "channels" '"ok": true'
battery_line "author" '"ok": true'
battery_line "contain" "6/6 passed"
printf 'verdict: %s\n' "$VERDICT"
[ -n "$FAIL_REASONS" ] && printf 'reasons: %s\n' "$FAIL_REASONS"
printf '=== END AUTHOR-AGENT TELEMETRY ===\n'
} | tee "$TDIR/telemetry-block.txt"

printf '\nfull logs: %s\n' "$TDIR"
