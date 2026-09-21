# Bridge spec — the pydantic→core compile path

- **Status:** adopted per DR-CMD-037 (2026-09-21) — the build's basis; changes during build must keep the evaluated conditionals holding and discharge the four adoption conditions
- **Date:** 2026-09-21
- **Matter:** the framed bridge claim — "dsys should gain a generic bridge — one compile path from pydantic automaton sources to AutomatonFlow/FlowRun + RunBook/Step/Tool entities — such that any future automaton is authored as pydantic models and executed on the existing FlowRun scheduler, with zero new engine code."
- **Purpose:** the A4 artifact for the bridge expansion matter.

## Glossary

- **Bridge:** the compile path specified here. A pure function from a pydantic automaton source to the entity set the FlowRun scheduler executes. The DR-CMD-030 term ("source→core bridge"); "compiler" is avoided because this maps models to entities within one schema, not between languages.
- **Automaton source:** a frozen pydantic v2 model describing one automaton — its states, guarded transitions, and run-book structures. Authored by the operator (or drafted by the ambient and disposed by the operator — proposer≠disposer holds for sources).
- **Compilation:** the bridge's single act — source bytes in, entities out. Total, deterministic, closed under the existing entity schema (§3).
- **Source bytes:** the canonical serialization of the source model (frozen models serialize deterministically). The unit of the replay story.
- **Compilation totality:** every element of the source maps to exactly one entity — nothing dropped, nothing invented (validator B-1).
- **Id determinism:** the same source bytes always yield the same entity ids (validator B-2).
- **Schema closure:** the bridge introduces no new state kinds, trigger kinds, or step policies — anything unmappable to the existing entity schema is refused at compile time, loudly (validator B-3). This is the load-bearing constraint from F1 (§6).
- **Tool registry:** the code-side mapping from tool id to implementation. Tools are registered code; the source names them but cannot define them (§5).

## 1. What the bridge compiles

One automaton source compiles to exactly the entity set the scheduler already executes:

- `AutomatonFlow` (id, name, release_version, initial_state_id)
- `FlowState[]` (flow_id, name, kind ∈ task|wait|end, runbook_id?, outcome?, step_policy?)
- `FlowTransition[]` (flow_id, from_state_id, trigger, guard?, to_state_id)
- `RunBook[]` (id, release_version, name), `Step[]` (runbook_id, seq, expr, tool_id), `Tool[]` (id, name)

The X4 delta from the matter framing, specified: `updater.compile_flow()` compiles only states and transitions from source — its five run-books are hand-written in `_runbook_entities()`, Python tuples, not derived from the pydantic model. The bridge closes that gap: **run-book structure is source; tool behavior is registered code.** A source declares *which* steps in *which* order with *which* guards and *which* tool ids; the implementations those ids name live in the tool registry, outside the source. The source cannot define behavior — only structure. (F2, §6.)

The bridge is a constructor, not an engine: it adds no execution semantics. Everything it emits is validated by the standing validators — I-14 (flow totality), I-15 (transition determinism), I-16 (flow-run closure) — exactly as the updater's compiled output was.

## 2. Source models (pydantic v2 — the DR-CMD-028 pin)

Generalizing the updater's `MonitorState`/`MonitorTransition`/`ReleaseMonitorFlow`. Frozen models; YAML is serialization (DR-CMD-028).

```python
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal

Trigger = Literal['timer', 'run_completed', 'run_aborted', 'external']
StateKind = Literal['task', 'wait', 'end']
EndOutcome = Literal['completed', 'aborted']

class AutomatonState(BaseModel):
    """One FSM state — compiles to FlowState."""
    model_config = ConfigDict(frozen=True)

    name: str
    kind: StateKind
    runbook_id: str | None = None          # required iff kind == 'task'
    step_policy: str | None = None         # iff kind == 'task': abort | skip | retry:<n>
    outcome: EndOutcome | None = None      # iff kind == 'end'

class AutomatonTransition(BaseModel):
    """One guarded edge — compiles to FlowTransition."""
    model_config = ConfigDict(frozen=True)

    from_state: str
    trigger: Trigger
    guard: str | None = None               # AST-allowlisted expr over payload.*
    to_state: str

class RunBookStepSource(BaseModel):
    """One run-book step — compiles to Step."""
    model_config = ConfigDict(frozen=True)

    expr: str = "True"                     # AST-allowlisted guard for the step
    tool_id: str                           # must resolve in the tool registry (B-3)

class RunBookSource(BaseModel):
    """One run-book's structure — compiles to RunBook + Steps."""
    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    steps: list[RunBookStepSource] = Field(min_length=1)   # strictly sequential; seq = index

class AutomatonSource(BaseModel):
    """One automaton — compiles to AutomatonFlow + states + transitions + run-books."""
    model_config = ConfigDict(frozen=True)

    name: str
    release_version: str
    initial_state: str
    states: list[AutomatonState] = Field(min_length=1)
    transitions: list[AutomatonTransition] = Field(min_length=1)
    runbooks: list[RunBookSource] = Field(min_length=1)
```

A2 (ontology, from the framing): "bridge" is justified against `compile_flow` — the updater's function is one application of the compile path to one source; the bridge is the general mechanism. On adoption, `updater.compile_flow()` is re-expressed through the bridge (migration = build work, §8) — one path, not two.

## 3. Compilation semantics

`compile(source: AutomatonSource, tools: ToolRegistry) -> (AutomatonFlow, FlowState[], FlowTransition[], RunBook[], Step[], Tool[])`. Pure function: source bytes and the registry in, entities out. No I/O, no network, no inference (R4, P2).

