#!/usr/bin/env bash
# push-and-broadcast.sh -- push the code branch, then broadcast on the bus.
#
# Standing rule: every verified push to a remote is followed by a bus
# broadcast, so tuned listeners are informed without hand-carrying.
# Flow (promoted from the proven /tmp/dsys-final.sh run):
#   1. GitHub device flow, `repo` scope (one single-use token covers both
#      the public dsys-repo and the private dsys-store).
#   2. Push dsys-repo <branch> (never force); verify the remote head via
#      `git ls-remote` BEFORE proceeding.
#   3. Publish the broadcast via the bus CLI
#      (`tax-prep.build` / `code_landed`, payload built by
#      taxprep.bus.code_landed_payload).
#   4. Commit the message in the dsys-store checkout
#      (git -c user.name=taxprep-bus -c user.email=taxprep-bus@local),
#      push dsys-store `main`, verify its head via ls-remote.
#   5. THEN destroy the token. On ANY failure: destroy the token, print
#      FAIL with the reason, exit non-zero -- never silently treat as done.
#
# Why this does not reuse the dsys-push skill (~/workspace/skills/dsys-push):
#   - the skill pushes `main`; this pushes the work branch (build/half1);
#   - the skill requests `public_repo` scope, which 403s on the private
#     dsys-store; this requests `repo` scope for both pushes.
#
# No broadcast is emitted for the dsys-store push itself: the store push
# IS the broadcast delivery (listeners pull it); announcing it would be
# noise.
#
# Usage: push-and-broadcast.sh [branch]     (default: build/half1)
# The script takes no other args. Operator-run: the device-flow half
# needs a human to open the link and enter the code in an EXTERNAL
# browser (not the in-app browser).
set -u

BRANCH="${1:-build/half1}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TAXPREP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_DIR="$(git -C "$TAXPREP_DIR" rev-parse --show-toplevel 2>/dev/null)" \
  || { echo "FAIL: tax-prep dir is not inside a git checkout: $TAXPREP_DIR"; exit 1; }
STORE_DIR="${TAXPREP_STORE_DIR:-$HOME/workspace/dsys-store}"
TAXPREP_PY="${TAXPREP_PYTHON:-$TAXPREP_DIR/.venv/bin/python}"
CLIENT_ID="178c6fc778ccc68e1d6a"   # registered GitHub OAuth app (public id, not a secret)
CODE_REMOTE_HOST_PATH="github.com/pltrinh1122/dsys-repo"
STORE_REMOTE_HOST_PATH="github.com/pltrinh1122/dsys-store"

fail() { unset token 2>/dev/null; echo "FAIL: $1; token destroyed"; exit 1; }

[ -x "$TAXPREP_PY" ] \
  || { echo "FAIL: no taxprep python at $TAXPREP_PY (set TAXPREP_PYTHON)"; exit 1; }
[ -d "$STORE_DIR/.git" ] \
  || { echo "FAIL: dsys-store checkout not found at $STORE_DIR (set TAXPREP_STORE_DIR)"; exit 1; }

# --- prechecks (before any credential is issued) ---
cd "$REPO_DIR" || { echo "FAIL: repo dir not found: $REPO_DIR"; exit 1; }
actual_remote="$(git remote get-url origin 2>/dev/null)" \
  || { echo "FAIL: no origin remote in $REPO_DIR"; exit 1; }
case "$actual_remote" in
  *"$CODE_REMOTE_HOST_PATH"*) ;;
  *) echo "FAIL: origin remote is unexpected: $actual_remote (refusing to change it)"; exit 1 ;;
esac
ahead="$(git rev-list --count "origin/${BRANCH}..HEAD" 2>/dev/null || git rev-list --count HEAD)" \
  || { echo "FAIL: cannot count commits ahead of origin/${BRANCH}"; exit 1; }
if [ "$ahead" -eq 0 ]; then
  echo "OK: nothing to push (local head == origin/${BRANCH}); no broadcast needed."
  exit 0
fi
echo "Commits ahead of origin/${BRANCH}: $ahead"

# --- device flow: request codes (repo scope covers both repos) ---
resp="$(curl -sS -X POST https://github.com/login/device/code \
  -d "client_id=${CLIENT_ID}" -d "scope=repo" \
  -H "Accept: application/json")" \
  || { echo "FAIL: device code request failed"; exit 1; }
j() { printf '%s' "$resp" | python3 -c "import json,sys; print(json.load(sys.stdin)$1)"; }
device_code="$(j '["device_code"]')"
user_code="$(j '["user_code"]')"
verification_uri="$(j '["verification_uri"]')"
interval="$(j '.get("interval", 5)')"

