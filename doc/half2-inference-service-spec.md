# Half 2: the inference-service channel — spec

Status: **draft** (for Peter's ratification). Companion: `doc/half2-inference-service-design.md`
(design rationale, falsification record). This doc is the contract.

## Glossary

- **Prompt-request**: a fenced block printed by the contained agent to stdout
  (§1). The agent's sole inference surface.
- **`claude` CLI**: harness-side fulfillment command (§2).
- **Kind**: closed enum `propose | classify | triage | assess | challenge | goal`.
- **Inference round**: one contained agent execution + fulfillment of its
  prompt-requests. Numbered from 1.
- **Inference result**: `{"request_id", "kind", "prompt_sha256", "text",
  "text_sha256"}` — one fulfilled response, staged to the agent next round.
- **Transcript**: the `infer` run's complete record (§5).
- **Backing**: the executable behind the `claude` name (`scripts/claude-stub`
  for tests; the real CLI in production). Always identified in the transcript.
- **Refusal**: the loop stops without adopting the agent's output, recording
  reasons. The closed refusal list is §6.

## 1. Prompt-request text format

The agent's stdout is scanned line-wise. A prompt-request is:

```
@@prompt-request id="<id>" kind="<kind>"
<prompt: one or more lines; no line may begin with "@@">
@@end
```

Grammar:

- Start line: exactly `@@prompt-request id="<id>" kind="<kind>"`, where
  `<id>` matches `[A-Za-z0-9_-]{1,64}` and `<kind>` is one of the closed
  enum values. Attribute order is fixed (`id` then `kind`); quoting is
  double quotes; no extra attributes.
- Prompt body: ≥1 line, ≤ 65536 bytes UTF-8 total. No body line may begin
  with `@@` (reserved for framing).
- End line: exactly `@@end`.
- Blocks may not nest or overlap. Text outside blocks is ignored (logs).

Violations (each → round refused per §6):

- V1: a start line with no `@@end` before EOF (dangling block).
- V2: unknown kind.
- V3: malformed start line (bad id, wrong order, extra attributes).
- V4: empty prompt body.
- V5: prompt body > 65536 bytes.
- V6: a body line beginning with `@@`.
- V7: more than 8 well-formed blocks in one round's stdout.

Duplicate ids within a round: the second and later occurrences are ignored
(first wins); ids need only be unique within the run for transcript clarity.

## 2. `claude` CLI contract

```
claude [--kind KIND] PROMPT
```

- `PROMPT`: a single argv element (may contain newlines). Alternatively the
  harness may pass `--kind` only; the prompt is always argv, never stdin,
  so shell history and process tables show the invocation shape honestly.
- `--kind KIND`: one of the closed enum; default `assess`.
- stdout: the response text (arbitrary bytes; treated as inert data).
- stderr: diagnostics. Exit 0 = success. Non-zero = failure (§6 R4).
- Resolution: `$CLAUDE_BIN` if set, else `claude` on `PATH`.
- Timeout: the harness kills the process after `claude_timeout_s`
  (default 120); kill → §6 R5.

Backings:

- **stub** (`scripts/claude-stub`): deterministic test double. Response is a
  pure function of (kind, prompt): `verdict: ROUTINE|URGENT` derived from
  `sha256(kind + "\x00" + prompt)`, wrapped as
  `[stub:<kind>:<sha16>]\nverdict: <V>\n`. No network. Byte-identical across
  runs and machines.
- **production**: the real CLI (API-backed). Not implemented in this tree;
  specified here so the stub can be swapped without changing the harness.
  Key management, model selection, and cost accounting are production
  concerns and out of scope.

Every transcript records `claude.backing` (`stub` or the resolved binary
path) and `claude.kind` per request. A stub-backed transcript must never be
presented as a production inference.

## 3. The `infer` loop

Command: `python -m core.package.author_channels infer --agent NAME
--event JSON [--max-rounds N] [--claude-timeout-s S]` (also callable as
`author_infer.infer_loop(...)`).

Semantics:

1. Round r = 1: build the contained commission
   `{"mode": "infer", "agent": NAME, "event": EVENT,
     "inference_results": []}` and execute it via `run_contained`
   (the Half 1 containment machinery, unchanged).
2. Parse the contained stdout per §1. On violation → refuse (R1..R3,R6),
   transcript records the violation, run ends.
3. If no prompt-requests: adopt `result.json`'s `agent_result`, write the
   transcript, outcome `complete`.
4. Else, for each request in order: `prompt_sha256 = sha256(prompt)`;
   invoke `claude --kind KIND PROMPT` harness-side; on success append the
   inference result; on failure → refuse (R4/R5), run ends.
5. If r == max_rounds and requests remain → refuse (R7), run ends.
   Else r += 1 and repeat from step 1 with the accumulated
   `inference_results`.

The agent entry contract (`core/package/<NAME>.py` in the tree, copied into
the scratch):

```python
def handle(event: dict, inference_results: list[dict]) -> dict: ...
```

- `event`: the original event (principal prompt, world data — any JSON).
- `inference_results`: list of §4 results from prior rounds (possibly empty).
- Returns: JSON-serializable dict, written to `result.json` as `agent_result`.
- May print anything to stdout; only §1 blocks are honored.

## 4. Inference-result event shape

```json
{"request_id": "pr-1", "kind": "classify",
 "prompt_sha256": "<hex>", "text": "<claude stdout>",
 "text_sha256": "<hex>"}
```

Staged into the next round's commission. It is harness-service data, not a
principal/world channel code; the afferent–efferent triad is unchanged.

## 5. Transcript shape

`infer_loop` returns (and the CLI prints as JSON):

```json
{"agent": "demo_classifier", "outcome": "complete",
 "rounds": [
   {"round": 1, "requests": [
      {"request_id": "pr-1", "kind": "classify",
       "prompt_sha256": "<hex>", "response_sha256": "<hex>",
       "claude_exit": 0}],
    "agent_stdout_sha256": "<hex>"},
   {"round": 2, "requests": [], "agent_stdout_sha256": "<hex>"}],
 "result": {"verdict": "ROUTINE", "...": "..."},
 "claude": {"backing": "stub", "timeout_s": 120},
 "bounds": {"max_rounds": 3, "max_requests_per_round": 8,
            "max_prompt_bytes": 65536}}
```

`outcome` is one of `complete | refused`. On `refused`, `refusal_reasons`
lists the §6 reasons and `result` is absent (nothing adopted).

## 6. Refusals (closed list)

- R1: malformed prompt-request (V1..V6) — reasons name the violation.
- R2: > 8 prompt-requests in one round (V7).
- R3: unknown kind (V2 — also listed here as a refusal cause).
- R4: `claude` exits non-zero — reasons include exit code + stderr tail.
- R5: `claude` timeout — reasons include the timeout value.
- R6: contained agent crashes / contained timeout — the Half 1
  quarantine/timeout rules apply; the round is refused, nothing adopted.
- R7: max rounds reached with requests still pending.

Refusals are fail-closed: no partial adoption, no retry inside the run.
The operator re-drives. Every refusal is recorded in the transcript.

## 7. Determinism and replay

- The agent function is required deterministic: identical
  (event, inference_results) → identical `agent_result` and identical
  prompt-requests. (The harness cannot enforce this for arbitrary agents;
  the demo agent and golden battery assert it by two-run comparison.)
- With a fixed backing, replay reproduces the transcript byte-identically
  after scratch-name normalization (per-run scratch counters excluded, same
  rule as Half 1 diagnostics).
- The golden battery asserts two-run transcript equality for the demo.

## 8. Bounds (normative values)

| bound | default | overridable |
|---|---|---|
| max_rounds | 3 | `--max-rounds` |
| max_requests_per_round | 8 | no |
| max_prompt_bytes | 65536 | no |
| claude_timeout_s | 120 | `--claude-timeout-s` |
