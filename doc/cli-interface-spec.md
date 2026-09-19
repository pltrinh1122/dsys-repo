# `dsys` CLI Interface — Design Spec

Spec-only. Nothing here is implemented. This specifies the complete
command-line interface: command tree, arguments, I/O contracts, exit
codes, JSON schemas, and config. Companion to
`agent-cli-packaging-spec.md` (which covers *what the tool is*);
this covers *exactly how it is invoked*.

## 1. Shape

```
dsys [--config PATH] [--backend NAME] [--format text|json]
           [-q|--quiet] [-v|--verbose] <command> [<args>]
```

- No interactive prompts, ever. Missing required input → exit 1.
- `--format json` is the stable machine contract; `text` is human
  output and may change between versions. Scripts must use json.
- stdout purity: in `text` mode, stdout carries *only* the
  command's primary output (agent text, view rows, file content).
  Diagnostics go to stderr. In `json` mode, stdout carries exactly
  one JSON envelope — including on failure (with `error` set).

## 2. Exit codes

| Code | Meaning |
|------|---------|
| 0 | ok (for `execute`: the agent ran; for `referee validate`: state clean) |
| 1 | usage / config / tool failure |
| 2 | backend failure (missing, crashed, probe failed at call time) |
| 3 | timeout (backend killed after `--timeout`) |
| 4 | agent refusal (the agent declined the task — first-class) |
| 5 | validation ran, violations found (`referee validate`) |
| 6 | scenario step failed (`scenario run`) |

Codes are part of the contract: a test-drive that can't tell 4
from 2 can't test refusal cases; one that can't tell 5 from 1
can't test validators.

## 3. Commands

### 3.1 `execute` — headless agent run under a role

```
dsys execute --as ROLE (--prompt TEXT | --prompt-file PATH)
                   [--timeout SEC] [--stream] [--max-tokens N]
```

- `--prompt-file -` reads the prompt from stdin (fully, under the
  same timeout — never blocks forever).
- `--stream`: forwards backend streaming to stdout as it arrives
  (text mode only; json mode buffers into the envelope).
- Role bundle resolution: `--as cos` → `roles/cos.md` +
  `roles/cos.json`; missing role → exit 1 naming the role.
- stdout (text): agent response text only. stdout (json): run
  envelope (§5). stderr: backend command, timing, warnings.

### 3.2 `roles` — inspect role bundles

```
dsys roles list [--format text|json]
dsys roles show ROLE [--format text|json]   # system prompt; json adds role_hash
```

### 3.3 `referee` — the machine judges

```
dsys referee validate --state FILE [--format text|json]
# exit 0 clean · exit 5 violations (each printed / listed)

dsys referee view --state FILE --view NAME [--format text|json]
# NAME in {open-disclosures, ...}: view registry, one pure function each
```

`validate` in json mode prints `{"state_file","clean","violations",
"core_hashes"}`. `view --view open-disclosures` renders
`verification_view()` rows.

### 3.4 `scenario` — test-drive runner (phase 2)

```
dsys scenario list
dsys scenario run NAME_OR_FILE [--transcript FILE] [--fail-fast]
                                     [--backend NAME] [--timeout SEC]
```

- Each step appends one JSONL record to the transcript (run
  envelopes for agent turns, validation results for referee
  turns). The transcript *is* the run record.
- `--fail-fast` (default): stop on first unexpected result.
- Exit 0: every step matched expectation. Exit 6: mismatch, with
  the failing step named on stderr (and in the transcript).

#### 3.4.1 Scenario vs script

A **scenario** is a declarative exercise specification: actors,
turns, inputs, and expectations (`{actor, input, expect}`). It says
*what should happen and what counts as passing*. A scenario never
executes itself; a driver interprets it, mediating every turn
through the proper channel (`execute --as <role>`) and judging
outcomes via `referee validate`. Replay is transcript
re-validation, never behavior re-execution.

A **script** is imperative code: it says *how*, with arbitrary
power — it can import anything, reach the network, write anywhere.
`dsys scenario run` executes a script file dumbly
(`subprocess.run([sys.executable, script])`); nothing about a script
declares what passing means, and nothing in the runner constrains
what it does. Shipped scenarios are inference-free by construction,
not by sandbox — the runner would happily execute a script that
phones an LLM.

