# Dialog protocol spec — file-based prompt-response transport

Status: exploration (2026-09-19). NOT approved for implementation.

## 1. Motivation

The backend stress-test (packaging spec §3, 2026-09-19) found that:

- bash backends are easy but collapse role binding, envelope
  integrity, and side-effect bounds (S2);
- inference-API backends are blocked on the missing secret store
  (S3);
- a file interface is not an inferencing agent — it is a transport
  — but as a transport it is the most architecturally coherent
  shape (S4, surviving redirect).

The `dialog` protocol is that transport, designed to preserve the
hermetic intent of the architecture: **dsys itself never touches
the network.** All inference happens in an external *answerer*
that dsys never sees and never invokes — dsys writes prompts as
files and reads responses as files. The answerer may be a human
watching the directory, a poll loop wrapping an LLM API, another
dsys installation, or a stub script. That choice is the
answerer's business, not dsys's.

The honest name matters: `dialog` is a *transport backend*, not
an inferencing agent. Calling it an agent repeats the S4 category
error.

## 2. Non-goals

- Not an inference engine. Nothing in dsys infers.
- Not a sandbox. A malicious local answerer can write anything;
  the threat model is inadvertent error, consistent with the
  architecture's declared-trust posture elsewhere.
- Not a replacement for the Backend protocol — `dialog` *is* a
  backend: one adapter implementing `Backend`, alongside `stub`
  and `claude-cli`.
- `stub` (in-process, canned responses) stays: it is the
  zero-dependency self-test path. `dialog` is stub's grown-up
  sibling — same hermeticity, responses from outside.

## 3. Layout

`var/dialog/` — runtime state, so `var/` (accreted material, not
part of pristine hashing). Created by the installer, mode 0700
(operator-only).

```
var/dialog/
  pending/<turn_id>/prompt.json      # written by dsys, read by answerer
  pending/<turn_id>/response.json    # written by answerer, read by dsys
  closed/<turn_id>/                  # prompt.json + response.json + envelope.json
```

`turn_id`: `dlg_` + 12 hex chars (e.g. `dlg_9f3a41c7e2b0`).

## 4. Formats

`prompt.json` (dsys → answerer; self-contained so the answerer
needs no access to the install tree):

```json
{
  "turn_id": "dlg_9f3a41c7e2b0",
  "dialog_id": "dlg-thread-7",
  "in_reply_to": null,
  "role": "cos",
  "role_hash": "sha256:…",
  "prompt_hash": "sha256:…",
  "system": "<full role system prompt text>",
  "prompt": "<the input>",
  "timeout_s": 300,
  "backend": "dialog"
}
```

`response.json` (answerer → dsys; strict schema, see §7):

```json
{
  "turn_id": "dlg_9f3a41c7e2b0",
  "text": "<response text>",
  "refusal": false,
  "backend_name": "human-operator",
  "backend_version": "…",
  "model": "…",
  "error": null
}
```

`dialog_id` / `in_reply_to` thread multi-turn dialogs; v0 turns are
otherwise stateless (each turn carries the full system prompt),
which matches the harness's turn structure. The scenario driver
treats turns independently.

## 5. Turn lifecycle (`Backend.execute` for `dialog`)

1. `dsys execute --as <role> "<input>"` with `backend: dialog`
   (config or `--backend`): resolve the role bundle, compute
   hashes, mint `turn_id`, write `pending/<turn_id>/prompt.json`.
2. Poll for `pending/<turn_id>/response.json` (ignore `*.tmp`),
   wall-clock timeout from `timeout_s` (default: config).
3. On appearance: read, validate schema and `turn_id` match,
   build the run envelope
   `{role, role_hash, prompt_hash, backend: "dialog",
   backend_version, started_at, duration_ms, exit_code, stdout:
   text, stderr: ""}`, move the turn directory to
   `closed/<turn_id>/` with `envelope.json` appended.
4. On timeout: exit 2, stderr names the `turn_id`; the pending
   turn is retained for `dialog status` / `dialog abandon`.
5. On `refusal: true`: exit 4 — agent refusal stays first-class,
   consistent with the packaging spec.

CLI surface addition: `dsys dialog status` (list pending turns:
turn_id, role, wait time), `dsys dialog abandon <turn_id>`
(moves to `closed/<turn_id>/` with `abandoned.json`). No
auto-reaping — see §8.

## 6. Atomicity

