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
human-authorized. Authority is write-gated: the ambient never
publishes; publication is the Operator's act performed through
the ambient's hands.

1. **dsys issues** an `inference_request` record (§15) as
   `pending/<turn_id>/prompt.json`. The issuer is a deterministic
   component (`issued_by`: `scenario-driver`, `flow-scheduler`,
   or `operator-cli` for a typed ad-hoc request) — never the
   ambient itself, never chat prose.
2. **The human authorizes processing** in chat: "process next
   inferencing request record issued by dsys." Authorization,
   not authorship.
3. **The ambient infers and stages drafts** — draft content, not
   records. Nothing is written to `pending/<turn_id>/` yet.
4. **The human dispositions the draft content** (Y/N/counter) —
   the write disposition. Only now may records be written.
5. **The ambient writes** `pending/<turn_id>/response.json` +
   `pending/<turn_id>/artifacts/*.json`. Every record cites
   `request_ref: <request_id>` (what requested it) and
   `disposition_ref: <disposition-id>` (who authorized the
   write). Because the write itself was disposed, the content
   carries the Operator's authority.
6. **dsys ingests**: verifies each `disposition_ref` resolves to
   a recorded disposition — cite-vs-verify: dsys checks the
   citation resolves (a shape check); it does not re-adjudicate
   the Operator's judgment — validates each artifact against
   the request's `output_contract` plus the package validators,
   validates the typed `result` (§15), stages candidate state,
   runs `referee validate`, and advances the FSM — which may
   issue the next request.

Properties:

- **Three keys.** Issuance (system) + process authorization
  (human) + write disposition (human). The ambient can invent
  no work, start no work, and publish no records.
- **Transcribes, never decides — and never publishes.** On "Y",
  the ambient writes what was disposed, nothing more.
- **Instruction content is auditable.** It was never chat prose:
  a typed system record with `request_id`, `request_type`, and
  hashes. The transcript captures the full chain: request →
  process authorization → draft → write disposition → records →
  validation.
- **No self-instruction.** Each turn requires a fresh
  dsys-issued record, a fresh process authorization, and a
  fresh write disposition.
- **Freshness collapses structurally.** The write disposition
  authorizes *this content now*; the staleness window between
  authorization and write is ~zero by construction.
  (`state_ref` binding still governs what the content *claims
  about* the state.)
- **Scope creep dissolves for the per-write case.** Each write
  is individually disposed — there is nothing to creep.
  Carried-forward authority survives only for standing
  dispositions (§16.4b), which keep their scope check.
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
| `propose` | `{matter: str, constraints: [str], kinds: [record-kind]}` | the listed architecture record kinds | `{proposals: [{kind, file}]}` — pointers to `artifacts/` files; plus optional `plan` (§16) |
| `classify` | `{item_ref: str, taxonomy: [str, …] (≥2), context?: str}` | kinds in `output_contract`, if any | `{item_ref, class: <one of taxonomy>, rationale: str}` |
| `triage` | `{item_refs: [str, …]}` | `DecisionRecord` (triage mode) | `{dispositions: [{item_ref, disposition: acknowledged\|escalated\|dissolved, response: str}]}` |
| `assess` | `{subject_ref: str, criteria: [{id: str, text: str}]}` | kinds in `output_contract`, if any | `{findings: [{criterion_id, finding: pass\|fail\|na, note: str}]}` |
| `challenge` | `{claim: str, context?: str}` | kinds in `output_contract`, if any | `{verdict: survives\|falsified\|decomposed, reasoning: str, breaking_case?: str}` |
| `goal` | `{prompt_text: str, goal_refs?: [str] (default: the active goal set), context?: str}` | none — result-only (`"output_contract": []`) | `{intent: str, goal_mapping: [{goal_ref: str, relation: advances\|contradicts\|unrelated, note: str}], needs_clarification: bool, clarification?: str, follow_ons: [request_type…] (advisory)}` |

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
- **R3** — `output_contract` ⊆ the type's allowed kinds. It may
  be explicitly empty, meaning result-only: the type's output is
  the typed `result` alone, and I1 rejects any artifact files for
  the turn. (`goal` is result-only in v0.)
- **R4** — `role` resolves to a sealed bundle; `role_hash`
  matches.
- **R5** — no freeform instruction field. All instruction
  content lives inside `input`; the record carries exactly the
  known fields. Note the boundary this draws: a type's
  freeform-text *subject* (a `challenge` claim, an `assess`
  subject, a `goal` prompt_text) is data being interpreted, not
  instruction. The instruction is the typed request itself.

### 15.4 Ingest validators (ambient output, I1–I3)

- **I1** — every file in `artifacts/` has a kind ∈
  `output_contract`, else the turn's artifacts are rejected.
- **I2** — every artifact cites `request_ref == request_id`
  and `disposition_ref` resolving to a recorded disposition
  (the write disposition, §14). dsys verifies the citation
  resolves; it does not re-adjudicate the Operator's judgment.
