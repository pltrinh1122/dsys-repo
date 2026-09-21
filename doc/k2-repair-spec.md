# K2 repair spec — explicit accretion adoption + fail-closed drive

- **Status:** adopted per DR-CMD-038 (2026-09-21) — the build's basis; D3 disposed as refuse-the-drive. Changes during build must keep the evaluated conditionals holding and discharge the four adoption conditions.
- **Provenance:** K2 ("new installation of updater should by default adopt previous installation's accretion") was operator-tagged `falsify` and killed 2026-09-21; specified in `doc/updater-spec.md` §9 per DR-CMD-036. Framed as a governed `/pb-extend` matter this session (dual-scope, decomposed at START); draft verdict refuse(not-ready); the operator directed "author the repair spec."

## Glossary

- **Accretion:** the durable, journaled state a dsys installation accumulates — config, run state, snapshots, promotion records. The accreted set is `etc/` + `var/` minus cache dirs (installer-spec §13).
- **Accretion-repo:** a local git repository holding one installation's accretion, git dir at `<accretion-path>/.git` with the install home as worktree. Local only — no remote, no push (installer-spec §13).
- **Accretion path:** the filesystem path of an accretion-repo. Default `<accretion-root>/{instance}` (`/var/daccretion`, instance = install-home basename); overridable by `accretion.path` in `etc/config.yaml` or `--accretion-path` flag; precedence flags > config > default.
- **Install-home:** the root directory of one dsys installation (e.g. `~/dsys-inst`). The updater build has no install-home concept — the K2 kill's first falsifying observation.
- **Resume (vs overwrite):** the installer's default when a repo already exists at the accretion path — continue its history. `--overwrite` moves the existing repo aside and starts fresh (installer-spec §13).
- **Warn-and-continue:** the installer-spec §13 rule "Never fails the install" — git absent or path unwritable → warn, continue with accretion disabled, record `accretion: {"enabled": false, "reason}` in the manifest. The exact edge K2 killed.
- **Fail-closed:** the repair's installer mode — accretion required; if it cannot be enabled the install fails (nonzero exit) instead of warn-and-continue.
- **Refuse-the-drive:** the repair's unwritable-path rule — the updater's drive aborts loudly (`run_aborted → failed`) rather than driving an install whose history has nowhere to land.
- **Loud-surface:** the rejected alternative — proceed but surface the condition loudly. Rejected: under autonomous operation with no watcher, a loud surface with no one watching is warn-and-continue renamed (the notification entity was falsified; no watching channel exists).
- **Ambient defaults:** invoking the installer with no accretion arguments and hoping the installer's default-resume lands on the right repo. The K2 kill's second falsifying observation — the updater "never wires to it."
- **Explicit wiring:** the repair — the drive derives the previous install's effective accretion path and passes it as an explicit `--accretion-path` flag.
- **Autonomous operation:** the updater running under `policy=auto` on its timer with no human watching. Silence is the failure mode here.

## The kill restated

K2 claimed a new installation adopts the previous installation's accretion repo by default. It broke twice: (1) the build has no install-home and no accretion-repo concept — a fresh `World` starts empty; (2) the installer *intends* adoption via default-resume, but the updater never wires to it (the installer tool takes no accretion path or resume flag), and the unwritable-path edge (warn + install completes, no accretion) drops history silently — under autonomous `policy=auto` with no human watching, "by default" fails in exactly the failure mode. What survives: installer default-resume on the happy path. Repair direction (from the kill record): the drive's installer invocation must explicitly pass/resume the accretion path; the unwritable-path edge needs a rule for autonomous operation — refuse the drive, or surface loudly enough that silence cannot mean history loss. Which rule is a disposition.

## Narrowed claim

The updater's drive explicitly resumes the previous installation's accretion repository when invoking the installer, and the unwritable-accretion-path edge refuses the drive rather than warn-and-continue under autonomous operation — so history is never silently lost.

## Scope (dual, decomposed at START — conjunctive adoption)