Relation: a scenario may be *realized by* a script, but is never
*identical to* it. `share/scenarios/01-boot-diagnostic.py` is a
script carrying the "boot diagnostic" scenario; the scenario is the
named exercise plus its declared checks. The phase-2 target is
scenarios as data (YAML declarations interpreted by the driver),
with scripts demoted to one step-implementation kind among others —
invoked by the driver, mediated, and never trusted. Agent outputs
anywhere in this pipeline are parsed, never trusted.

### 3.5 `state` — state-file utilities

```
dsys state init --out FILE [--seed golden|empty]
# golden: build_state() equivalent; empty: blank SystemState

dsys state get --state FILE --collection NAME [--id ID]
# inspect what the agents wrote; json mode prints the records
```

### 3.6 `doctor` — self diagnostic

```
dsys doctor [--format text|json] [--strict]
# --strict: WARNs become failures (exit 1)
```

Checks (from scenario 01): python ≥ 3.10, core importable (+
module hashes), golden chain PASS / refusal count, fresh-state
boot clean, verification view empty, role bundles present,
backend probes, `~/.local/bin` on PATH. Each check prints its
fix hint on failure.

## 4. Config file — `~/.dsys/etc/config.yaml`

```yaml
backend: auto        # auto | claude-cli | stub | in-session
timeout_s: 300
format: text         # default output mode
roles_dir: ~/.dsys/lib/roles   # override bundled roles
core_pin: sha256:…   # optional: refuse to run if core hash differs
```

Precedence: flags > config > built-in defaults. `--config PATH`
points at an alternate file (per-scenario configs).

## 5. JSON schemas (stable)

Run envelope (`execute --format json`, also each transcript line):

```json
{
  "tool": "dsys", "tool_version": "0.1.0",
  "command": "execute",
  "role": "cos", "role_hash": "sha256:…",
  "prompt_hash": "sha256:…",
  "backend": "in-session", "backend_version": "…",
  "started_at": "2026-09-19T06:10:00-07:00", "duration_ms": 1234,
  "exit_code": 0, "error": null,
  "stdout": "…", "stderr": "…"
}
```

Validation result (`referee validate --format json`):

```json
{
  "state_file": "state.json", "clean": false,
  "violations": ["I-13: governance run cos2 closed with …"],
  "core_hashes": {"schema.py": "ed7e1251f2c5", "validators.py": "…",
                  "views.py": "…", "golden_run.py": "…"}
}
```

View result (`referee view --format json`):

```json
{
  "view": "open-disclosures",
  "rows": [{"id": "dis-1", "kind": "conflict", "text": "…",
            "seq": 4, "triage_in_flight": false}]
}
```

## 6. Worked examples

```sh
# CoS drains the queue; operator answers; referee judges
dsys execute --as cos --prompt-file drain-prompt.txt --format json \
  > turn-1.json
dsys referee validate --state state.json --format json
dsys referee view --state state.json --view open-disclosures
dsys scenario run scenarios/drain-duty.yaml --transcript runs/t1.jsonl
dsys doctor --strict
```

## 7. Falsifiers (pre-registered)

- **F-C1.** "Exit 0 from `execute` means the architecture
  accepted the output." False — 0 means the agent *ran*.
  Acceptance is `referee validate`'s verdict (exit 0 vs 5).
  Confusing the two repeats F1 at the interface level.
- **F-C2.** "Text output is scriptable." False — only
  `--format json` is contractual. Text may change; scripts that
  parse it are broken by design.
- **F-C3.** "json mode is just pretty text." False — json mode
  changes the stdout contract (envelope, always emitted, `error`
  field on failure). A json consumer that can't handle
  `exit_code != 0` with a valid envelope is incomplete.
- **F-C4.** Scope: if the scenario runner (3.4) never needs more
  than `execute` + `referee` + transcripts, `state get` and
  `roles show` are convenience, not contract — they may stay
  thin or be cut without touching the test-drive loop.