The answerer writes `response.json.tmp`, then renames to
`response.json` (atomic on POSIX). dsys only ever reads
`response.json` — no torn reads, no new machinery; filesystem
semantics suffice. Partial-write discipline is the answerer's
business and is documented in the protocol, not enforced by dsys.
v0 declares POSIX local filesystem (F-D3).

## 7. Trust posture (honest limits)

- **The answerer is untrusted.** `response.json` is parsed
  against a strict schema; wrong `turn_id`, missing `text`, or
  malformed JSON = failed turn. The parsed-never-trusted rule
  applies unchanged downstream (scenario driver, referee).
- **Role binding stays advisory.** dsys *offers* the system
  prompt in `prompt.json`; whether the answerer *used* it is
  unobservable. `prompt_hash` attests to what was offered, not
  what was consumed. Stated, not solved.
- **Response authenticity is declared trust.** Nothing binds
  `response.json` to `prompt.json` except the `turn_id` match
  plus local-filesystem trust. A swapped response is
  undetectable in v0.
- **`backend_name` / `model` are self-reported claims.** The
  transcript records them as claims — which is still strictly
  more than S2's shell backend records about its configuration.

## 8. The clock question

The architecture models no clock (DR-5): no timeout *entities*,
no time-based *validators*. The dialog timeout is wall-clock
*inside the CLI process*, used only for its own run record
(`started_at`, `duration_ms` — already wall-clock in the spec'd
envelope). This is operational behavior, not an architectural
entity; no validator ever sees it. The rule is: the CLI may use
wall-clock; the architecture may not depend on time. Orphaned
turns are therefore surfaced (`dialog status`), never
auto-reaped — reaping would be the CLI inventing architectural
time.

## 9. Hermeticity result

New row for the installer spec's §4 table:

| `execute --backend dialog` | never | file I/O on the local tree only |

The network surface, if any, belongs entirely to the external
answerer, which is not dsys. `doctor`'s hermetic check stays
green; `dialog`'s `probe` is "var/dialog writable" — no PATH
dependency, so `execute` becomes usable with zero external setup.
This also repairs the installer preflight story: `stub` keeps
install green today; `dialog` keeps *use* green.

## 10. Relation to the scenario driver

The phase-2 driver composes dialog turns unchanged: each YAML
turn becomes one `execute --backend dialog`; fail-fast and
transcript logic sit on top. The transcript gains an honest
property no other backend offers: the exchange *is* the files,
so transcript re-validation covers the full dsys↔answerer
exchange, not just dsys's side of it.

## 11. Worked example

```
$ dsys execute --as cos "drain the queue" --backend dialog
# dsys writes var/dialog/pending/dlg_9f3a41c7e2b0/prompt.json, waits
# … external answerer (human, poll loop, other dsys) writes response.json …
<the answer text>

$ dsys execute --as cos "drain the queue" --backend dialog --format json
{"tool": "dsys", …, "data": {"role": "cos", "role_hash": "sha256:…",
  "prompt_hash": "sha256:…", "backend": "dialog", …}}

$ dsys dialog status
pending: dlg_9f3a41c7e2b0 (cos, waiting)
```

## 12. Falsifiers (pre-registered)

- **F-D1** — "dialog preserves dsys's hermeticity": falsified if
  the dialog adapter performs any network I/O. Test: run
  `execute --backend dialog` with networking disabled; must work.
  The adapter is file-I/O-only by inspection.
- **F-D2** — "files suffice as a turn transport": falsified if
  any turn needs dsys→answerer communication richer than
  (system, prompt), or answerer→dsys richer than (text,
  refusal). Streaming / progress updates would falsify v0.
- **F-D3** — "atomic rename suffices": falsified by a
  non-POSIX filesystem or network mount without atomic rename.
  v0 declares POSIX local fs.
- **F-D4** — "dialog is a backend, not an agent": the standing
  redirect from S4. Calling dialog an "inferencing agent" is the
  category error this protocol exists to avoid.
- **F-D5** — "timeout needs a modeled clock": resolved by §8
  (wall-clock scoped to the CLI process). Falsified only if a
  validator or entity ever depends on dialog timing.

## 13. Build order (exploration only — not approved)

1. `backends.py`: `Backend` protocol + `dialog` + `stub`
   adapters (packaging spec §3).
2. `cmd_execute` dispatch on `backend:` / `--backend` (today:
   unconditional exit 2 — S1).
3. `dsys dialog status` / `dialog abandon`.
4. Installer: `var/dialog/` at 0700; hermeticity table row (§9);
   preflight note.
5. The answerer is never dsys's code. A reference poll-loop
   answerer may be shipped as an example, never as the mechanism.
