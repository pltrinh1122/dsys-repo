#!/usr/bin/env python3
"""Golden run for tool-register-artifact (lib/dsys/tools/register_artifact.py).

Mechanical verification for the DR-CMD-102 tranche-1 build, following
the repo's golden-run pattern and the DR-CMD-055 tool discipline
(contract spec: doc/tool-register-artifact-spec.md).

Sections:
  A. Clean registration — receipt fields, registry row appended.
  B. Duplicate content-hash — existing receipt returned, no new row,
     tip does not advance (idempotency, the F-E3 analog).
  C. New bytes, same (kind, name) — version N+1, never an overwrite;
     the v1 row is intact.
  D. Malformed inputs refused — every required input, fail-closed with
     a reason (ToolAborted).
  E. Registry refusals preserved verbatim — the post-release
     commission rule reaches the caller as ToolAborted with the
     registry's reason.
  F. Compiler routing — the write-scope channel 'artifact-registry'
     resolves to ['tool-register-artifact'] through the J1 registry
     (the recorder unblock, checked at the routing stage).
  G. Real loading path — executor.load_tools picks the tool up by its
     TOOL_NAME (this module's leading underscore keeps the golden run
     itself out of the registry).
  H. Determinism — identical registrations in fresh roots yield
     byte-identical receipts.

Returns {'ok', 'violations', 'cases'}. Prints RESULT: PASS/FAIL.
"""