printf '=== ACTION NEEDED ===\n'
printf 'Open this link in an EXTERNAL browser (Safari or Chrome -- NOT the in-app browser):\n%s\n' "$verification_uri"
printf 'Then enter this code:\n%s\n' "$user_code"
printf '(One repo-scoped token for both pushes; destroyed after. Code expires in ~15 min.)\n'

# --- poll for the token ---
token=""
deadline=$(( $(date +%s) + 840 ))
while [ "$(date +%s)" -lt "$deadline" ]; do
  sleep "$interval"
  tresp="$(curl -sS -X POST https://github.com/login/oauth/access_token \
    -d "client_id=${CLIENT_ID}" -d "device_code=${device_code}" \
    -d "grant_type=urn:ietf:params:oauth:grant-type:device_code" \
    -H "Accept: application/json")" || continue
  err="$(printf '%s' "$tresp" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("error",""))')"
  case "$err" in
    "")
      token="$(printf '%s' "$tresp" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("access_token",""))')"
      break ;;
    authorization_pending) continue ;;
    slow_down) interval=$(( interval + 5 )); continue ;;
    expired_token) echo "FAIL: device code expired; run again for a fresh code"; exit 1 ;;
    access_denied) echo "FAIL: authorization denied"; exit 1 ;;
    *) echo "FAIL: token poll error: $err"; exit 1 ;;
  esac
done
[ -n "$token" ] || { echo "FAIL: timed out waiting for authorization"; exit 1; }

# --- 1. push the code branch (never force) ---
code_push_url="https://x-access-token:${token}@${CODE_REMOTE_HOST_PATH}.git"
git -c credential.helper= push "$code_push_url" "$BRANCH" \
  || fail "dsys-repo push of $BRANCH"
local_head="$(git rev-parse HEAD)"
remote_head="$(git ls-remote "$code_push_url" "refs/heads/${BRANCH}" | cut -f1)"
[ -n "$remote_head" ] && [ "$local_head" = "$remote_head" ] \
  || fail "dsys-repo head mismatch (local $local_head vs remote $remote_head)"
echo "OK: dsys-repo pushed ($ahead commit(s)); remote head verified."

# --- 2. publish the broadcast (payload from the shared helper) ---
cd "$TAXPREP_DIR" || fail "tax-prep dir not found: $TAXPREP_DIR"
# TAXPREP_CODE_LANDED_ADDRESSES (comma-separated, optional): requirement IDs
# this push addresses (e.g. "X1,D5"); carried into the code_landed payload
# for the workstation's re-install gate protocol.
payload="$("$TAXPREP_PY" -c "
from taxprep.bus import code_landed_payload
import json, sys
print(json.dumps(code_landed_payload('dsys-repo', sys.argv[1], sys.argv[2], int(sys.argv[3]))))
" "$BRANCH" "$local_head" "$ahead")" || fail "building code_landed payload"
TAXPREP_SESSION_ID="${TAXPREP_SESSION_ID:-architect}" \
TAXPREP_STORE_DIR="$STORE_DIR" \
  "$TAXPREP_PY" -m taxprep.cli bus publish \
    --topic tax-prep.build --type code_landed --payload "$payload" \
  || fail "bus publish"

# --- 3. commit + push the store checkout (this push IS the delivery) ---
cd "$STORE_DIR" || fail "store checkout not found: $STORE_DIR"
# Rebase our broadcast onto any listener messages that landed while the
# device flow was waiting (sibling commits, independent files -- safe).
# Identity is repo-local so the rebase can finalize without a global config.
git config user.name "taxprep-bus" 2>/dev/null || true
git config user.email "taxprep-bus@local" 2>/dev/null || true
GIT_EDITOR=true git -c credential.helper= pull --rebase 2>/dev/null \
  || fail "store pull --rebase (resolve manually in $STORE_DIR)"
git add bus/ || fail "store git add"
git -c user.name="taxprep-bus" -c user.email="taxprep-bus@local" \
    -c credential.helper= commit -q \
    -m "bus: code_landed broadcast dsys-repo ${BRANCH} ${local_head}" \
  || fail "store commit"
store_push_url="https://x-access-token:${token}@${STORE_REMOTE_HOST_PATH}.git"
git -c credential.helper= push "$store_push_url" main \
  || fail "dsys-store push"
store_head="$(git rev-parse HEAD)"
store_remote_head="$(git ls-remote "$store_push_url" refs/heads/main | cut -f1)"
unset token
if [ -n "$store_remote_head" ] && [ "$store_head" = "$store_remote_head" ]; then
  echo "OK: dsys-store pushed; remote head verified; token destroyed."
  exit 0
else
  echo "FAIL: dsys-store head mismatch (local $store_head vs remote $store_remote_head); token destroyed"
  exit 1
fi
