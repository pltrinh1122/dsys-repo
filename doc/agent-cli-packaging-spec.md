# Agent CLI Packaging & Installer — Design Spec

Spec-only. Nothing here is implemented. Purpose: headless invocation
of an agent runtime under a named role — e.g.
`dsys execute --as cos --prompt "..."` — so the Dyad
architecture can be **test-driven end to end**: agents act, the
machine-native package referees.

## 1. Goals / non-goals

**Goals.**
- One installed command, `dsys`, that runs an agent headlessly:
  prompt in, response on stdout, diagnostics on stderr, meaningful
  exit codes.
- Role framing: `--as cos | operator | auditor | ...` selects a
  versioned system-prompt bundle encoding that role's duties and
  output contract (the CoS drain duty, the operator's CTA grammar,
  ...).
- Backend-agnostic: the CLI shells out to an agent runtime through a
  small adapter interface. Reference backend: the `claude` CLI in
  headless print mode. Nothing in the CLI assumes a particular
  vendor beyond the adapter.
- A `referee` mode: the same installed CLI validates state files
  and renders views using the machine-native package — agents act,
  the package judges.
- An installer that takes a fresh machine from zero to
  `dsys doctor` green in one command.

**Non-goals.**
- The CLI does **not** enforce architecture rules. It is plumbing +
  role framing + run records. Enforcement lives in
  `package/validators.py`, which the test harness calls. (This is
  the surface/entity split from the notification falsification,
  applied to tooling.)
