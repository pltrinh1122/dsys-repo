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
needs no access to the install tree). This is the transport form
of the `inference_request` record — its shape and constraints are
defined in §15; the form below is illustrative:

```json
{
  "request_id": "req_9f3a41c7e2b0",
  "turn_id": "dlg_9f3a41c7e2b0",
  "dialog_id": "dlg-thread-7",
  "in_reply_to": null,
  "request_type": "propose",
  "role": "cos",
  "role_hash": "sha256:…",
  "system": "<full role system prompt text>",
  "input": {
    "matter": "<the matter, in the type's schema>",
    "constraints": ["…"],
    "kinds": ["DecisionRecord"]
  },
  "output_contract": ["DecisionRecord"],
  "issued_by": "scenario-driver"
}
```

There is no freeform prompt string: all instruction content
lives inside the request type's input schema (§15). A record
with an untyped instruction field is malformed.

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

## 14. Ambient-inferencing mode

The inferencing agent is ambient (in-session, unconfigured — the
S5 backend), and every turn is both system-specified and
human-authorized:

1. **dsys issues** an `inference_request` record (§15) as
   `pending/<turn_id>/prompt.json`. The issuer is a deterministic
   component (`issued_by`: `scenario-driver`, `flow-scheduler`,
   or `operator-cli` for a typed ad-hoc request) — never the
   ambient itself, never chat prose.
2. **The human authorizes** in chat: "process next inferencing
   request record issued by dsys." Authorization, not authorship —
   the human dispositions, never composes freeform instructions.
3. **The ambient processes**: reads the request record, infers,
   writes `pending/<turn_id>/response.json` +
   `pending/<turn_id>/artifacts/*.json`. Every artifact cites
   `request_ref: <request_id>`; the response cites it too.
4. **dsys ingests**: validates each artifact against the
   request's `output_contract` plus the package validators,
   validates the typed `result` (§15), stages candidate state,
   runs `referee validate`, and advances the FSM — which may
   issue the next request.

Properties:

- **Two keys.** Issuance (system) + authorization (human). The
  ambient can neither invent work (no dsys-issued record →
  nothing to process) nor start work (no human authorization →
  the record sits in `pending/`).
- **Instruction content is auditable.** It was never chat prose:
  a typed system record with `request_id`, `request_type`, and
  hashes. The transcript captures the full chain: request →
  authorization → response → artifacts → validation.
- **No self-instruction.** The ambient never chains turns
  autonomously; each turn requires a fresh dsys-issued record
  and a fresh human authorization.
- **Disposition stays terminal and human.** On "Y", the ambient
  transcribes (writes the record), never decides.
- **The human's freeform channel is authorization-only.** An
  operator who wants ad-hoc inference composes through the
  typed request interface (`dsys dialog request --type …`),
  which dsys validates (§15, R1–R5) before issuing. The ambient
  only ever processes dsys-issued records.

## 15. `inference_request` record constraints

The request record is what makes ambient inference bounded: dsys
can only ask for what the enum can express, with the shapes the
enum declares. An instruction the enum cannot express is not
issuable — that is the constraint biting.

### 15.1 The closed enum

| `request_type` | input schema | ambient may write (`output_contract` ⊆) | typed `result` in `response.json` |
|---|---|---|---|
| `propose` | `{matter: str, constraints: [str], kinds: [record-kind]}` | the listed architecture record kinds | `{proposals: [{kind, file}]}` — pointers to `artifacts/` files |
| `classify` | `{item_ref: str, taxonomy: [str, …] (≥2), context?: str}` | kinds in `output_contract`, if any | `{item_ref, class: <one of taxonomy>, rationale: str}` |
| `triage` | `{item_refs: [str, …]}` | `DecisionRecord` (triage mode) | `{dispositions: [{item_ref, disposition: acknowledged\|escalated\|dissolved, response: str}]}` |
| `assess` | `{subject_ref: str, criteria: [{id: str, text: str}]}` | kinds in `output_contract`, if any | `{findings: [{criterion_id, finding: pass\|fail\|na, note: str}]}` |
| `challenge` | `{claim: str, context?: str}` | kinds in `output_contract`, if any | `{verdict: survives\|falsified\|decomposed, reasoning: str, breaking_case?: str}` |

- `triage` is distinct from `classify` because its grammar is
  fixed by the architecture (the triage CTA grammar), not
  supplied per-request.
- `challenge` is the dialectic falsification type: verdict +
  reasoning, with the breaking case required on `falsified`.

### 15.2 Excluded names

- **`decide` is not a request type.** The agent never decides:
  human disposition is terminal ("propose, never dispose"). A
  `decide` type would promise what the architecture forbids.
  The agent-side verb is `propose`; decision is recorded
  afterward, by the human's disposition.
- **`evaluate` is not a request type.** `evaluate` is reserved
  for deterministic expression-language evaluation (the
  architecture's mechanical evaluator). Inference-side judgment
  against criteria is `assess`. Sharing the name would let
  unevidenced judgment wear the authority of mechanical
  evaluation.

### 15.3 Issuance validators (dsys side, R1–R5)

- **R1** — `request_type` ∈ the §15.1 enum. Unknown type: the
  record is invalid; dsys must not issue it, the ambient must
  not process it.
- **R2** — `input` matches the type's schema exactly.
- **R3** — `output_contract` is non-empty and ⊆ the type's
  allowed kinds.
- **R4** — `role` resolves to a sealed bundle; `role_hash`
  matches.
- **R5** — no freeform instruction field. All instruction
  content lives inside `input`; the record carries exactly the
  known fields.

### 15.4 Ingest validators (ambient output, I1–I3)

- **I1** — every file in `artifacts/` has a kind ∈
  `output_contract`, else the turn's artifacts are rejected.
- **I2** — every artifact cites `request_ref == request_id`.
- **I3** — `response.json` cites `request_id`; its `result`
  matches the type's result schema; `refusal: true` → exit 4.

### 15.5 Extension rule

New types require a spec amendment plus issuance and ingest
validators. The enum is closed by validator (R1), not by
convention.

### 15.6 Falsifiers

- **F-R1** (sufficiency): falsified by a dsys component needing
  an inference shape no type covers. Remedy: spec the type —
  never smuggle it as untyped prose inside `input`.
- **F-R2** (type discipline): falsified by the ambient using
  one type to do another's job (e.g. `assess` rendering a
  claim verdict — that is `challenge`'s job). The result
  schema won't fit; ingest rejects. Types are honored by
  shape, not by trust.
- **F-R3** (exclusion standing): falsified if a future need
  genuinely requires agent-side `decide` — which would mean
  repealing "human disposition is terminal," a load-bearing
  invariant, not a naming choice.