- **Totality (B-1):** every state, transition, run-book, and step in the source yields exactly one entity. Cross-references resolve by name (`runbook_id`, `from_state`/`to_state`, `tool_id`); a dangling reference is a compile-time refusal, not a warning.
- **Id determinism (B-2):** entity ids derive deterministically from the source. The source declares `state_id_prefix` / `transition_id_prefix` (default: the slugified flow name as `{slug}-s-` / `{slug}-t-`): states `{state_id_prefix}{name}`, transitions `{transition_id_prefix}{i:02d}` in source order, run-books keep their source ids, steps `{runbook_id}-s{seq}`. Same source bytes → same ids, every time. The explicit prefixes manage the id space when several flows share a `SystemState` (the I-14 cross-flow checks), and let the bridge reproduce the updater's legacy `urm-` / `urmt-` prefixes byte-for-byte (§7.1). (Refined at build 2026-09-21: the draft's fixed `{slug}-s-` scheme could not express legacy prefixes; the refinement keeps B-2 holding — determinism is over source bytes, which include the prefixes.)
- **Schema closure (B-3):** the bridge maps only onto the existing entity schema. A source element requiring a new state kind, trigger kind, or step policy is refused at compile time — the bridge never extends the execution semantics to accommodate a source. This is what keeps DR-CMD-030's "no new engine" decision holding under generalization.
- **Guards and step exprs** are AST-allowlisted (the v1 Python-syntax subset — comparisons, boolean ops, attribute access over `payload.*`; compiled once). A guard outside the allowlist is a compile-time refusal.
- **Unknown tool id** is a compile-time refusal (loud — the same lesson as the updater review's unknown-tool fix, moved earlier: from run time to compile time).

The compiled output is then subject to the standing validators I-14, I-15, I-16 — mechanically, before anything executes.

## 4. Replay story (R1)

The bridge does not change the replay story — it sharpens its precondition. Replay re-derives the state path from the `FlowTransitionEvent` log (the entity's definition); the bridge compiles once, ahead of execution. The bridge's own checkable property: **re-compiling the same source bytes yields byte-identical entities** — hash equality of the serialized entity set between compilations. An automaton whose source changed is a new `release_version` (a step-change), never a silent recompilation under the old version.

## 5. Trust declaration (R5)

- The bridge is trusted core code (`core/package`): it is the machine's own constructor, reviewed like the scheduler.
- Sources are operator-authored. The ambient may draft a source; the operator disposes it (proposer≠disposer). A source takes effect only as a versioned step-change.
- The tool registry is code, reviewed as code. Registration is explicit — there is no ambient tool discovery. A source naming an unregistered tool id fails closed at compile time (B-3).
- The anti-smuggling line: sources declare structure (states, edges, step order, guards, tool names). Behavior lives in registered tool implementations and in the scheduler. Nothing the source says can widen what the machine can do — schema closure (§3) is the enforcement.

## 6. Falsification (A1)

Two genuine attempts, both survived:

- **F1 — the second-engine objection:** "A generic compiler over heterogeneous automata collapses into a framework with options and flags — the 'generic' bridge becomes a second execution engine, violating DR-CMD-030." *Survived, with the load-bearing constraint:* the bridge emits only the existing entities and is validated only by the existing validators; schema closure (B-3) refuses anything that would need new execution semantics. The day a source needs a new state kind, the answer is a governed expansion matter for the scheduler — not a bridge option. The constraint is specified, not hoped.
- **F2 — behavior smuggling via tool ids:** "Compiling run-books from source lets a source inject behavior by naming tools." *Survived:* naming is not defining. Tool ids resolve against the explicit code registry; unknown ids refuse at compile time. The source's power is structural rearrangement of registered behaviors — which is exactly what an automaton definition should be able to express, and nothing more.

## 7. Acceptance (A5 — checkable sequences)

1. **Updater re-expression:** the release-monitor source, compiled by the bridge, yields entities equal (by serialized hash) to `updater.compile_flow()` output — the bridge subsumes the one-off path.
2. **Second automaton:** a new automaton (candidate: the K1 repair's accretion-commit path — an inter-install commit driver — or a minimal timer-driven heartbeat) authored *purely* as an `AutomatonSource`, compiled by the bridge, executed by the scheduler, with replay-hash equality between live run and log re-derivation.
3. **Refusals:** a source with a dangling `runbook_id` → compile refusal; a source naming an unregistered tool → compile refusal; a source requiring a novel trigger kind → compile refusal (B-3 bites).
4. **Determinism:** compile the same source bytes twice → byte-identical entity sets (hash equality).
5. F1/F2 falsification records exist (this section).

## 8. Open questions

- **Module placement:** `core/package/bridge.py` is the natural home; the build decides.
- **Migration:** whether `updater.compile_flow()` is re-expressed through the bridge at build time or kept as the frozen one-off with the bridge built alongside. A2's "one path, not two" argues for re-expression; the build sequences it.
- **The mermaid generator** (DR-CMD-029) consumes the *source*, not the compiled entities — rendering intent, not execution. The bridge does not preempt that decision.
- **Second-automaton candidate:** the K1 repair direction (updater event-log accretion commits) would exercise the bridge on a real need rather than a toy — but K1's repair is itself an undisposed matter. The bridge's acceptance should not wait on it; a minimal heartbeat automaton suffices if K1 stays open.
- **YAML authoring:** DR-CMD-028 pins pydantic models as the source format with YAML as serialization. The bridge reads models; YAML→model parsing is a thin loader, not bridge work.

## 9. What this spec does not do

- It does not change the scheduler, the entity schema, or any standing validator. It constructs inputs for them.
- It does not define tool implementations — those are registered code, authored per automaton, reviewed as code.
- It does not grant the ambient any new initiation path (K3 stands — the bridge compiles what the operator disposes; it does not invoke anything).