- No new agent capabilities, no hosted service, no daemon.
- No API-key handling: the CLI uses whatever auth the backend
  already has (e.g. the `claude` CLI's own login). The installer
  never touches secrets.

## 2. CLI surface

```
dsys execute --as <role> --prompt "..." [--prompt-file f]
                   [--timeout 300] [--format text|json] [--stream]
dsys roles list
dsys roles show <role>          # prints system prompt + hash
dsys backend status
dsys referee validate --state state.json
dsys referee view --state state.json [--kind open-disclosures]
dsys doctor
dsys --version
```

**`execute` semantics.**
- Reads the role bundle (`roles/<role>.md` + `roles/<role>.json`
  contract), builds the backend invocation, runs it headless with
  no TTY.
- **stdout**: the agent's response text only (pipeable).
- **stderr**: diagnostics, timing, backend chatter — never mixed
  into stdout.
- **Exit codes**: `0` ok · `1` usage error · `2` backend failure
  (backend missing/crashed) · `3` timeout (backend killed) ·
  `4` agent refusal (the agent declined the task — first-class,
  because refusal-case testing needs it).
- `--format json`: stdout carries a run envelope instead of raw
  text:
  `{role, role_hash, prompt_hash, backend, backend_version,
    started_at, duration_ms, exit_code, stdout, stderr}`.
  The envelope is the **run record**: what makes a test-drive
  auditable after the fact.

**Role bundles.** `roles/cos.md` (system prompt: CoS duties incl.
the drain-duty procedure, triage CTA grammar, "propose, never
dispose"), `roles/operator.md` (disposition grammar: Y/N/counter,
one CTA per turn), `roles/auditor.md` (read-only: may render
views, may not propose). Each bundle carries a sha256 `role_hash`
printed by `roles show` and embedded in every run envelope.

## 3. Backend adapter interface

```python
class Backend(Protocol):
    name: str
    def probe(self) -> tuple[bool, str]: ...        # doctor/status
    def execute(self, *, system: str, prompt: str,
                timeout_s: int) -> BackendResult: ...  # text, exit_hint
```

- **Reference backend `claude-cli`**: `probe` = `claude --version`;
  `execute` = `claude --print --system <system> <prompt>` (flags
  pinned in the adapter; `doctor` fails loudly if they drift).
- **Backend `stub`**: echoes a canned response; for installer
  self-test and CI without credentials.
- Third backends (codex, local runner, …) are new adapter files,
  not CLI changes. Selected by `backend:` in config or
  `--backend`.

## 4. Test-drive harness (why this exists)

A scenario driver (phase 2; sketched here so the CLI surface fits
it):

1. Scenario YAML declares turns: e.g. `cos: "drain the queue"` →
   `operator: "answer pending CTAs"` → `referee: validate`.
2. Each agent turn runs `dsys execute --as <role>
   --format json`; the envelope is appended to a transcript log.
3. Agent outputs are **parsed, never trusted**: the driver
   extracts proposed records (JSON blocks per the role contract),
   writes a candidate `state.json`, and runs
   `dsys referee validate`. Malformed output = failed turn,
   retried or aborted — never silently accepted.
4. Replay = re-running `referee validate` + `referee view` over
   the **recorded transcript**. Deterministic, mechanical. (What
   is *not* replayable: the LLM's choices. The spec is explicit:
   behavior replay is out; transcript re-validation is the
   determinism story. This matches the architecture's
   zero-inference-in-execution posture — the agents are the
   inferenceful outside; the package is the deterministic
   inside.)

Minimal scenario schema (v0): list of steps
`{actor: cos|operator|referee, input: ..., expect: clean|violation}`.

## 5. Packaging layout

Monorepo next to the architecture package:

```
dsys/
  pyproject.toml            # name dsys; deps: pydantic (already used)
  dsys/
    __init__.py
    cli.py                  # argparse, stdlib only
    roles.py                # bundle loading + hashing
    backends.py             # Backend protocol + claude-cli + stub
    referee.py              # thin wrapper over package.validators / views
    roles/
      cos.md / cos.json
      operator.md / operator.json
      auditor.md / auditor.json
  install.sh
  scenarios/
    drain-duty.yaml         # phase 2
```

`referee.py` imports the architecture `package/` (vendored or
sibling dependency, pinned by content hash recorded in
`dsys --version` output). One version string covers CLI +
core + role hashes: `dsys --version` prints all three.

## 6. Installer (`install.sh`)

> Superseded by `installer-spec.md` (2026-09-19): self-contained
> deployment design (`~/.dsys` tree, offline install, manifest +
> hash verification, per-command hermeticity boundary). The sketch
> below is retained as history.

One command: `./install.sh` (or via curl). Steps:

1. Preflight: `python3 >= 3.10`, `curl`; warn (don't fail) if no
   agent backend is on PATH — `stub` keeps install green.
2. Create `~/.dsys/venv`; `pip install` the repo
   (editable optional flag `--dev`).
3. Symlink `~/.dsys/venv/bin/dsys` → `~/.local/bin/dsys`
   (create `~/.local/bin`; remind about PATH if needed).
4. Write default `~/.dsys/config.yaml`
   (backend: auto → first green probe; timeout: 300).
5. Self-test: `dsys --version`, `dsys doctor`,
   `dsys execute --as auditor --backend stub --prompt "ping"`.
   Any failure aborts with the step named.
6. Idempotent: re-running upgrades in place, never duplicates
   symlinks or venvs.

`dsys doctor` checks, each with fix hints: python version,
venv integrity, `package/` core importable (+ its content hash),
roles present (+ hashes), backend probes, `~/.local/bin` on PATH.

## 7. Trust boundaries (load-bearing)

- **The CLI trusts nothing the agent says.** Role prompts are
  advisory to the LLM; every test assertion runs through the
  referee. A scenario that "passes" because the agent *claimed*
  validity is not a test — the harness design ( §4.3 ) is what
  makes it one.
- **The installer handles no secrets.** Backend auth is the
  backend's business.
- **Refusals are data.** Exit code 4 exists because the
  architecture's refusal cases are its specification — a
  test-drive that can't distinguish "agent refused" from
  "backend crashed" can't test them.

## 8. Falsifiers (pre-registered)

- **F1.** "The CLI guarantees valid dispositions." False by
  design (§1). If any doc or message implies it, kill the claim,
  not the tool.
- **F2.** "Role prompts bind the agent." False — advisory only.
  Binding happens in validators. A role whose duties matter must
  have a referee check behind each duty (cf. the DR-5 progress
  hole: unenforced diligence is decoration).
- **F3.** "Test-drives are deterministic replays." False for
  behavior; true for transcript re-validation (§4.4). Do not
  promise what §4.4 disclaims.
- **F4.** Backend flag drift (`claude --print` changes): caught
  by `doctor`'s probe + pinned adapter. If `doctor` is green and
  `execute` fails, the adapter's pin is the first suspect.
- **F5.** Scope: if headless agents turn out unnecessary because
  scenarios are fully scriptable without LLMs, this whole
  package collapses to `referee` + scenario YAML — which is a
  legitimate simplification, not a failure. The CLI must not
  become load-bearing for anything the referee can do alone.