## 8. Falsification: "CLI reaches harness nodes (CoS and playbook),
   not run-book nodes" (2026-09-19)

**Verdict: FALSIFIED as stated.** Breaks on both halves.

**(i) There is no node addressing, and "playbook" has no
addressee.** `execute --as ROLE` addresses a *role prompt*, not a
node — there is no `--run-id`, no cos1-vs-cos2 targeting. CoS is
addressable *as a role* (bundle exists). But "playbook" matches
nothing: the decision-making playbook (§8.2) is a set of DoD
conditionals — a procedure you *follow*, not a node you command;
`CommonsPlaybook`/`Playbook` entities are definitions, not
running processes. (`AutomatonPlayBook` — the automaton plane's former
second name for the same executable unit — was collapsed into `RunBook`
2026-09-19; the "FSM orchestrating run-books" distinction was unmodeled.)
No playbook role exists in §3.2. The claim's first half
is true only for CoS, and only under "role," not "node."

**(ii) "Cannot" is too strong for run-books.** The CLI is a dumb
pipe (F1): nothing stops
`execute --as cos --prompt "run monthly-close step 5"`. The
interface has no automaton role and no run-book command, but
absence of a legitimate addressee is not prevention of the
attempt. The real boundary is downstream: such output has no
valid architectural effect — the package's zero-inference
posture gives it nowhere to land.

**Narrowed survivor.** The interface's *well-formed* surface —
roles {cos, operator, auditor}, scenario actors {cos, operator,
referee} — covers harness-plane agency only and offers no
run-book addressee. Misuse (prompting *at* run-books) is not
refused by the CLI but is architecturally inert. Required
follow-through (phase 2 driver rule): the scenario driver must
never translate agent output into automaton-plane records;
`--as <unknown>` exit 1 is registry hygiene, not architectural
enforcement, and must not be mistaken for it.

## 9. Falsification: "'dyad' ~ 'harness'" (2026-09-19)

**Verdict: FALSIFIED.** The dyad is the authority; the harness
run is the exercise. Four breaks:

**(i) Existence independence.** A dyad exists with zero harness
runs — d1 is born (birth_id, constitution) before hr1/cos1 open,
and persists with none open (the orphan-queue validator
contemplates exactly that state). The bond is a property of the
dyad, not of any run.

**(ii) Cardinality.** One dyad → many runs, including two
*concurrent* runs in different scopes (hr1 execution + cos1
governance in the golden state). An identity cannot be ~ to a
plurality it outlives.

**(iii) Reference direction.** `HarnessRun.dyad_id` is an FK *to*
`Dyad` (and Optional at that — a run need not reference any
dyad). The harness is defined in terms of the dyad, not vice
versa. What references X is not X.

**(iv) DR-1's "per".** DR-1 slots runs *per* (principal, scope):
a run is *per* a principal the way a session is *per* an
authority — the "per" expresses non-identity. Collapsing them
erases the very relation DR-1 governs.

**(v) The human problem.** The dyad includes the human as
constituent; the harness *mediates* human↔agent turns. If dyad ~
harness, terminal disposition authority sits inside the mediated
structure, collapsing the external check "human disposition is
terminal" relies on.

**Narrowed survivor.** The CLI's *operational surface* is
harness-plane agency (roles, runs, referee) — there are no
dyad-plane commands because the dyad is never *operated*, only
*participated in*. For the test-drive: the dyad is *exercised
through* the harness, not identical to it. (`dyad` as the CLI
name is fine — it names the thing being exercised, not the
thing being invoked.)

> Superseded 2026-09-19 by decision-making-playbook ratification:
> the CLI is renamed `dsys`. The parenthetical above stands as valid
> history — the denotation was fine — but operational confusion was
> reported at the prompt (`dyad <verb>` reads as addressing the Dyad),
> and documentation doesn't fix a daily-use misreading. `dyadctl`
> killed (retains the confusion prefix; `-ctl` promises control
> semantics the CLI avoids); `harness` killed (Harness.io ecosystem
> collision; over-narrow).

## 10. Falsification: "'principal' ~ Operator" (2026-09-19)

