# Half 2: the inference-service channel — design

Status: **draft** (for Peter's disposition — ratify spec / accept build are separate acts).
Ratified: no. Half 1: closed and ratified 2026-09-26 (DR-CMD-083..088).

## Glossary

- **Half 1**: the author-agent loop (DR-CMD-083/084), channels (DR-CMD-085/087),
  containment (DR-CMD-086/088). The agent is authored by ambient inference;
  the automaton executes with zero inference inside.
- **Half 2** (this doc): the inference-service channel. A contained agent that
  needs inference emits a **prompt-request**; the harness accommodates it with
  a **`claude` CLI invocation** and feeds the response back as an event.
  The agent never infers; it is served inference.
- **Prompt-request**: text printed by the agent to its stdout, in the fenced
  block format of §3, asking the harness for inference service.
- **`claude` CLI**: the harness-side command fulfilling inference requests.
  Contract: `claude [--kind KIND] PROMPT` → response text on stdout.
  The name is the contract, not an implementation: the test backing is
  `scripts/claude-stub` (deterministic); the production backing is the real
  CLI (API-backed). Telemetry always marks which backing served.
- **Inference round**: one contained execution of the agent plus the
  fulfillment of the prompt-requests its stdout carried.
- **Inference loop** (`infer`): the harness-side bounded loop —
  drive agent → parse prompt-requests → invoke `claude` per request →
  stage responses → re-drive — until the agent emits no requests or a
  bound is hit.
- **Inference result**: the harness-staged event carrying one fulfilled
  response back to the agent. Typed as harness-service data; it is not a
  principal or world channel code, and the afferent–efferent triad is untouched.
- **J0**: the standing architectural ruling — authoring inference is
  harness-side ambient inference governed by the wright profile; zero
  inference occurs inside Automaton execution.
- **Dumb relay** (falsified, carried from Half 1): a shape in which ambient
  chat is reduced to piping prompts to an agent. Killed because ambient is
  the inference actor under J0.

## 1. What Half 2 is

Half 1 proved an agent can be authored, contained, driven, and verified with
zero inference inside execution. Half 2 answers the next question: **how does
such an agent obtain inference when its task needs it, without performing
inference itself?**

Peter's thesis (2026-09-26), adopted as the design constraint:

> every prompt (principal → agent) and inferencing request (world → agent)
> would be accommodated with a `claude {prompt}` CLI invocation. when agent
> needs inferencing service, it would output to stdout with a prompt-request
> text.

The reading this design adopts: there is **one mechanism** for all three
directions. The agent — and only the agent — decides it needs inference. It
says so by printing a prompt-request block to stdout. The harness (outside
containment, where inference is allowed) accommodates each request by
invoking `claude {prompt}`, then stages the response as an inference-result
event and re-drives the agent. A principal prompt and a world inference
request are accommodated the same way: they arrive as events, and the agent
requests inference for them iff its logic says so.

## 2. Architecture

```
principal/world event
        │
        ▼
┌─────────────────────────────┐
│  harness: infer loop        │  ◄── inference is allowed here
│  1. drive agent (contained) │
│  2. parse stdout: any       │
│     prompt-request blocks?  │
│  3a. none → adopt result,   │
│      write transcript, done │
│  3b. some → for each:       │
│      `claude --kind K PROMPT`│
│  4. stage responses as      │
│     inference-result events │
│  5. re-drive (next round)   │
└─────────────────────────────┘
        │
        ▼
┌─────────────────────────────┐
│  contained agent            │  ◄── zero inference inside (J0)
│  pure function:             │
│  (event, inference_results) │
│    → result.json + stdout   │
│  stdout may carry           │
│  @@prompt-request blocks    │
└─────────────────────────────┘
```

Load-bearing separations:

- The **agent never invokes `claude`**. Containment already refuses child
  processes; the agent has no path to the CLI. Its only inference surface is
  the prompt-request text (§3).
- The **harness never infers on the agent's behalf unasked**. Every
  `claude` invocation is traceable to a prompt-request the agent printed.
- **`claude`'s stdout is inert data.** It is never scanned for
  prompt-request markers. Only the contained agent's stdout, in a fresh
  round, is parsed. This kills prompt-injection recursion by construction.
- The **agent's transition stays deterministic**: same
  (event, inference_results) → same result.json and same prompt-requests.
  Non-determinism enters only through `claude` responses, and every response
  is hash-recorded in the transcript, so replay against the same backing
  reproduces the transcript exactly.

## 3. The prompt-request text (summary; exact grammar in the spec)

The agent prints fenced blocks; anything else on stdout is logs:

```
@@prompt-request id="pr-1" kind="classify"
Classify the following principal message as ROUTINE or URGENT:
<message text, any lines>
@@end
```

Strictness is fail-closed: a `@@prompt-request` line with no closing
`@@end` before EOF, an unknown kind, an empty or oversized prompt, or a
malformed header → the round is refused with reasons and the agent's output
is not adopted. Well-formedness is the agent's responsibility; the parser
does not repair.

Request kinds are a closed enum, taken from the dialog protocol's request
vocabulary: `propose, classify, triage, assess, challenge, goal`. The harness
passes the kind to `claude --kind KIND` so the backing can frame accordingly.

## 4. Falsification record

Alternatives considered; each killed on a named ground (falsification is
opt-in per claim — Peter's thesis set the frame; these are the breaks inside
it):

- **F1 — auto-inference on every principal prompt** (harness invokes
  `claude` for each principal → agent message without being asked).
  **Killed.** It recreates the dumb relay: the agent stops deciding and
  starts relaying, and every prompt pays inference cost. The agent must stay
  the decider; the harness accommodates, never initiates.
- **F2 — agent invokes `claude` itself** (subprocess from inside
  containment). **Killed.** Containment refuses child-process creation
  (DR-CMD-086); punching that hole would put a network-adjacent capability
  inside the agent. The stdout text is the narrowest possible surface.
- **F3 — outer-loop fulfillment** (`drive` returns prompt-requests
  unfulfilled; ambient/the operator fulfills and re-stages). **Killed.**
  It splits one bounded loop across an unbounded outer driver, leaves no
  single transcript, and reintroduces the relay shape ambient was
  falsified against. The loop belongs in the harness command, bounded and
  transcribed.
- **F4 — harness-inline bounded loop** (`infer`). **Survivor — adopted.**
  One command, one transcript, explicit bounds (rounds, requests/round,
  prompt bytes, claude timeout). Directly implements Peter's thesis.
- **F5 — nested prompt-requests** (scan `claude` responses for further
  blocks, i.e. inference requesting inference). **Killed.** Responses are
  data; only the agent's fresh stdout is parsed. Recursion, if the agent
  wants it, happens across rounds — visible in the transcript, bounded by
  max-rounds.

## 5. Bounds (exact values in the spec)

- max rounds per `infer` run: 3 (flag-overridable).
- max prompt-requests honored per round: 8; excess → refusal.
- max prompt bytes: 65536.
- `claude` timeout: 120 s; timeout/non-zero exit → round refused with
  reasons (no retry — fail-closed; the operator re-drives).
- max rounds exceeded with requests still pending → outcome `refused`,
  transcript records the cutoff.

## 6. Determinism and replay

- The stub backing (`scripts/claude-stub`) is a pure function of
  (kind, prompt) → byte-identical responses across runs and machines.
- The transcript records, per round: request id, kind, `prompt_sha256`,
  `response_sha256`, claude exit code, backing identity.
- Replay = re-run `infer` with the same backing; the golden battery asserts
  transcript equality across two runs (scratch-name-normalized, same as
  Half 1's diagnostics).

## 7. Containment and safety

Half 2 adds no containment holes: the agent runs under the existing
`run_contained` machinery (hash-pinned venv, source-tree copy-in, per-run
scratch, scrubbed env, timeout/quarantine, no network, no child processes,
no outside-scratch writes). New surface is exactly one: the agent's stdout
is parsed for prompt-request blocks. `claude` executes harness-side with
the harness's environment — never the agent's.

## 8. Demo and verification

- Hand-built demo agent `core/package/demo_classifier_agent.py`: receives a
  principal message; round 1 emits a `classify` prompt-request; round 2
  reads the verdict from the inference result and returns it. Pure and
  deterministic.
- Golden battery `core/package/author_infer_golden_run.py` (~10 cases):
  parsing (well-formed, multiple, dangling, unknown kind, oversized),
  full loop via the stub, response-inertness, max-rounds cutoff, claude
  failure refusal, two-run transcript determinism.
- `make install` runs it as battery 5; `make infer` runs the demo with a
  bounded telemetry block (mirroring `make run`'s BEGIN/END markers).
  `make infer` refuses without a valid install receipt, same as `make run`.

## 9. What Half 2 does not do

- The **author-agent does not yet build inference-using agents**. The demo
  agent is hand-built. Teaching the author loop a second agent archetype is
  a future matter (Half 3 candidate).
- **World channels stay unbound** for the wright (D7 0.75, D5 0.0). A
  world → agent inference request is accommodated only insofar as a
  world-facing agent's logic requests it; no world ingress paths are opened.
- **No standing inference policy**: kinds, bounds, and the backing are
  per-run configuration, not profile facets. Whether inference use belongs
  in the D-dimensions is an open question, recorded not decided.
- The production `claude` backing (API key, model selection, cost
  accounting) is specified as a contract, not implemented. The stub is
  labeled in every transcript that uses it.
