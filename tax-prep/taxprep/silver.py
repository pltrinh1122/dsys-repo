"""Silver layer: typed artifact derivation (Arc B medallion, W2).

Derives the ``silver_artifact`` rows that mirror a document's operational
field store (``silver_doc.fields_json``), per contract section 5: every
mutation path (ingest derivation, review edit/validate, re-derivation)
updates both inside one transaction.

Artifact types (contract section 4):

- ``field``   — one per fields-dict key (extracted keys; review
  bookkeeping keys prefixed ``__`` are excluded — they are
  operator-authored, carried in ``fields_json`` only, and preserved
  verbatim across re-derivation).
- ``payer``   — one per payer block (``payer1.*`` keys grouped under the
  ``payer1`` anchor).
- ``lot``     — one per 1099-B lot (``fields["lots"]["value"][i]``,
  anchor ``f"lot:{i}"``).
- ``section`` — one for an R1 split section (split-child documents only).

Artifact ids are stable per contract section 6:
``sha256(bronze_hash:page:type:anchor)[:32]`` — re-running a derivation
with the same version reproduces byte-identical rows (I5).

``canonical_json`` here is deliberately byte-identical to
``taxprep.mstore._canon`` (``json.dumps`` with ``sort_keys=True``,
compact separators, ``ensure_ascii=True``, ``default=str``): artifact
rows must compare equal no matter which write path produced them.

Re-derivation semantics (I6, R16 spec): see :func:`reconcile_rederivation`.
Validated values win over re-derived values; a validated field whose
re-derived value differs keeps the validated value and the document is
flagged ``re_review``; a validated field that disappears from the new
extraction is dropped from the operational store and its decisions are
flagged orphaned (append-only — decision rows are never deleted).
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import NamedTuple

from . import extractors

# ---------------------------------------------------------------------------
# Artifact vocabulary
# ---------------------------------------------------------------------------

FIELD = "field"
PAYER = "payer"
LOT = "lot"
SECTION = "section"

ARTIFACT_TYPES = (FIELD, PAYER, LOT, SECTION)

# Review-managed bookkeeping keys (form_type / tax_year corrections, ...).
# Operator-authored: never derived, never overwritten by re-derivation,
# excluded from artifacts (their audit trail is fields_json history +
# the decision log).
BOOKKEEPING_PREFIX = "__"

_PAYER_KEY_RE = re.compile(r"^(payer\d+)\.(.+)$")


# ---------------------------------------------------------------------------
# Stable identifiers (contract section 6)
# ---------------------------------------------------------------------------

def artifact_id_for(doc_id: str, bronze_hash: str, page: int,
                    artifact_type: str, anchor: str) -> str:
    """Stable artifact id.

    sha256(doc_id:bronze_hash:page:type:anchor)[:32]. The doc_id is
    included because one bronze routinely feeds many silver docs (R1
    split children, CSV rows); doc_id is content-derived and stable, so
    I5 determinism holds and ids are unique per artifact.
    """
    return hashlib.sha256(
        f"{doc_id}:{bronze_hash}:{page}:{artifact_type}:{anchor}".encode(
            "utf-8")
    ).hexdigest()[:32]


# ---------------------------------------------------------------------------
# Canonical JSON / config / digests (contract section 7)
# ---------------------------------------------------------------------------

def canonical_json(obj) -> str:
    """Canonical JSON for artifact values and config hashes.

    Byte-identical to ``taxprep.mstore._canon`` by construction: sorted
    keys, compact separators, ASCII, ``default=str`` for non-natives
    (Decimal money values that escaped string form, datetimes, ...).
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, default=str)


def derivation_config() -> dict:
    """Derivation-relevant config (contract section 7).

    Captures everything besides the extractor version that can change
    derived bytes: the OCR modes/engines offered and the section-split
    backend. Bump ``EXTRACTOR_VERSION`` (not this) on extraction-logic
    changes.
    """
    return {
        "extractor_version": extractors.EXTRACTOR_VERSION,
        "ocr": {
            "modes": ["skip-text", "redo-ocr", "force-ocr"],
            "engine_preference": ["ocrmypdf", "tesseract"],
        },
        "split": {"backend": "extractors.split_form_sections"},
    }


def config_hash_of(config: dict) -> str:
    """sha256 of the canonical JSON of a derivation config."""
    return hashlib.sha256(
        canonical_json(config).encode("utf-8")).hexdigest()


