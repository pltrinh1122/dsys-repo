"""Artifact registry — mechanical, factory-side (customization bridge).

The customization sequence's mechanical half: prove-absence lookups and
versioned registration of adopted customizations (schemas, criteria,
contracts). Content-addressed: every record pins sha256 of the exact
bytes registered. Registration is append-only and versioned — a new
customization of the same (kind, name) becomes vN+1, never an overwrite.

Nothing here infers. The customizer agent drafts; the operator disposes;
this module records.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

ArtifactKind = Literal["schema", "criteria", "contract"]


class RegistryError(Exception):
    """Fail-closed: every registry refusal carries reasons."""


class ArtifactRecord(BaseModel):
    kind: ArtifactKind
    name: str
    version: int = Field(ge=1)
    sha256: str
    bytes_len: int = Field(ge=1)
    producer: str  # agent label that drafted it, e.g. "customizer"
    commission_id: str
    disposition_ref: str  # the operator adoption this registration rests on
    seq: int = Field(ge=1)


def _path(root: Path) -> Path:
    return Path(root) / "artifact-registry.jsonl"


def _read(root: Path) -> list[dict]:
    p = _path(root)
    if not p.exists():
        return []
    return [json.loads(ln) for ln in p.read_text().splitlines() if ln.strip()]


def lookup(root: Path, kind: str, query: str) -> list[ArtifactRecord]:
    """Mechanical prove-absence query: substring match on name.

    Returns matching records (latest version per name). An empty return
    IS the absence evidence the customization sequence requires — it is
    computed, never asserted.
    """
    if kind not in ("schema", "criteria", "contract"):
        raise RegistryError(f"unknown artifact kind {kind!r}")
    q = query.strip().lower()
    if not q:
        raise RegistryError("lookup query must be non-empty")
    latest: dict[str, ArtifactRecord] = {}
    for raw in _read(root):
        if raw["kind"] != kind:
            continue
        rec = ArtifactRecord(**raw)
        prev = latest.get(rec.name)
        if prev is None or rec.version > prev.version:
            latest[rec.name] = rec
    return [r for name, r in sorted(latest.items()) if q in name.lower()]


def latest_version(root: Path, kind: str, name: str) -> ArtifactRecord | None:
    """Latest registered version of (kind, name), or None if absent."""
    recs = [r for r in lookup(root, kind, name)
            if r.name.lower() == name.lower()]
    return max(recs, key=lambda r: r.version) if recs else None


def register(root: Path, *, kind: str, name: str, artifact_bytes: bytes,
             producer: str, commission_id: str,
             disposition_ref: str) -> ArtifactRecord:
    """Register an ADOPTED customization. Fail-closed:

    - no disposition_ref -> refused (registration rests on disposition);
    - identical bytes already registered -> refused (already registered);
    - same (kind, name), new bytes -> new version (never an overwrite);
    - commission_id equal to the producing commission of the latest
      version -> refused: post-release customization of a delivered
      artifact under its original commission is the falsified claim
      made mechanical — open a new commission (a new authoring cycle).
    """
    if not artifact_bytes:
        raise RegistryError("cannot register empty artifact bytes")
    if not disposition_ref or not disposition_ref.strip():
        raise RegistryError(
            "registration refused: no operator disposition_ref — "
            "artifacts register on disposition, never on drafting")
    if not commission_id or not commission_id.strip():
        raise RegistryError("registration refused: commission_id required")
    name = name.strip()
    if not name:
        raise RegistryError("registration refused: artifact name required")

    sha = hashlib.sha256(artifact_bytes).hexdigest()
    prev = latest_version(root, kind, name)
    if prev is not None and prev.sha256 == sha:
        raise RegistryError(
            f"already registered: {kind}/{name} v{prev.version} "
            f"pins identical bytes ({sha[:12]}…)")
    if prev is not None and prev.commission_id == commission_id:
        raise RegistryError(
            f"post-release customization refused: {kind}/{name} v{prev.version} "
            f"was delivered under {commission_id}; customizing a delivered "
            f"artifact under its original commission is refused — open a new "
            f"commission (a new authoring cycle produces v{prev.version + 1})")

    version = 1 if prev is None else prev.version + 1
    recs = _read(root)
    rec = ArtifactRecord(
        kind=kind, name=name, version=version, sha256=sha,
        bytes_len=len(artifact_bytes), producer=producer,
        commission_id=commission_id, disposition_ref=disposition_ref,
        seq=len(recs) + 1)
    with _path(root).open("a") as f:
        f.write(rec.model_dump_json() + "\n")
    return rec


def find_by_sha256(root: Path, sha256: str) -> ArtifactRecord | None:
    """First record pinning these exact bytes, or None.

    Additive lookup for the contracted write channel
    (`tool-register-artifact`): on a duplicate content-hash the tool
    returns the existing receipt instead of appending a second row.
    First (lowest-seq) record wins — the original registration.
    Changes no existing behavior.
    """
    for raw in _read(root):
        if raw.get("sha256") == sha256:
            return ArtifactRecord(**raw)
    return None


def absence_evidence(root: Path, kind: str, query: str) -> dict:
    """The evidence object a proposal must carry: the query, run now,
    and the hit names it returned. The propose channel re-runs this and
    compares — evidence is verified, not trusted."""
    hits = lookup(root, kind, query)
    return {"kind": kind, "query": query,
            "hits": [h.name for h in hits]}