import hashlib
import json
import sys
import tempfile
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
LIB_DSYS = TOOLS_DIR.parent
REPO_ROOT = LIB_DSYS.parent.parent  # <repo>/lib/dsys/tools -> <repo>
for p in (str(TOOLS_DIR), str(LIB_DSYS), str(REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

import _common as C  # noqa: E402
import register_artifact as T  # noqa: E402
import executor as X  # noqa: E402

CASES = 0
VIOLATIONS: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    global CASES
    CASES += 1
    if not cond:
        VIOLATIONS.append(f"{name}: {detail}")


def fresh_root() -> Path:
    return Path(tempfile.mkdtemp(prefix="ra-golden-"))


def base_ctx(root: Path, **kw) -> dict:
    ctx = {
        "artifact_registry_root": str(root),
        "artifact_bytes": b'{"$schema": "test/v1"}',
        "kind": "schema",
        "name": "test-schema",
        "producer": "customizer",
        "commission_id": "commission:test-1",
        "disposition_ref": "DR-CMD-102",
    }
    ctx.update(kw)
    return ctx


def registry_rows(root: Path) -> list[dict]:
    p = root / "artifact-registry.jsonl"
    if not p.exists():
        return []
    return [json.loads(ln) for ln in p.read_text().splitlines() if ln.strip()]


def run() -> dict:
    # -- A. clean registration -------------------------------------------
    root = fresh_root()
    out = T.run(base_ctx(root))
    check("RA-A1", out["ok"] is True, f"ok flag: {out}")
    r = out["result"]
    check("RA-A2", r["registered"] is True and r["duplicate"] is False,
          f"flags: {r}")
    receipt = r["receipt"]
    expect_sha = hashlib.sha256(b'{"$schema": "test/v1"}').hexdigest()
    check("RA-A3", receipt["sha256"] == expect_sha
          and receipt["version"] == 1 and receipt["seq"] == 1
          and receipt["kind"] == "schema" and receipt["name"] == "test-schema"
          and receipt["bytes_len"] == len(b'{"$schema": "test/v1"}')
          and receipt["disposition_ref"] == "DR-CMD-102",
          f"receipt: {receipt}")
    check("RA-A4", len(registry_rows(root)) == 1, "one row appended")
    d = out["ctx_delta"]
    check("RA-A5", d["artifact_registered"] is True
          and d["artifact_sha256"] == expect_sha
          and d["artifact_version"] == 1 and d["artifact_seq"] == 1,
          f"delta: {d}")
    # result + delta must be JSON-shaped (the executor enforces this).
    try:
        json.dumps(r)
        json.dumps(d)
        json_ok = True
    except (TypeError, ValueError):
        json_ok = False
    check("RA-A6", json_ok, "result/delta not JSON-shaped")

    # -- B. duplicate content-hash -> existing receipt, no new row --------
    out2 = T.run(base_ctx(root))
    r2 = out2["result"]
    check("RA-B1", out2["ok"] is True and r2["registered"] is False
          and r2["duplicate"] is True, f"flags: {r2}")
    check("RA-B2", r2["receipt"] == receipt, "existing receipt returned")
    check("RA-B3", len(registry_rows(root)) == 1,
          "no second row appended on duplicate")
    check("RA-B4", out2["ctx_delta"]["artifact_seq"] == 1,
          "tip did not advance on duplicate")

    # -- C. new bytes, same (kind, name) -> v2, append-only ---------------
    v2_bytes = b'{"$schema": "test/v2"}'
    out3 = T.run(base_ctx(root, artifact_bytes=v2_bytes,
                          commission_id="commission:test-2"))
    r3 = out3["result"]
    check("RA-C1", r3["registered"] is True and r3["duplicate"] is False,
          f"flags: {r3}")
    check("RA-C2", r3["receipt"]["version"] == 2
          and r3["receipt"]["seq"] == 2
          and r3["receipt"]["sha256"]
          == hashlib.sha256(v2_bytes).hexdigest(),
          f"receipt: {r3['receipt']}")
    rows = registry_rows(root)
    check("RA-C3", len(rows) == 2 and rows[0]["version"] == 1
          and rows[0]["sha256"] == expect_sha,
          "v1 row intact — append-only, never overwritten")

    # -- D. malformed inputs refused --------------------------------------
    bad_cases = {
        "missing-root": {"artifact_registry_root": ""},
        "empty-bytes": {"artifact_bytes": b""},
        "bytes-not-bytes": {"artifact_bytes": "not-bytes"},
        "bad-kind": {"kind": "policy"},
        "empty-name": {"name": "   "},
        "missing-producer": {"producer": ""},
        "missing-commission": {"commission_id": ""},
        "missing-disposition": {"disposition_ref": ""},
    }
    for label, kw in bad_cases.items():
        try:
            T.run(base_ctx(fresh_root(), **kw))
            check(f"RA-D-{label}", False, "no refusal raised")
        except C.ToolAborted as e:
            check(f"RA-D-{label}", bool(str(e)), "empty refusal reason")

    # -- E. registry refusals preserved verbatim --------------------------
    root_e = fresh_root()
    T.run(base_ctx(root_e))  # v1 under commission:test-1
    try:
        T.run(base_ctx(root_e, artifact_bytes=b'{"$schema": "test/v3"}'))
        check("RA-E1", False, "post-release customization not refused")
    except C.ToolAborted as e:
        check("RA-E1", "post-release customization refused" in str(e),
              f"reason not verbatim: {e}")
    # ... but a NEW commission for new bytes is the honest path (v2).
    out_e = T.run(base_ctx(root_e, artifact_bytes=b'{"$schema": "test/v3"}',
                           commission_id="commission:test-2"))
    check("RA-E2", out_e["result"]["receipt"]["version"] == 2,
          f"v2 under new commission: {out_e['result']}")

    # -- F. compiler routing: 'artifact-registry' resolves ----------------
    sys.path.insert(0, str(REPO_ROOT))
    from core.package import factory_compiler as FC  # noqa: E402
    resolved = FC._resolve_channel("artifact-registry")
    check("RA-F1", resolved == ["tool-register-artifact"],
          f"resolved: {resolved}")
    check("RA-F2", "tool-register-artifact" in FC.AGENT_TOOL_IDS,
          "tool id in the closed registry")
    check("RA-F3", FC.CHANNEL_ALIASES.get("artifact-registry")
          == ["tool-register-artifact"], "alias registered")
    check("RA-F4", FC.TOOL_REGISTRY_PIN.startswith("contracted-tools-v1:"),
          f"pin: {FC.TOOL_REGISTRY_PIN}")

    # -- G. real loading path ---------------------------------------------
    # (load_tools re-imports under a synthetic module name, so verify
    # the loaded run comes from this file rather than function identity.)
    import inspect  # noqa: E402
    registry = X.load_tools(TOOLS_DIR)
    loaded = registry.get("tool-register-artifact")
    check("RA-G1", callable(loaded) and loaded.__name__ == "run"
          and Path(inspect.getsourcefile(loaded)).name
          == "register_artifact.py",
          "tool loads by TOOL_NAME through executor.load_tools")

    # -- H. determinism ----------------------------------------------------
    ra = T.run(base_ctx(fresh_root()))["result"]["receipt"]
    rb = T.run(base_ctx(fresh_root()))["result"]["receipt"]
    check("RA-H1",
          json.dumps(ra, sort_keys=True) == json.dumps(rb, sort_keys=True),
          "identical registrations in fresh roots differ")

    return {"ok": not VIOLATIONS, "violations": VIOLATIONS, "cases": CASES}


if __name__ == "__main__":
    res = run()
    print(f"RESULT: {'PASS' if res['ok'] else 'FAIL'} "
          f"({res['cases']} cases, {len(res['violations'])} violations)")
    for v in res["violations"]:
        print(f"  VIOLATION: {v}")
    sys.exit(0 if res["ok"] else 1)
