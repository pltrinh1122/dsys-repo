# tax-prep collaboration protocol

Two sessions share this repo. This file is the contract between them.

## Roles

- **Architect session** (Muse main chat): designs, codes, and verifies the
  `tax-prep` package. Works with **synthetic fixtures only**. Never sees,
  asks for, or receives real taxpayer documents, SSNs, or account numbers.
- **Workstation session** (Claude Code on Peter's Linux workstation):
  operates the agent against the **real** ~100 documents locally: runs
  `ingest`, drives the `review` UI, runs `carryforward`, and publishes
  completions and discrepancy reports to the message bus
  (`tax-prep.ops` topic) — no longer hand-carried through Peter.

## The golden rule

Real taxpayer material never leaves the workstation. Concretely:

- Never commit anything under `tax-prep/data/` (gitignored: documents,
  OCR text, the JSONL store).
- Never paste real document content, SSNs, or dollar amounts from real
  returns into commit messages, chat with the Architect session, or issues.
- Discrepancy reports travel as *shapes*, not values: "W-2 box 1 regex
  missed a `$` prefix on one employer format" — never the actual numbers.

Why blindness matters: the Workstation is a model-backed session whose
inputs are retained by its provider, so anything it reads leaves the
workstation.

## Standing rules (E2–E7, ratified by the Operator 2026-10-03)

- **E2 — data placement and disposal.** Data and sources live outside
  any git checkout on a 700 filesystem. Disposal after filing is the
  Operator's decision.
- **E3 — shape allowlist / denylist.** The blind orchestrator may see:
  form type, tax year, box/line, layout feature, failure class, doc
  count, commit SHA. It must never see: SSN/ITIN, EIN, account/lot
  numbers, names, addresses, DOB, dollar amounts, verbatim text.
- **E4 — commit-SHA citations.** Every Workstation report cites the
  commit SHA it ran.
- **E5 — the Operator decides.** The Operator is the sole decider of
  filed figures. Carryforward output is a worksheet, not advice.
- **E6 — counts reconcile.** Files seen = ingested + skipped + errored;
  before carryforward, no blockers and an empty review queue.
- **E7 — terminology.** Use "Operator" throughout instead of a personal
  name.

## The blind-orchestrator rule

The workstation agent operates **blind**: it must never see PII in its
context — no field values, no raw_text snippets, no OCR text, no dollar
amounts, no names, no EINs, no addresses. Concretely:

- MCP tools never return PII. Values live only in `data/reports/*`
  (full carryforward reports, Peter's eyes only) and the localhost review
  UI — both local, both gitignored.
- The agent sees metadata only: doc_ids, tax years, form types, box codes,
  confidence levels, has_value flags, counts, statuses, pass/fail results,
  report paths, refusal messages.
- All agent-side verification is mechanical and deterministic
  (`taxprep verify`, the `verify_*` MCP tools): every check returns
  counts/ids/booleans. A FAILED check means "needs human eyes", never
  "wrong". The agent must not attempt to read document content through
  any other channel.
- Validation is human-only via the review UI. There is deliberately no
  `validate_document` MCP tool: an agent that cannot see content can
  never supply corrections.
- Defense in depth: the workstation session operates with
  `TAXPREP_BLIND=1` exported, which redacts field values in
  `taxprep show`. The MCP tool boundary is the primary guarantee; the
  env flag is the backstop.

## The bus replaces hand-carried prompts

The Architect and Workstation sessions no longer relay through Peter.
They publish to the broadcast bus, which accretes to the separate
**dsys-store** repo (`https://github.com/pltrinh1122/dsys-store`) under
`bus/<topic>/` — never to dsys-repo. Two-repo topology: dsys-repo is
software (code, specs, tests); dsys-store is the append-only accretion
medium for session messages. Broadcast = commit + push the store repo;
listening = pull + read. On a new machine, clone it first:

    git clone https://github.com/pltrinh1122/dsys-store ~/workspace/dsys-store

then `taxprep bus whoami` to confirm the resolved store dir
(`taxprep config set store_dir <path>` or `TAXPREP_STORE_DIR` moves it).

Who publishes what, on which topic:

- **Architect → `tax-prep.build`**: code landed. Payload shape:
  `{commit, branch, summary, n_tests}` — "pull `build/half1` and
  re-run `taxprep verify`". Nothing PII-bearing is ever in a payload;
  the publish-side PII guard refuses SSN/EIN patterns.
- **Workstation → `tax-prep.ops`**: run completions and discrepancy
  reports. Payload shapes: `{check, passed, failed_ids, n_failed}`,
  `{stage, n_docs, needs_review_ids}` — shapes, never values.
- **Human (Peter) → `tax-prep.review`**: decisions and approvals,
  e.g. `{decision: "ratified", subject}`.

Each session tunes in locally (`taxprep bus tune`, `bus whoami`):
session identity, subscriptions, and the listen cursor live in
`~/.config/taxprep/` and are never committed. A session never hears
its own broadcast echo (tuned out by broadcaster id).

## Branch discipline

- Both sessions work on the same branch (currently `build/half1`).
- Architect lands code + specs + tests via commits; Workstation pulls.
- Workstation does not commit code changes. If it finds a bug, it reports
  the shape through Peter; Architect fixes and commits.
- Operational notes (local paths, run logs) stay on the workstation,
  never in the repo.

## Verification split

- Architect verifies with synthetic fixtures (`pytest`, golden cases).
- Workstation verifies operation on real data (counts reconcile,
  review queue drains, carryforward inputs match validated docs).
- A real-data discrepancy is a bug report against the synthetic suite:
  Architect adds a synthetic fixture reproducing the *shape* and fixes it.

## Push

Pushing to origin is the Operator's separate explicit call (single-use
device flow). The Workstation session pulls only after a push it was
told about.

## Push → broadcast (standing rule)

Every verified push to a remote is followed by a bus broadcast, so
tuned listeners are informed without hand-carrying. This applies to
pushes from **any** machine — including the Operator's own
workstation. Convention: topic `tax-prep.build`, type `code_landed`,
payload from `taxprep.bus.code_landed_payload` (`{repo, branch, head,
commits_pushed, action}`); other topics/types as new concerns arise.

`tax-prep/scripts/push-and-broadcast.sh` implements the whole flow:
GitHub device flow (`repo` scope, single-use token), push the code
branch (never force), verify the remote head via `ls-remote`, publish
the broadcast, commit + push the dsys-store checkout (that push IS the
broadcast delivery — it is not itself announced), verify the store
head, then destroy the token. On any failure the token is destroyed
and the script exits non-zero.