- **I3** — `response.json` cites `request_id` and the write
  `disposition_ref`; its `result` matches the type's result
  schema; `refusal: true` → exit 4. (A refusal reports the
  authorized processing's outcome, so the process authorization
  covers its write — no separate write disposition needed.)

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

### 15.7 Startup: the first record

`goal` is the front door: the only type whose subject is raw
user text, and whose job is converting the untyped outside into
the typed inside. The startup pattern:

1. dsys's first record is a wait state: awaiting a text prompt
   from the user. (No inference is issuable until it arrives —
   there is nothing to interpret.)
2. On arrival, dsys immediately issues a `goal`-type
   `inference_request` with the prompt as `input.prompt_text`.
3. The ambient returns intent + goal mapping + advisory
   `follow_ons`.
4. The FSM acts on the result by issuing further typed requests
   (`propose`, `assess`, `challenge`, …) — issuance remains
   dsys's; in ambient mode each issuance still requires the
   human's authorization (§14).

The user's text never becomes an instruction (R5): it is the
subject of a typed intent-understanding request, and only the
structured result re-enters the machine. `goal_refs` cite goals
by id/label from whatever goal store backs the installation;
the spec does not define the store — that binding is declared
per deployment.

### 15.8 Goal-result persistence (P0)

The `goal` result needs no new entity. It persists as the turn's
closed transcript (`closed/<turn_id>/`: `prompt.json` +
`response.json` + `envelope.json`) — the full exchange, citable
by `request_id`. Follow-on `propose` requests cite it in
`input.matter` (e.g. `"matter": "goal classification req_…: …"`);
the driver resolves the citation from the transcript. "dsys
records goal classification" means: the result is retained as a
closed turn, addressable by its request id. (Rejected: a
`GoalClassification` entity — unnecessary ontology for what the
transcript files already do.)

## 16. Plans and initiation (P4)

The ratified sequence is goal → propose → **dispose** →
initiate-through-gates. This section specs the last two links:
the plan's form and the initiation path. DR-1 and the
step-change discipline are unchanged — they are the gates the
path routes through.

### 16.1 Plan schema

Planning is proposing a course of action: no new request type.
`propose`'s typed `result` gains an optional `plan` field — a
list of initiations:

```json
"plan": [
  {"kind": "initiate_harness_run" | "initiate_automaton_run" | "initiate_flow_run",
   "principal_ref": "dyad leo",
   "params": { "...": "per-kind initiation parameters" },
   "rationale": "why this initiation serves the matter"}
]
```

I3 validates the plan shape (known kinds, well-formed entries).
A plan whose shape needs a fourth kind is F-P1: amend the
schema, never smuggle it.

### 16.2 Principal binding

Validator on the plan (checked before disposition): every
initiation's `principal_ref` resolves to a dyad-or-human
principal — agents excluded, per the schema's Principal
definition. Unresolvable → malformed plan → the turn fails
before it can be disposed. (Closes P2's "whose slot": the plan
declares it, the validator checks it.)

### 16.3 The initiation path

After human disposal approves the plan, the driver executes the
initiations sequentially, each through its real gate:

- **harness run**: strap gates, then the DR-1 slot check for
  (`principal_ref`, scope). Slot free → initiate; slot taken →
  I-9 refusal, recorded with the blocking run named. The driver
  continues to the next item — partial fulfillment, honestly
  reported, never silently truncated.
- **automaton run / flow run**: the scheduler's step-change
  gate. The plan's disposition satisfies the human-in-the-loop;
  the scheduler still performs its declared duties
  (idempotency, trigger routing per the flow spec).

Each attempt appends to the run record (the new
`HarnessRun`/`AutomatonRun`/`FlowRun`, or the refusal). The
turn's fulfillment report lists per item: stood up, or refused
and why.

### 16.4 Disposition coverage rule

No initiation without coverage — the mechanical form of the
restored human link. Coverage is either:

- (a) a fresh disposition `DecisionRecord` citing the plan's
  `request_id` (mode `ratify` or `authorize` as appropriate),
  or
- (b) a `set_standing` disposition whose recorded scope
  (domain + principal + initiation kind) provably covers every
  initiation in the plan.

Under write-gated authority (§14), clause (a) is the natural
case: the write disposition that authorized the plan's records
is recorded as the DecisionRecord citing the plan's
`request_id` — the plan arrives at initiation already carrying
its authority, and the driver verifies the citation. Clause (b)
is the only carried-forward case and keeps its scope check.

The driver checks coverage before the first initiation. No
coverage → no initiation, plan parked, reported. Standing
authorization may displace the human link in time; it may not
remove it.

### 16.5 Falsifiers

- **F-P1** (schema sufficiency): falsified by a needed
  initiation shape the plan schema cannot express. Remedy:
  amend §16.1 — never smuggle it as prose in `rationale`.
- **F-P2** (gate integrity): falsified by any plan path that
  initiates without passing DR-1 (harness) or the step-change
  gate (automaton). Such an initiation is a violation, not a
  shortcut.
- **F-P3** (standing-scope creep): falsified by citing a
  `set_standing` disposition for initiations outside its
  recorded scope (domain/principal/kind). Coverage is checked
  against what was recorded, not what is claimed.