def derivation_digest_for(*, bronze_hash: str, derivation_version: str,
                          config_hash: str) -> str:
    """Digest over the derivation inputs (contract section 4).

    Bound to the bronze bytes (by content hash), the extractor version,
    and the config hash. The derived text is a deterministic function of
    exactly these inputs, so the digest identifies the derivation
    without restating the text. Recomputable on any mutation path that
    does not re-derive (review validate/edit, sync orphan).
    """
    return hashlib.sha256(canonical_json({
        "bronze_hash": bronze_hash,
        "derivation_version": derivation_version,
        "config_hash": config_hash,
    }).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Canonical value comparison (moved from ingest.py; numeric-aware)
# ---------------------------------------------------------------------------

def _canon_value(v):
    """Canonical form for comparing extracted values across derivations.

    Numeric values compare by value, not by representation: an Operator
    correction stored as the Decimal-safe string "10000.00" agrees with
    an extracted float 10000.0. Non-numeric values compare as strings;
    containers recurse.
    """
    if isinstance(v, bool):
        return ("bool", v)
    if isinstance(v, (int, float, Decimal)):
        try:
            return ("num", str(Decimal(str(v)).normalize()))
        except InvalidOperation:
            pass
    if isinstance(v, str):
        s = v.strip().replace("$", "").replace(",", "")
        if s:
            try:
                return ("num", str(Decimal(s).normalize()))
            except InvalidOperation:
                pass
        return ("str", v)
    if isinstance(v, (list, tuple)):
        return ("list", tuple(_canon_value(x) for x in v))
    if isinstance(v, dict):
        return ("dict", tuple(sorted((str(k), _canon_value(x))
                                     for k, x in v.items())))
    return ("str", str(v))


def _field_value(entry):
    """The comparable value inside a field entry dict."""
    if isinstance(entry, dict):
        return entry.get("value")
    return entry


def fields_agree(old: dict, new: dict) -> bool:
    """True when two field dicts carry the same canonical values.

    Bookkeeping keys (``__`` prefix) are compared like any other key;
    callers that want them ignored filter first.
    """
    old = old or {}
    new = new or {}
    if set(old) != set(new):
        return False
    for code in old:
        if _canon_value(_field_value(old[code])) != _canon_value(
                _field_value(new[code])):
            return False
    return True


# ---------------------------------------------------------------------------
# Artifact derivation
# ---------------------------------------------------------------------------

def best_page_for_doc(doc) -> int:
    """Best-known 1-based page for a document's artifacts, else 0.

    Split children report the first page of their page range; anything
    else reports 0 (page unknown at the artifact level — R15 geometry
    would refine this when available).
    """
    page_range = getattr(doc, "page_range", None)
    if page_range:
        try:
            return int(str(page_range).split("-")[0])
        except (ValueError, IndexError):
            pass
    return 0


def field_artifact_value(field_entry: dict) -> str:
    """Canonical value_json for a field artifact (contract section 5:
    the artifact mirrors the operational field entry)."""
    return canonical_json(field_entry)


def _payer_groups(fields: dict) -> dict[str, dict]:
    """Group ``payerN.*`` field keys into payer blocks."""
    groups: dict[str, dict] = {}
    for key in sorted(fields):
        if key.startswith(BOOKKEEPING_PREFIX):
            continue
        m = _PAYER_KEY_RE.match(key)
        if m:
            groups.setdefault(m.group(1), {})[m.group(2)] = fields[key]
    return groups


def _lot_list(fields: dict) -> list | None:
    """The 1099-B lot table as a list, or None when absent."""
    lots = fields.get("lots")
    if isinstance(lots, dict):
        lots = lots.get("value")
    return lots if isinstance(lots, list) else None


def _section_anchor(doc) -> str | None:
    """Stable anchor for an R1 split section, else None.

    The child doc_id is ``<parent>-p<range>-<section-hash>`` (contract
    section 6); the section anchor is the doc_id suffix after the
    parent prefix.
    """
    parent = getattr(doc, "parent_doc_id", None)
    doc_id = getattr(doc, "doc_id", "")
    if not parent:
        return None
    prefix = parent + "-"
    if doc_id.startswith(prefix):
        return doc_id[len(prefix):]
    return None


def _artifact_row(*, doc_id: str, bronze_hash: str, page: int,
                  artifact_type: str, anchor: str, value_json: str,
                  offsets_json: str | None,
                  derivation_version: str, config_hash: str) -> dict:
    return {
        "artifact_id": artifact_id_for(doc_id, bronze_hash, page,
                                       artifact_type, anchor),
        "doc_id": doc_id,
        "bronze_hash": bronze_hash,
        "page": page,
        "artifact_type": artifact_type,
        "anchor": anchor,
        "value_json": value_json,
        "offsets_json": offsets_json,
        "derivation_version": derivation_version,
        "config_hash": config_hash,
    }


def derive_artifacts(doc, bundle=None, *, bronze_hash: str,
                     derivation_version: str, config_hash: str) -> list[dict]:
    """Derive the silver artifact rows mirroring a document's fields.

    Deterministic: the same ``(doc.fields, bronze_hash, page,
    derivation_version, config_hash)`` always yields byte-identical
    rows (I5). ``bundle`` (the ingest PageBundle) is accepted for
    signature compatibility and future R15 geometry; per-page offsets
    are not produced by the current extractors, so ``offsets_json`` is
    None.
    """
    page = best_page_for_doc(doc)
    fields = getattr(doc, "fields", None) or {}
    doc_id = getattr(doc, "doc_id", "")
    out: list[dict] = []

    def _row(artifact_type: str, anchor: str, value_json: str) -> dict:
        return _artifact_row(
            doc_id=doc_id, bronze_hash=bronze_hash, page=page,
            artifact_type=artifact_type, anchor=anchor,
            value_json=value_json, offsets_json=None,
            derivation_version=derivation_version, config_hash=config_hash,
        )

    # One 'field' artifact per fields-dict key (bookkeeping excluded).
    for key in sorted(fields):
        if key.startswith(BOOKKEEPING_PREFIX):
            continue
        entry = fields[key]
        out.append(_row(
            FIELD, key,
            field_artifact_value(entry if isinstance(entry, dict)
                                 else {"value": entry})))
    # One 'payer' artifact per payer block.
    for payer_key in sorted(_payer_groups(fields)):
        out.append(_row(PAYER, payer_key,
                        canonical_json(_payer_groups(fields)[payer_key])))
    # One 'lot' artifact per 1099-B lot.
    lots = _lot_list(fields)
    if lots is not None:
        for i, lot in enumerate(lots):
            out.append(_row(LOT, f"lot:{i}",
                            canonical_json(lot if isinstance(lot, dict)
                                           else {"value": lot})))
    # One 'section' artifact for an R1 split section.
    section_anchor = _section_anchor(doc)
    if section_anchor is not None:
        out.append(_row(SECTION, section_anchor, canonical_json({
            "form_type": getattr(doc, "form_type", None),
            "tax_year": getattr(doc, "tax_year", None),
            "page_range": getattr(doc, "page_range", None),
            "parent_doc_id": getattr(doc, "parent_doc_id", None),
        })))
    return out


def artifact_anchors(artifacts: list[dict]) -> set[tuple[str, str]]:
    """The ``(artifact_type, anchor)`` identity set of artifact rows."""
    return {(a["artifact_type"], a["anchor"]) for a in (artifacts or [])}


def field_artifact_anchors(fields: dict) -> set[tuple[str, str]]:
    """The ``(type, anchor)`` set a fields dict derives (excl. sections).

    Used to attribute artifact rows to the doc's CURRENT fields: rows
    for anchors outside this set are stale derivations, never the doc's
    current derivation.
    """
    fields = fields or {}
    anchors: set[tuple[str, str]] = set()
    for key in fields:
        if key.startswith(BOOKKEEPING_PREFIX):
            continue
        anchors.add((FIELD, key))
    for payer_key in _payer_groups(fields):
        anchors.add((PAYER, payer_key))
    lots = _lot_list(fields)
    if lots is not None:
        for i in range(len(lots)):
            anchors.add((LOT, f"lot:{i}"))
    return anchors


def dropped_artifacts(old_artifacts: list[dict],
                      new_artifacts: list[dict]) -> list[dict]:
    """Old artifact rows with no counterpart in the new derivation.

    ``section`` artifacts are doc-identity-level (stable per doc_id) and
    are handled by the stale-child logic in ingest, not here.
    """
    new_anchors = artifact_anchors(new_artifacts)
    return [a for a in (old_artifacts or [])
            if (a["artifact_type"], a["anchor"]) not in new_anchors
            and a["artifact_type"] != SECTION]


# ---------------------------------------------------------------------------
# I6 re-derivation reconciliation
# ---------------------------------------------------------------------------

class ReconcileResult(NamedTuple):
    """Outcome of reconciling a re-derivation against Operator decisions."""
    fields: dict          # final operational fields (Semantics B)
    re_review: bool       # True when a validated value changed or vanished


_MISSING = object()


def reconcile_rederivation(*, old_fields: dict, new_fields: dict,
                           validated_keys: set[str] | None) -> ReconcileResult:
    """Reconcile freshly re-derived fields against Operator decisions (I6).

    Semantics B (R16 spec, operator-approved):

    - validated key, re-derived value canon-equal  -> keep the validated
      (old) value;
    - validated key, re-derived value differs      -> keep the validated
      value, flag ``re_review``;
    - validated key, absent from the new extraction -> DROP from the
      operational fields, flag ``re_review`` (the artifact disappears;
      ingest flags the orphaned decisions — decision rows are never
      deleted);
    - non-validated key -> take the new value (or drop when absent);
    - ``__`` bookkeeping keys -> carried over untouched, always
      (operator-authored, never derived).

    Comparison is numeric-aware (:func:`_canon_value`): "10000.00"
    agrees with 10000.0.
    """
    old_fields = old_fields or {}
    new_fields = new_fields or {}
    validated = set(validated_keys or {})
    final: dict = {}
    re_review = False

    # Bookkeeping first: always carried over, never reconciled.
    for key, value in old_fields.items():
        if key.startswith(BOOKKEEPING_PREFIX):
            final[key] = value

    for key in sorted(set(old_fields) | set(new_fields)):
        if key.startswith(BOOKKEEPING_PREFIX):
            continue
        old_v = old_fields.get(key, _MISSING)
        new_v = new_fields.get(key, _MISSING)
        if key in validated:
            if new_v is _MISSING:
                # Validated value vanished from the new extraction:
                # drop it (Semantics B) and flag re-review. The
                # decision log keeps the audit trail.
                re_review = True
                continue
            if old_v is _MISSING:
                final[key] = new_v  # validated but no old value: take new
            elif _canon_value(_field_value(old_v)) == _canon_value(
                    _field_value(new_v)):
                final[key] = old_v
            else:
                final[key] = old_v  # validated wins
                re_review = True
        else:
            if new_v is not _MISSING:
                final[key] = new_v
            # else: unvalidated and gone -> dropped silently
    return ReconcileResult(fields=final, re_review=re_review)


@dataclass
class DerivationContext:
    """The (version, config) pair stamping one derivation."""
    derivation_version: str
    config_hash: str

    @classmethod
    def current(cls) -> "DerivationContext":
        config = derivation_config()
        return cls(derivation_version=extractors.EXTRACTOR_VERSION,
                   config_hash=config_hash_of(config))


# ---------------------------------------------------------------------------
# Store-facing helpers (duck-typed on the contract section 4 Medallion API)
# ---------------------------------------------------------------------------

def derivation_for_doc(store, doc_id: str) -> DerivationContext:
    """A doc's derivation from its artifact rows (majority vote).

    Falls back to the current derivation when the doc has no artifacts
    (e.g. BLOCKED docs derive none). Never returns None -- callers that
    need the unknown sentinel read the artifacts themselves.
    """
    try:
        arts = store.get_artifacts(doc_id) or []
    except Exception:
        arts = []
    if arts:
        votes: dict[tuple, int] = {}
        for a in arts:
            key = (a.get("derivation_version"), a.get("config_hash"))
            votes[key] = votes.get(key, 0) + 1
        best = max(sorted(votes), key=lambda k: votes[k])
        if best[0] is not None:
            return DerivationContext(derivation_version=best[0],
                                     config_hash=best[1] or "")
    return DerivationContext.current()


def bronze_hash_for_doc(store, doc) -> str | None:
    """A doc's bronze hash: its artifacts first (authoritative), then the
    record's source_sha256 (None for tombstone-mapped docs)."""
    try:
        arts = store.get_artifacts(doc.doc_id) or []
    except Exception:
        arts = []
    if arts and arts[0].get("bronze_hash"):
        return arts[0]["bronze_hash"]
    return getattr(doc, "source_sha256", None)


def persist_silver_doc(store, doc, ctx: DerivationContext,
                       bronze_hash: str | None = None) -> None:
    """Write one silver_doc row via upsert_silver_doc.

    The derivation is stamped explicitly (never reset to the
    pre-medallion "1" by this path); the digest is recomputed from
    (bronze_hash, version, config_hash). ``doc.source_sha256`` is keyed
    transiently so tombstone-mapped docs (None) keep their real bronze
    linkage -- the caller's object is restored afterwards.
    """
    if bronze_hash is None:
        bronze_hash = bronze_hash_for_doc(store, doc)
    saved = doc.source_sha256
    if bronze_hash is not None:
        doc.source_sha256 = bronze_hash
    try:
        digest = derivation_digest_for(
            bronze_hash=bronze_hash,
            derivation_version=ctx.derivation_version,
            config_hash=ctx.config_hash)
        store.upsert_silver_doc(
            doc, derivation_version=ctx.derivation_version,
            config_hash=ctx.config_hash, derivation_digest=digest)
    finally:
        doc.source_sha256 = saved