- **Runtime:** the machine gains a guarantee — under `policy=auto`, a drive whose accretion path is unwritable refuses (lands `failed`) instead of silently dropping history. No flow-table change: the refusal rides the existing `run_aborted → failed` edge (installer nonzero → `ToolAborted`). R1's replay story is untouched — the precondition is pre-drive; the event log still re-derives. (R1's *durability premise* stays K1's territory — see D6.)
- **Package:** the installer invocation gains explicit accretion arguments; `install.sh` gains the fail-closed flag (DR-CLI-001: a flag on the existing `install.sh` surface, consistent with `--accretion-require-authorization`).

## Decisions

- **D1 — Explicit wiring.** The drive's installer invocation passes `--accretion-path` derived from the *previous install's effective path*: read `<prev-home>/etc/config.yaml` `accretion.path`; fall back to the default rule (`<accretion-root>/{basename}`). The updater gains an install-home concept (its configuration names the previous home; on a first install there is none and the path derives from its own home — fresh repo, defined behavior, not a refusal). Ambient defaults are never relied on: with an explicit flag the installer has no default to fall back on for this invocation.
- **D2 — Fail-closed flag.** New installer flag `--accretion-required`: accretion is required for this install; if git is absent or the path unwritable, the installer exits nonzero naming the reason (no manifest lie — the install fails before converge). The updater's drive always passes it. Name parallels `--accretion-require-authorization`.
- **D3 — Refuse-the-drive (disposed DR-CMD-038).** Unwritable path → installer nonzero → `ToolAborted` → `run_aborted` → `failed`. The update is deferred, not lost: the next timer cycle retries; the failure is observable as a failed run rather than silent loss. Loud-surface was rejected under autonomy — no watcher exists, so it collapses to warn-and-continue renamed; re-arguable only if a watching channel with teeth ever exists.
- **D4 — No flow-table change.** The existing `run_aborted → failed` edge carries the refusal; the guarantee lives in the tool contract and the invocation, not in new states.
- **D5 — Never `--overwrite` from the updater.** Under autonomy, moving history aside is destruction-adjacent; overwrite stays an interactive-operator act. The updater's invocation contract pins resume.
- **D6 — K1 boundary (explicit premise).** This repair defines *which repo* the new install binds and the *failure rule* when it can't. The *writer* of inter-install state (the updater's event log) is K1's open repair. Without K1, the adopted repo accrues installer snapshots only. This spec claims no durability it doesn't provide.
- **D7 — Replay unchanged.** The precondition is pre-drive; R1's re-derivation story stands as evaluated.

## Falsification

- **F1 — "Explicit `--accretion-path` is ambient defaults with extra steps."** Falsified: the path is derived from a declared previous-home input through the documented precedence (config > default) and passed as an explicit flag. Observable difference: with ambient defaults, a config change between installs silently re-homes the repo; with explicit wiring, the updater pins the previous install's effective path.
- **F2 — "Refuse-the-drive bricks the fleet on a transient permissions glitch."** Survives weakened: the update is deferred, not lost — the next cycle retries. Accepted residual: a fleet-wide permissions break parks updaters in `failed`, which is the correct observable state for "we cannot durably record what we are doing."
- **F3 — "The writability check is racy (TOCTOU)."** Addressed by making the *installer flag* load-bearing, not a pre-check: the installer's own write attempt is the atomic truth. No separate pre-check is specified — one mechanism, fewer moving parts.
- **F4 — "Previous home unknown."** Defined behavior, not a refusal: first install derives the path from its own home; the installer initializes a fresh repo. The refusal is only for unwritable-path.

## Acceptance (checkable sequences)

1. Fixture: unwritable accretion path, `policy=auto`, newer feed version → the drive reaches `failed`; the installer was invoked with `--accretion-path=<explicit>` and `--accretion-required`; no promotion recorded; installed version unconverged.
2. Fixture: previous home with config-overridden `accretion.path` → the installer invocation's `--accretion-path` equals the previous install's effective path (not the default rule).
3. Fixture: no previous home (first install) → the drive proceeds; the installer initializes a fresh repo at the derived path.
4. The updater's installer invocation never carries `--overwrite` (contract assertion on the invocation args).
5. Replay of acceptance 1's event log re-derives the path (R1 untouched).

## Open questions (G6)

- K1's writer, when built, writes to the repo this repair adopts — the two repairs must compose; neither subsumes the other.
- If a watching channel with teeth ever exists, loud-surface can be re-argued as a composition — not as the rule.
- The exact config key naming the previous install home is build detail.
