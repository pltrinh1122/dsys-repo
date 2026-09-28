# `tool-register-artifact` spec: the contracted write channel for the artifact registry

**Status: ADOPTED for build** — tranche-1 commission under DR-CMD-102 (2026-09-27, Peter; O1 adopted-with-conditions): build the contracted `tool-register-artifact` now, per DR-CMD-055 tool discipline. Tranche 2 (triage channels, DR registration channel) is conditional and NOT commissioned by this spec.

This spec is the build contract for `tool-register-artifact`: the contracted tool backing the write-scope channel `artifact-registry` (recorder's channel, DR-CMD-096; renamed from registrar_clerk, DR-CMD-107). It settles the tool's contract, its refusal cases, its idempotency argument, and its registration in the compiler's closed contracted-tool registry (J1) — an addition under the standing discipline, not an amendment of J1 (O3 was refused; the closed-registry discipline stays intact).

## 1. What this spec is

`tool-register-artifact` is a dist-shipped `lib/dsys/tools/` module. Like the eight production tools (DR-CMD-055/056/057), it defines `TOOL_NAME: str` and `run(ctx: dict) -> {"ok": bool, "result": <json>, "ctx_delta": <json>}`, loaded by the executor's `load_tools` (no overlays, no search paths). It is the contracted write path into the content-addressed append-only artifact registry (`core/package/artifact_registry.py`, built under DR-CMD-091): given artifact bytes plus metadata, it computes the content hash, appends to the registry, and returns a receipt.

The registry exists as a contracted structure with no contracted write path today — `adopt-proposal` writes through direct ambient-side `register()` calls. This tool closes that half of the DR-CMD-091 bridge. It also unblocks `recorder` (DR-CMD-096; renamed from registrar_clerk, DR-CMD-107), whose compile refusal at routing names exactly this missing tool, and the DR-CMD-099 schema-artifact registration path.

## 2. The tool contract

- **Deterministic** (declared) and **idempotent** (required): crash recovery is at-least-once. Re-invocation with identical bytes never appends a second row — it returns the existing receipt (§4).
- **Hermetic:** no network, no subprocesses, no wall-clock. The tool runs in-process (`run(ctx)` in the executor's process, per the production-tools spec §2). The only filesystem touch is the registry root it is given.
- **Pure mechanical, zero inference.** Every refusal carries its reason verbatim.

### 2.1 Inputs (`ctx`)

All inputs are bound by the caller at disposition time (the Q2 direct-call discipline: exactly one contracted-tool call, all arguments bound — no dependence on prior tool results). Every missing or malformed input is a fail-closed refusal (`ToolAborted`, reason verbatim); nothing is defaulted or invented (the feed-URL precedent: a missing pin aborts loudly).

| Key | Type | Required | Rule |
|---|---|---|---|
| `artifact_registry_root` | str (path) | yes | The registry root directory. No invented default — absent or empty refuses. |
| `artifact_bytes` | bytes | yes | Non-empty. Passed in-process (the registry's own `register()` takes bytes; no encoding ceremony). |
| `kind` | str | yes | One of `schema`, `criteria`, `contract` (the registry's `ArtifactKind`). |
| `name` | str | yes | Non-empty after stripping. |
| `producer` | str | yes | Agent label that drafted the artifact (e.g. `customizer`). |
| `commission_id` | str | yes | The commission the artifact was authored under. |
| `disposition_ref` | str | yes | The operator disposition the registration rests on. Registration never happens on drafting alone — the registry enforces this; the tool passes the refusal through verbatim. |

### 2.2 Outputs

`run(ctx)` returns `{"ok": True, "result", "ctx_delta"}`:

- `result.registered: bool` — True when a new row was appended.
- `result.duplicate: bool` — True when the content-hash was already registered; the existing receipt is returned and no row is appended (§4).
- `result.receipt: dict` — the `ArtifactRecord`: `{kind, name, version, sha256, bytes_len, producer, commission_id, disposition_ref, seq}`.
- `ctx_delta` — small and JSON-shaped (the FlowTransitionEvent.payload discipline): `{artifact_registered, artifact_sha256, artifact_kind, artifact_name, artifact_version, artifact_seq}`.

### 2.3 Refusals (fail-closed, reasons verbatim)

- Missing/empty `artifact_registry_root`, empty `artifact_bytes`, unknown `kind`, empty `name`/`producer`/`commission_id`/`disposition_ref` → `ToolAborted` naming the missing input.
- Registry `RegistryError` → `ToolAborted` with the registry's reason verbatim, *except* the already-registered case (§4). This preserves the registry's own load-bearing refusals: no-disposition registration, and the post-release-commission rule (customizing a delivered artifact under its original commission is refused — open a new commission).

## 3. Registry semantics preserved

The tool is a thin contracted wrapper; the registry's semantics are untouched:

- **Append-only:** new bytes for an existing `(kind, name)` become version N+1; no row is ever overwritten.
- **Content-addressed:** every record pins sha256 of the exact bytes registered.
- **Disposition-gated:** `disposition_ref` is required — artifacts register on disposition, never on drafting.
- **Post-release rule:** same `commission_id` as the latest version with new bytes is refused (fail-closed, reason verbatim).

One additive helper, `find_by_sha256(root, sha256)`, joins the registry module so the tool can return the existing receipt on duplicates. It changes no existing behavior.

## 4. Idempotency argument (the F-E3 analog)

Duplicate content-hash → the tool returns the existing receipt with `registered: False, duplicate: True` and appends nothing. Crash re-invocation after a successful commit is therefore non-duplicating: the second call observes the first call's row and returns its receipt. The duplicate test requires the found record's `(kind, name)` to match the request — a same-bytes-different-name registration is the registry's versioning business, not a duplicate, and the tool does not conflate them. Registry tip (`seq`) advances only on genuine new registrations.

## 5. Module layout (dist vs repo tree)

The tool is dist-shipped at `lib/dsys/tools/register_artifact.py`; the registry module ships at `lib/core/package/artifact_registry.py` (the install tree vendors `core/package/` under `lib/core/`). In the repo working tree the layout is `core/package/` beside `lib/dsys/`. The tool resolves the registry module by probing, in order: `<tool-dir>/../../core/package` (dist: `lib/core/package`) then `<tool-dir>/../../../core/package` (repo tree), inserting the right parent so `from core.package.artifact_registry import …` resolves. First match wins, deterministic; if neither exists the tool aborts loudly rather than running without the registry.

## 6. Compiler registration (J1 addition, not amendment)

- `tool-register-artifact` joins `AGENT_TOOL_IDS` in `core/package/factory_compiler.py`.
- New channel alias: `artifact-registry` → [`tool-register-artifact`], so recorder's `write_scope=["artifact-registry"]` resolves at the routing stage.
- `TOOL_REGISTRY_PIN` recomputes from the id list automatically — the pin mechanism is exactly the established path for registry membership changes. The J1 discipline (channels resolve against the *closed* registry; unknown channels refuse loudly) is unchanged: the registry stays closed, it now has nine members. This is the addition O1 commissioned; O3 (amending the discipline) was refused and is not what this is.

No schema-enum or schema-field change is involved, so no minor schema bump under the DR-CMD-082 rule; the pin digest captures the membership change inside `FactoryVersion`.

## 7. What this spec does not commission

- Tranche 2 channels (triage, DR registration) — explicitly not authorized (DR-CMD-102).
- The DR-registry structure design — still open follow-on work (DR-CMD-100).
- Registration of `recorder` itself — a green build stages it for Peter's registration disposition; `CLERK.members` stays `()` until he disposes.

## Glossary

- **Contracted tool:** a tool whose id is registered in the compiler's closed contracted-tool registry (J1); the only tools a built agent's write-scope channels may resolve to.
- **J1:** the compiler's closed-registry discipline — write-scope channels resolve against registered tool ids or aliases; anything else is a loud refusal at the routing stage.
- **Receipt:** the `ArtifactRecord` returned for a registration: kind, name, version, content hash, byte length, producer, commission, disposition reference, and registry sequence number.
- **Idempotent (F-E3):** re-invocation under at-least-once crash recovery is safe — duplicate inputs return the existing receipt instead of duplicating the effect.
- **`ToolAborted`:** the tool's refusal exception; the executor's C1 normalizes it into the failure record with the reason preserved verbatim.
