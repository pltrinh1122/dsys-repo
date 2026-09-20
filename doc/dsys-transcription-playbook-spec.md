# dsys-transcription-playbook — spec

Status: specified 2026-09-20. Not ratified; implementation not
approved (rides the dialog protocol's exploratory status).

The third playbook, following the pattern of the decision-making
playbook (§8.2, dyad-architecture-doc) and the dsys-mutation-playbook:
a **set of definition-of-done conditionals** (never a sequence), with
its own gates, writing the shared DecisionRecord entity
(discriminated by `playbook`), disposed through the single
disposition machinery. Playbooks proliferate; disposition doesn't.

Matter: **whether raw operator text has been converted into typed
records fit for the deterministic core** — the transcription
function, raw → typed, governed as DoD conditionals rather than as
the step-sequence §14.1 was first captured in. (That sequential
capture violated the standing rule — "a playbook isn't a sequence
but a set of definition-of-done conditionals" — this spec is the
repair.)

Inherits from dialog-protocol-spec §14/§14.1/§15/§16.4, not
duplicates: the three keys, the Ambient Originated Sequence, the
performer taxonomy (`human` | `ambient` | `api`), F-AO-1, R1–R5,
I1–I3, and the disposition coverage rule. What this spec adds is
the playbook form: gates, terminal conditions for every path, and
the mechanical closure that makes the ratified-authorized
invariant checkable.

**Term justification.** "Transcriber" names the playbook, not a
renderer. Nothing in this playbook performs inference: on the LLM
paths the ambient/api renders *within a playbook step*, in
response to a dsys-issued record, exactly as §14 requires. The
playbook's definitional job is the gate — the DoD under which a
transcription matter may STOP with records the core may operate
on.

## 1. START — "open candidacy"

*When:* raw operator text arrives and satisfies dsys's wait state
(§15.7), with no transcription yet performed.

- Frame the matter: the raw text (cited by transcript/turn id),
  its arrival interface (chat | CLI).
- State the gates before evaluating. Inherited: **G1**
  well-formed, **G2** legitimate source, **G3** non-redundant,
  **G4** actionable. Transcription-specific:
  - **T1 determinism** — is the raw text deterministically
    parseable (valid typed syntax, CTA grammar)? If yes, no
    inference turn runs: parse directly, validate shape, STOP
    by parse (§3). Inference where parsing suffices is
    refused, not merely discouraged (F-T4).
  - **T2 performer binding** — who performs the transcription:
    `human` (the operator hand-composed typed input at the
    CLI — no inference occurs, validate and STOP by
    composition), `ambient`, or `api`. An LLM performer
    renders *only* in response to a dsys-issued record; a
    transcription with no issuance behind it fails G2
    (no self-instruction, §14).
  - **T3 request-type fit** — the transcription turn, when one
    runs, is issued as a `goal`-type `inference_request`
    (§15.1): the front-door type, `input.prompt_text` = the
    raw text, result-only.
  - **T4 issuance validity** — R1–R5 pass. Failure: the
    matter never STARTs (STOP/unstarted, §3); dsys must not
    issue, the ambient must not process.
- G2 kills matters whose "raw text" did not originate with the
  operator — the ambient volunteering a transcription, a
  replayed transcript presented as a new arrival.

*Done when:* the matter is framed (raw text cited, interface
noted, T1/T2 routed, the `goal` request issued or the
parse/compose path taken) — and nothing is transcribed yet.

## 2. STOP — terminal conditions (all paths, not just success)

*When:* a gate fails, a disposition is recorded, the turn is
abandoned, or issuance was refused.

- **STOP/done** — the invariant, as a DoD: the ingested record
  cites (a) a `ratify`-mode DecisionRecord
  (`playbook="dsys-transcription-playbook"`, decision Y on the
  transcribed content, citing the `goal` request's
  `request_id`) — *ratified*; and (b) a `process authorization`
  covering the turn — either a fresh `authorize`-mode
  DecisionRecord citing the same `request_id`, or a
  `set_standing` DecisionRecord whose recorded scope
  (domain + principal + turn kind) provably covers it
  (§16.4b) — *authorized*. Citations resolve (cite-vs-verify);
  I1–I3 pass; the record validates. Only then may the core
  operate on it. This is the mechanical form of
  "ratified-authorized."
- **STOP/refused** — write disposition N: no records written,
  nothing ingested. The refusal is recorded in the transcript
  (covered by the process authorization, I3); the matter is
  terminal without ingestion.
- **STOP/parsed** — T1 path: the deterministic parse output,
  shape-validated. No inference occurred, no renderer exists,
  so no disposition debt: ingested as operator-authored.
- **STOP/composed** — T2 `human` path: the operator's
  hand-composed typed input, validated (R1–R5). The
  composition is the operator's act; ingested as
  operator-authored.
- **STOP/abandoned** — `dialog abandon`: terminal, no write
  disposition, nothing ingested.
- **Never-STARTed** — T4 failure: dsys must not issue; the
  matter closes at START with the failed validator cited.

*Done when:* the matter's terminal state is recorded with its
reason — done, refused, parsed, composed, abandoned, or
unstarted — each naming what it cites.

## 3. KEEP — "await the keys"

*When:* the matter is open on the LLM path (T2 =
`ambient`/`api`), between issuance and STOP.

- The driver holds the matter: process authorization awaited
  → rendering → write disposition awaited (Y/N/counter) →
  ingest. Each key is fresh per turn (no self-instruction,
  §14); a `counter` re-renders and requires a fresh
  disposition on the new draft — the old disposition never
  carries forward (freshness; F-T6).
- Orphaned turns (authorized, rendered, never disposed) are
  surfaced, not reaped (§5 turn lifecycle): KEEP does not
  time out into STOP.
- Run **G5**: binding vs provisional/advisory. Binding: the
  STOP/done DoD — mechanically checkable via citations +
  validators (I-18). Advisory: fidelity judgments ("is this
  transcription faithful?") — human judgment, recorded in the
  disposition, never validated.
- Enforce **G6**: uncertainties tagged — notably, the
  authorized-half check is transcript-captured today, not
  ingest-gated; making it mechanical (I-18) is specified
  here, not yet built.
- Write the DecisionRecords: `playbook=
  "dsys-transcription-playbook"`, matter, raw-text citation,
  performer, T1/T2 gate trail, the `authorize`-mode record
  (process authorization or the covering `set_standing`
  citation) and the `ratify`-mode record (Y/N/counter on the
  content), consequences, uncertainties, timestamp.
- Submit through the single disposition machinery:
  - **ratify** — adopt the transcription (write it).
  - **authorize** — grant processing of the turn. (The two
    keys are two modes, not two votes on one mode.)
  - **triage** — the text is ambiguous
    (`needs_clarification`, §15.1 `goal` result); exactly one
    outcome per the triage DoD.
  - **overrule** — the operator overrides a gate routing
    (e.g. T1 said "parseable," the operator insists on LLM
    transcription); reason recorded.
  - **set_standing** — standing process-authorization scope
    (domain + principal + turn kind). **It may never cover
    the ratified half**: a standing pre-ratification of
    unseen content violates freshness — the write
    disposition authorizes *this content now* (F-T2).
- Unratified = draft = not a decision (proposer ≠ disposer);
  undisposed = unwritten (ambient proposes, Operator
  disposes).

*Done when:* both key-records are complete per above and the
dispositions recorded, or the matter has left KEEP for a STOP
state.

## 4. Mechanical closures

- **I-18 (transcription-record closure):** an ingested
  transcription record (LLM path) must cite (a) a
  `ratify`-mode DecisionRecord with
  `playbook="dsys-transcription-playbook"`, decision Y,
  citing the `goal` request's `request_id`; and (b) either a
  fresh `authorize`-mode DecisionRecord citing the same
  `request_id`, or a `set_standing` DecisionRecord whose
  recorded scope covers the turn. A `set_standing` citation
  never satisfies (a). The validator checks citation
  resolution and scope containment — completeness of the
  declaration, not its truth (declared trust, cf. I-17/F-M4).
- Exactly one transcription matter per raw-text arrival
  (G3); the records are citable (E1) like any
  DecisionRecord.

## 5. Worked example

Matter: operator chats "summarize open disclosures and propose
a triage order."

- START: raw text cited (chat interface). T1: open prose, not
  deterministically parseable — inference turn required. T2:
  `ambient` (chat arrival). T3: `goal` request issued,
  `input.prompt_text` = the message. T4: R1–R5 pass.
- KEEP: "process next" observed → `authorize`-mode
  DecisionRecord citing `request_id`. Ambient renders
  intent + goal mapping + advisory `follow_ons`. Operator
  dispositions Y → `ratify`-mode DecisionRecord.
- STOP/done: ingest — I1–I3 pass; I-18: both citations
  resolve. The structured result re-enters the machine;
  follow-on `propose` requests cite it in `input.matter`
  (§15.8).
- Contrast: operator dispositions N → STOP/refused — no
  records, refusal in the transcript. Operator chats
  `{"triage": ["d1","d2"]}` → T1: parseable → STOP/parsed,
  no turn, no dispositions.

## 6. Relation to the other playbooks

| | decision-making (§8.2) | dsys-mutation | transcription (this spec) |
|---|---|---|---|
| shape | DoD conditionals, START/STOP/KEEP | same | same |
| gates | G1–G6 | G1–G4 + M1–M4 | G1–G4 + T1–T4 |
| record | DecisionRecord | DecisionRecord, `playbook` discriminated | DecisionRecord, `playbook` discriminated |
| disposition | ratify/authorize/set_standing/overrule/triage | same five modes | same five modes; bound per §3 (ratify = content, authorize = processing, set_standing = processing-scope only) |
| closures | I-2, I-11, I-12, … | + I-17 | + I-18 |

The transcription playbook does not duplicate disposition,
records, or closures — it specializes the matter and the
gates. It replaces the sequential reading of §14.1; §14.1's
content (trigger, delivery-vs-transcription correction,
performer taxonomy, F-AO-1) is inherited.

## 7. Pre-registered falsifiers

- **F-T1:** the playbook cannot make a transcription faithful
  — only disposed. A Y on a mistranscription is the
  operator's recorded error, not a prevented one. (Mirrors
  F-M1: declare, don't prevent.)
- **F-T2:** `set_standing` never satisfies the ratified half.
  Any reading permitting standing pre-ratification of unseen
  content fails against freshness (§14).
- **F-T3:** the ambient never judges STOP/done on its own
  rendering — executor split (§3, KEEP). A STOP/done citing
  only ambient acts is malformed.
- **F-T4:** deterministic parse is not transcription by
  inference. Routing T1-parseable input through an LLM turn
  violates T1 — waste plus untrusted rendering where none
  was needed.
- **F-T5:** "the playbook is fully operable today." False —
  it rides the dialog protocol's exploratory status. The
  decision/record pattern exists; the turn loop, the
  authorize/ratify DecisionRecord filing, and I-18 do not.
  (Mirrors F-M6.)
- **F-T6:** `counter` is not terminal. A countered draft
  returns to KEEP; the re-render needs a fresh disposition.

## 8. Applicability

Specified, not ratified, not approved for implementation.
Operable today: the DoD conditionals as governance and the
decision/record pattern they specialize. Specified, not
built: the turn-loop execution, DecisionRecord filing for
both keys, I-18. Blocking gap carried forward: a chatless
(CLI-only) deployment has no channel for the two human keys
— `dialog authorize` / `dialog dispose` do not exist —
so LLM-path transcription matters cannot reach STOP/done
there. (The door-2 authority-chain finding.)

## 9. Reason classification

Applies as spec'd (§10, dsys-mutation-playbook-spec): every
transcription matter states its reason. In practice the
reason is `accepted` — evidenced by the filed raw text in
the transcript (the arrival is the evidence). Whether the
classifier generalizes beyond mutation matters remains
G6-tagged there; this spec assumes it does, provisionally.