**Verdict: FALSIFIED as a general equivalence.** The schema's
own docstring is the first witness — `Principal`: *"The body a
run belongs to (a dyad or a human)."* A principal *may* be a
human; it is not *~* the human. Three breaks:

**(i) The disjunction.** The definition gives two cases, dyad or
human. The sole extant principal, pr-d1, is named "dyad leo" —
the dyad case. ~ claims identity in all cases; one
counter-case kills it.

**(ii) Schema typing.** Principals and humans are distinct
entity types in distinct collections (`principal_id` →
`principals`; `disposer_id` → `humans`). Even when the
principal *is* a human, the model types the principalship as a
separate role-entity — the human-as-authority-holder, not the
human. The schema refuses the collapse.

**(iii) The third term.** The disposition is proposer (agent) +
disposer (human), never the same. Both act *for* the principal.
If principal = the human disposer, the agent is a mere
instrument of the disposer — and no-self-ratify is otiose,
because there would be no second party to keep distinct. The
covalent bond (1+1>2, two parties) requires the principal to be
the joint enterprise both serve: the dyad.

**Side-finding.** This also retires the old open question
("principal: operator vs agent"): the schema's disjunction is
*dyad or human* — the agent is not a candidate principal. The
agent never holds a DR-1 slot; it acts *within* the principal's
runs.

**Narrowed survivor.** The operator is the principal's
*disposer* — the human through whom the principal's terminal
judgments are exercised — but principal ≁ operator. In the
single-dyad case the distinction is operationally invisible
(1:1:1 human/dyad/principal), which is why the equivalence
tempts. It bites in the fleet case: many dyads, many
operators — and the still-open question of whether the fleet
itself can be a principal.

## 11. Falsification: "dyad ~ Agent + Operator; harness ~
   Principal + agent" (2026-09-19)

**Verdict: both FALSIFIED as stated — and jointly incoherent.**
The "+" asserts additivity; the architecture asserts
superadditivity (1+1>2 *is* the bond). Worse, the two claims
compose into absurdity (see below).

**Claim 1 — dyad ~ Agent + Operator.** Falsified as an additive
identity:
- The `Dyad` entity *requires* `birth_id` and
  `constitution_ref`: a dyad has its own lifecycle and its own
  governing relation. Two strangers — an agent plus an
  operator with no bond, no constitution, no shared history —
  are not a dyad; the entity refuses them.
- Dyad-scoped joint products — intents, claims, knowledge
  units, and the principal "dyad leo" itself — belong to
  neither member alone.
- What survives is the *membership* claim: the dyad's members
  are exactly {agent, operator}, no third member. But the dyad
  is members + irreducible relation R (bond, constitution,
  common ground, joint principalship), R ≠ ∅.

**Claim 2 — harness ~ Principal + agent.** Falsified, by
dilemma over the schema's own disjunction ("a dyad or a
human"):
- If principal = human: claim 2 becomes harness ~ human +
  agent ~ dyad (by claim 1's membership reading) — which is
  exactly the dyad ~ harness already falsified in §9.
- If principal = dyad: substituting claim 1, harness ~
  agent + operator + R + agent. The agent is double-counted;
  "+" is not even idempotent. The notation is broken, not
  approximate.
- Category error underneath: principal and agent are *parties*
  (who); a harness run is a *structured process* — turns,
  conditions, threads, lifecycle, DR-1 slotting. The run is
  the *exercise*, not the sum of the exercisers (§9).
- The missing human: the harness is *defined* as
  human-prompts + LLM responses, yet claim 2 has no direct
  human term — in the dyad-principal disjunct the operator is
  buried inside the principal.

**Composition finding.** Under the additive reading, the two
claims jointly entail harness ~ agent + operator + R + agent —
while the actual run's most salient participant after the
agent, the prompting human, appears nowhere as a term. The
pair defeats itself.

**Narrowed survivors.** (a) Dyad membership is exactly {agent,
operator} — the third term is the *relation*, not a member.
(b) A harness run's *parties* are principal (for whom), agent
(who works), human (who prompts and disposes) — but the run
itself, the structured exercise, is not their sum.
