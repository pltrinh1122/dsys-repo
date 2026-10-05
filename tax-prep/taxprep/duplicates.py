"""Duplicate taxonomy L0-L4 + conflicts (Arc B workstream W3).

Taxonomy (R16a, operator requirements):

- L0  Same filename, different path. Not evidence of duplication by itself;
      decided by content. Solved structurally: one bronze object per byte
      hash (I1); every path kept as an alias (I3). No code here.
- L1  Byte-identical (any name/path): automatic. One bronze row, N aliases,
      counted once. Solved structurally by ``register_bronze``/``add_alias``;
      :func:`assess_new_bronze` deliberately creates NO group for L1.
- L2  Text-identical, different bytes (re-downloads with different PDF
      metadata): a probable-duplicate group, raised to the Operator.
      Never auto-merged.
- L3  Field-identical: different bytes and text, same field content.
      Salted field fingerprints per form type, at artifact level after the
      R1 split and at lot level across statements. Stored as salted hashes;
      the blind orchestrator sees group counts only.
- L4  Supersedes: same payer/form/year with a CORRECTED marker or changed
      values. Raised to the Operator as a ``supersedes`` group.

Corroboration: IRS Wage & Income transcript entries vs source documents
with the same payer/year are CORROBORATION candidates, never duplicates.
Corroboration groups are raised the same way and disposed by ruling.

Conflicts (absolute rule, R16a requirement 2): conflicting field values
are raised to the Operator to dispose and are NEVER mechanically resolved.
No source-precedence policy, no latest-wins, no highest-confidence-wins,
no averaging, no first-match-wins, no default pre-selection -- anywhere in
this module. Choosing is always explicit via :func:`choose_conflict`, and
ruling on a group is always explicit via :func:`rule_on_group`. Gold
refuses while any group or conflict is undisposed (W4's gate).

Blind contract: :func:`open_groups` and :func:`open_conflicts` return
``{class: count}`` only -- counts, never values. Member keys are hashes /
ids (safe); field values never leave the local SQLite store.

Store access: this module touches the store ONLY through ``store.txn()``
(contract section 4), which yields a DB-API connection inside a single
transaction (nested calls use savepoints). It reads/writes the contract
section 3 tables ``dup_group``, ``dup_member``, ``conflict``,
``conflict_option``, ``field_fingerprint``, ``bronze``, ``bronze_text``,
``silver_doc``, ``silver_artifact``, ``decision_log`` -- all owned by W1's
``medallion_schema.sql``. The one table this module owns is ``dup_salt``
(the fingerprint salt, see below), created with CREATE TABLE IF NOT
EXISTS so W1's schema file is never touched.

Fingerprint salt: one salt per store database, generated once with
``secrets.token_hex(32)`` and persisted in the ``dup_salt`` table
(``salt_id='v1'``). All field fingerprints are
``sha256(salt_hex + ":" + canonical_input)``. The salt never leaves the
local store; only salted hashes are persisted, and the agent sees counts.

Determinism: every id is a stable hash (contract section 6); every
comparison uses canonical JSON with sorted keys; no wall-clock except
``created_at``/``ts`` audit fields; no randomness except the one-time
salt generation.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import unicodedata
from datetime import datetime, timezone

# Salt namespace. Bump only if the fingerprint input scheme changes, and
# then treat old rows as stale (re-assess), never as comparable.
SALT_ID = "v1"

# Conflict classes (contract section 3 + R16a requirement 2).
# R21a adds "allocation": a joint/multi-owner document raised to the
# Operator for owner allocation (per-artifact or per-doc). The options
# are opaque person ids; the Operator disposes via choose_conflict or
# per-artifact owner assignment. Never mechanically split.
CONFLICT_CLASSES = frozenset({
    "duplicate", "corroboration", "reextract", "ocr", "parser", "supersedes",
    "allocation",
})

# Duplicate group classes (contract section 3).
GROUP_CLASSES = frozenset({"L1", "L2", "L3", "corroboration", "supersedes"})

# Rulings accepted per group class.
_RULINGS = {
    "L2": ("keep_one", "distinct", "merge"),
    "L3": ("keep_one", "distinct", "merge"),
    "corroboration": ("corroborates", "distinct"),
    "supersedes": ("authoritative",),
}

# Key boxes per form type for the L3 doc-level field fingerprint.
# Mirrors the key-box lists in extractors._FORM_REGISTRY (read, never
# modified); kept as a local table so fingerprinting does not depend on
# extractor internals across EXTRACTOR_VERSION bumps. 1099-B lots are
# fingerprinted per lot; the doc-level 1099-B fingerprint covers the
# broker plus the sorted lot fingerprints.
_KEY_BOXES = {
    "W-2": ("1", "2", "employer_ein"),
    "1099-B": ("broker",),
    "1099-INT": ("1",),
    "1099-DIV": ("1a",),
    "1099-NEC": ("1",),
    "1099-R": ("1",),
    "1098": ("1",),
    "1099-MISC": ("1",),
    "1099-G": ("1",),
}

# Payer identity field keys, in preference order. EIN wins over name.
_PAYER_EIN_KEYS = ("employer_ein", "payer_ein", "ein")
_PAYER_NAME_KEYS = ("employer_name", "payer_name", "broker")
# Recipient identity keys (masked digits when present). The current
# extractors do not emit these; the hooks are here for when they do.
_RECIPIENT_KEYS = ("recipient_ssn", "employee_ssn", "ssn")

# Source-doc form types that a Wage & Income transcript entry can
# corroborate.
_SOURCE_FORMS = frozenset({
    "W-2", "1099-INT", "1099-DIV", "1099-B", "1099-NEC",
    "1099-R", "1099-MISC", "1099-G",
})

# A CORRECTED marker on an information return. Word-boundary match so
# "uncorrected" does not fire; case-insensitive.
_CORRECTED_RE = re.compile(r"\bCORRECTED\b", re.IGNORECASE)

_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)
_WS_RE = re.compile(r"\s+")
_DIGITS_RE = re.compile(r"\D")


# ---------------------------------------------------------------------------
# Normalization + canonical JSON
# ---------------------------------------------------------------------------

def normalize_text(pages: list[str]) -> str:
    """Canonical normalization for L2 text comparison.

    Pages joined with newline, NFKC, casefolded, punctuation collapsed to
    spaces (never deleted, so ``end.start`` != ``endstart``), whitespace
    runs collapsed to a single space, stripped. Deterministic.
    """
    text = "\n".join("" if p is None else str(p) for p in pages)
    text = unicodedata.normalize("NFKC", text)
    text = _PUNCT_RE.sub(" ", text)
    text = text.casefold()
    return _WS_RE.sub(" ", text).strip()


def text_fingerprint(pages: list[str]) -> str:
    """sha256 hex of the normalized per-page text (L2 identity)."""
    return hashlib.sha256(
        normalize_text(pages).encode("utf-8")).hexdigest()


def _canon_scalar(value):
    """Deterministic scalar canonicalization for fingerprint inputs.

    Money arrives as Decimal-safe strings (extractors) or floats
    (transcript parser, D2); both normalize to the same ``dec:`` token so
    cross-source equality holds. Strings are stripped; None stays None.
    """
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        # Decimal(str(v)) avoids binary-float repr noise; normalize()
        # collapses 100.0 and 100.00 to the same token.
        from decimal import Decimal, InvalidOperation
        try:
            d = Decimal(str(value)).normalize()
        except InvalidOperation:  # NaN / inf: keep a stable token
            return f"float:{value!r}"
        return f"dec:{format(d, 'f')}"
    if isinstance(value, str):
        return value.strip()
    return str(value)


def _canon(obj) -> str:
    """Canonical JSON (sorted keys, no whitespace) of canonicalized values."""
    def walk(o):
        if isinstance(o, dict):
            return {str(k): walk(o[k]) for k in sorted(o, key=str)}
        if isinstance(o, (list, tuple)):
            return [walk(v) for v in o]
        return _canon_scalar(o)
    return json.dumps(walk(obj), sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True)


def _norm_name(value) -> str:
    """Normalized payer/recipient name for identity comparison."""
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value))
    text = _PUNCT_RE.sub(" ", text)
    return _WS_RE.sub(" ", text.casefold()).strip()


def _norm_ein(value) -> str:
    """Digits-only EIN; empty when absent."""
    if value is None:
        return ""
    return _DIGITS_RE.sub("", str(value))


def _mask_digits(value) -> str:
    """Masked digit identity: all but the last four digits masked.

    The blind contract forbids full account/SSN digits in agent-visible
    outputs; fingerprints use the masked form when digits are present.
    """
    digits = _DIGITS_RE.sub("", str(value)) if value is not None else ""
    if len(digits) <= 4:
        return "X" * len(digits)
    return "X" * (len(digits) - 4) + digits[-4:]


def _field_value(fields: dict, key: str):
    """Operational field value from the silver fields_json shape.

    ``fields_json`` mirrors Document.fields: {box: {value, confidence,
    raw_text}}. Tolerates bare values for forward compatibility.
    """
    entry = fields.get(key)
    if isinstance(entry, dict) and "value" in entry:
        return entry["value"]
    return entry


# ---------------------------------------------------------------------------
# Schema + salt (the one table this module owns)
# ---------------------------------------------------------------------------

def ensure_schema(store) -> None:
    """Create the module-owned ``dup_salt`` table if absent.

    All other tables come from W1's medallion_schema.sql (contract
    section 3); this module only reads/writes rows there.
    """
    with store.txn() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS dup_salt ("
            "salt_id TEXT PRIMARY KEY, salt_hex TEXT NOT NULL)")


def _get_salt(conn) -> str:
    """The store's fingerprint salt, generating and persisting it once."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS dup_salt ("
        "salt_id TEXT PRIMARY KEY, salt_hex TEXT NOT NULL)")
    row = conn.execute(
        "SELECT salt_hex FROM dup_salt WHERE salt_id = ?",
        (SALT_ID,)).fetchone()
    if row is not None:
        return row[0]
    salt = secrets.token_hex(32)
    conn.execute(
        "INSERT INTO dup_salt (salt_id, salt_hex) VALUES (?, ?)",
        (SALT_ID, salt))
    return salt


def _salted_fp(salt_hex: str, canonical_input: str) -> str:
    return hashlib.sha256(
        f"{salt_hex}:{canonical_input}".encode("utf-8")).hexdigest()


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Stable ids + group/conflict writers
# ---------------------------------------------------------------------------

def _group_id(cls: str, member_keys: list[str]) -> str:
    """Contract section 6: sha256(class:sorted member keys)[:32]."""
    joined = ":".join(sorted(member_keys))
    return hashlib.sha256(f"{cls}:{joined}".encode("utf-8")).hexdigest()[:32]


def _conflict_id(cls: str, field: str | None,
                 option_keys: list[str]) -> str:
    """Contract section 6: sha256(class:field:sorted option keys)[:32]."""
    joined = ",".join(sorted(option_keys))
    return hashlib.sha256(
        f"{cls}:{field or ''}:{joined}".encode("utf-8")).hexdigest()[:32]


def _upsert_group(conn, cls: str,
                  members: list[tuple[str, str]]) -> str | None:
    """Insert the group + members idempotently; return the group id.

    ``members`` is [(member_key, role)]. Groups always have >= 2 members;
    returns None otherwise. Re-running with the same members is a no-op
    (stable id + INSERT OR IGNORE).
    """
    keys = [k for k, _ in members]
    if len(set(keys)) < 2:
        return None
    gid = _group_id(cls, keys)
    now = _utcnow()
    conn.execute(
        "INSERT OR IGNORE INTO dup_group "
        "(group_id, class, status, created_at, disposed_at) "
        "VALUES (?, ?, 'open', ?, NULL)", (gid, cls, now))
    for key, role in members:
        conn.execute(
            "INSERT OR IGNORE INTO dup_member (group_id, member_key, role) "
            "VALUES (?, ?, ?)", (gid, key, role))
    return gid


def _group_members(conn, group_id: str) -> list[tuple[str, str | None]]:
    return [(r[0], r[1]) for r in conn.execute(
        "SELECT member_key, role FROM dup_member WHERE group_id = ? "
        "ORDER BY member_key", (group_id,)).fetchall()]


# ---------------------------------------------------------------------------
# Bronze-level: L2 text identity + L4 supersedes pairing
# ---------------------------------------------------------------------------

def _bronze_texts(conn, bronze_hash: str) -> list[str]:
    """Per-page texts for a bronze, deterministic page order.

    Only the latest derivation group is used: bronze_text rows are keyed
    (hash, page, derivation_version, config_hash), and a version bump
    adds rows. Page 0 is the whole-doc pseudo page (contract section 3);
    it is used only when no numbered pages exist, so text is never
    double-counted.
    """
    rows = conn.execute(
        "SELECT page, text FROM bronze_text WHERE hash = ? "
        "AND (derivation_version, config_hash) = ("
        "  SELECT derivation_version, config_hash FROM bronze_text "
        "  WHERE hash = ? ORDER BY rowid DESC LIMIT 1) "
        "ORDER BY page", (bronze_hash, bronze_hash)).fetchall()
    numbered = [t for p, t in rows if p >= 1]
    if numbered:
        return numbered
    return [t for p, t in rows if p == 0]


def _bronze_texts_for_doc(conn, doc_id: str) -> list[str]:
    """Per-page texts for a doc's bronze (latest derivation)."""
    row = conn.execute(
        "SELECT bronze_hash FROM silver_doc WHERE doc_id = ?",
        (doc_id,)).fetchone()
    if row is None:
        return []
    return _bronze_texts(conn, row[0])


def compute_and_store_text_fingerprint(store, bronze_hash: str) -> str | None:
    """Compute the L2 text fingerprint and store it on the bronze row.

    W2's ingest flow calls this (or inlines it) after bronze_text rows are
    written. Returns the fingerprint hex, or None when the bronze has no
    derived text yet (safe no-op: nothing stored, nothing raised).
    """
    with store.txn() as conn:
        row = conn.execute(
            "SELECT hash FROM bronze WHERE hash = ?",
            (bronze_hash,)).fetchone()
        if row is None:
            return None
        texts = _bronze_texts(conn, bronze_hash)
        if not texts or not any(t and t.strip() for t in texts):
            return None
        fp = text_fingerprint(texts)
        conn.execute(
            "UPDATE bronze SET text_fingerprint = ? WHERE hash = ?",
            (fp, bronze_hash))
        return fp


def _payer_identity(fields: dict) -> tuple[str, str]:
    """(ein_digits, normalized_name) for a doc's fields; ("","") if unknown."""
    ein = ""
    for key in _PAYER_EIN_KEYS:
        v = _field_value(fields, key)
        if v:
            ein = _norm_ein(v)
            if ein:
                break
    name = ""
    for key in _PAYER_NAME_KEYS:
        v = _field_value(fields, key)
        if v:
            name = _norm_name(v)
            if name:
                break
    return (ein, name)


def _recipient_identity(fields: dict) -> str:
    """Masked recipient identity; "" when no recipient digits are present."""
    for key in _RECIPIENT_KEYS:
        v = _field_value(fields, key)
        if v:
            masked = _mask_digits(v)
            if masked:
                return masked
    return ""


def _has_corrected_marker(texts: list[str], fields: dict) -> bool:
    """A CORRECTED marker in extracted text or in corrected-flag fields."""
    blob = "\n".join(texts)
    if _CORRECTED_RE.search(blob):
        return True
    for key, entry in fields.items():
        kl = str(key).lower()
        if "correct" in kl:
            v = entry.get("value") if isinstance(entry, dict) else entry
            if v is True or (isinstance(v, str)
                             and v.strip().lower() in ("true", "yes", "y", "1")):
                return True
    return False


def _key_values(fields: dict, form_type: str) -> dict:
    """Canonical key-box values for same-payer comparison."""
    out = {}
    for box in _KEY_BOXES.get(form_type, ()):
        if box == "broker":
            continue  # identity, not a value
        out[box] = _canon_scalar(_field_value(fields, box))
    if form_type == "1099-B":
        # Lots are the values on a 1099-B (key boxes carry no amounts).
        out["lots"] = _lot_key_values(fields)
    return out


def _lot_key_values(fields: dict) -> tuple:
    """Canonical per-lot money/term tuple for 1099-B comparison."""
    lots = fields.get("lots")
    if isinstance(lots, dict):
        lots = lots.get("value")
    if not isinstance(lots, list):
        return ()
    rows = []
    for lot in lots:
        if not isinstance(lot, dict):
            continue
        rows.append(tuple(
            _canon_scalar(lot.get(k)) for k in
            ("description", "date_acquired", "date_sold", "proceeds_1d",
             "basis_1e", "wash_1g", "term", "covered")
        ))
    return tuple(sorted(rows))


def _key_values_differ(a: dict, b: dict, form_type: str) -> bool:
    """Same (payer, form, year) but differing key values -> L4 candidate."""
    ka, kb = _key_values(a, form_type), _key_values(b, form_type)
    keys = set(ka) | set(kb)
    if not keys:
        return False
    return any(ka.get(k) != kb.get(k) for k in keys)


def _payer_columns_present(conn) -> bool:
    """True when silver_doc carries the B1 stored payer-identity columns.

    Real MedallionStore databases always have them (schema DDL for fresh
    DBs, _COLUMN_MIGRATIONS for legacy ones); minimal contract stores
    (e.g. the W3 test FakeStore) may not, and take the legacy scan path.
    """
    cols = {r[1] for r in conn.execute("PRAGMA table_info(silver_doc)")}
    return "payer_ein" in cols and "payer_name_norm" in cols


def _backfill_payer_columns(conn, form_type: str, tax_year) -> int:
    """Populate NULL payer-identity columns for one (form, year) slice.

    Runs at most once per doc ever: after the UPDATE no row of the slice
    still has NULL columns (unknown identity is stored as ''), so repeat
    calls find nothing to do. Returns the number of rows backfilled.
    """
    if tax_year is None:
        year_pred: str = "tax_year IS NULL"
        params: tuple = ()
    else:
        year_pred = "tax_year = ?"
        params = (tax_year,)
    rows = conn.execute(
        "SELECT doc_id, fields_json FROM silver_doc "
        f"WHERE form_type = ? AND {year_pred} "
        "AND (payer_ein IS NULL OR payer_name_norm IS NULL)",
        (form_type, *params)).fetchall()
    for doc_id, fields_json in rows:
        ein, name = _payer_identity(json.loads(fields_json or "{}"))
        conn.execute(
            "UPDATE silver_doc SET payer_ein = ?, payer_name_norm = ? "
            "WHERE doc_id = ?",
            (ein, name, doc_id))
    return len(rows)


def _l4_same_payer_priors(conn, form_type: str, tax_year, payer, doc_id):
    """Indexed same-payer candidate lookup (B1).

    Requires the B1 payer-identity columns. Returns [(doc_id,
    fields_json)] for prior docs of the same form, year, and payer
    identity, served by idx_silver_doc_payer (no full form-type scan).
    The year predicate is NULL-safe so the result set matches the legacy
    Python-side filter exactly.
    """
    if tax_year is None:
        year_pred = "tax_year IS NULL"
        params: tuple = ()
    else:
        year_pred = "tax_year = ?"
        params = (tax_year,)
    return conn.execute(
        "SELECT doc_id, fields_json FROM silver_doc "
        f"WHERE form_type = ? AND {year_pred} AND payer_ein = ? "
        "AND payer_name_norm = ? AND doc_id <> ? ORDER BY doc_id",
        (form_type, *params, payer[0], payer[1], doc_id)).fetchall()


def assess_new_bronze(store, bronze_hash: str) -> list[str]:
    """Assess a newly registered bronze: L2 groups + L4 supersedes pairs.

    Called by ingest after bronze registration (contract section 8, step 5).
    Safe no-op when tables are empty or the bronze has no derived text.

    L1 is structural (same bytes = same bronze row) and creates no group.
    Returns the created (or already-existing) group ids.
    """
    created: list[str] = []
    with store.txn() as conn:
        row = conn.execute(
            "SELECT hash FROM bronze WHERE hash = ?",
            (bronze_hash,)).fetchone()
        if row is None:
            return []
        # L2: text-identical, different bytes.
        # Backfill safety net: any bronze with derived text but no stored
        # fingerprint gets one now (deterministic, idempotent). In the
        # real ingest flow W2 stores the fingerprint at derivation time,
        # so after the first wave this query is empty.
        for (h,) in conn.execute(
                "SELECT DISTINCT b.hash FROM bronze b "
                "JOIN bronze_text t ON t.hash = b.hash "
                "WHERE b.text_fingerprint IS NULL").fetchall():
            _texts = _bronze_texts(conn, h)
            if _texts and any(t and t.strip() for t in _texts):
                conn.execute(
                    "UPDATE bronze SET text_fingerprint = ? WHERE hash = ?",
                    (text_fingerprint(_texts), h))
        fp = conn.execute(
            "SELECT text_fingerprint FROM bronze WHERE hash = ?",
            (bronze_hash,)).fetchone()[0]
        if fp:
            others = conn.execute(
                "SELECT hash FROM bronze WHERE text_fingerprint = ? "
                "AND hash <> ? ORDER BY hash", (fp, bronze_hash)).fetchall()
            for (other,) in others:
                gid = _upsert_group(
                    conn, "L2",
                    [(bronze_hash, "candidate"), (other, "reference")])
                if gid and gid not in created:
                    created.append(gid)
        # L4: CORRECTED marker or changed values vs a same-payer prior.
        docs = conn.execute(
            "SELECT doc_id, form_type, tax_year, fields_json "
            "FROM silver_doc WHERE bronze_hash = ? ORDER BY doc_id",
            (bronze_hash,)).fetchall()
        texts = _bronze_texts(conn, bronze_hash)
        # B1: on stores with the payer-identity columns the candidate set
        # comes from idx_silver_doc_payer (O(same-payer) per doc); on
        # minimal contract stores the legacy form-type scan applies.
        payer_indexed = _payer_columns_present(conn)
        backfilled: set = set()
        for doc_id, form_type, tax_year, fields_json in docs:
            fields = json.loads(fields_json or "{}")
            payer = _payer_identity(fields)
            if payer == ("", ""):
                continue  # cannot attribute same-payer without identity
            marker = _has_corrected_marker(texts, fields)
            if payer_indexed:
                bkey = (form_type, tax_year)
                if bkey not in backfilled:
                    _backfill_payer_columns(conn, form_type, tax_year)
                    backfilled.add(bkey)
                priors = _l4_same_payer_priors(
                    conn, form_type, tax_year, payer, doc_id)
            else:
                priors = conn.execute(
                    "SELECT doc_id, tax_year, fields_json FROM silver_doc "
                    "WHERE form_type = ? AND doc_id <> ? ORDER BY doc_id",
                    (form_type, doc_id)).fetchall()
            for prior in priors:
                if payer_indexed:
                    p_id, p_fields_json = prior
                else:
                    p_id, p_year, p_fields_json = prior
                    if p_year != tax_year:
                        continue
                p_fields = json.loads(p_fields_json or "{}")
                if not payer_indexed and _payer_identity(p_fields) != payer:
                    continue
                # Bidirectional: the CORRECTED marker may sit on the prior
                # doc (ingested first) or on the new one; differing values
                # in either direction also qualify.
                p_texts = _bronze_texts_for_doc(conn, p_id)
                if (marker
                        or _has_corrected_marker(p_texts, p_fields)
                        or _key_values_differ(fields, p_fields, form_type)):
                    gid = _upsert_group(
                        conn, "supersedes",
                        [(doc_id, "candidate"), (p_id, "reference")])
                    if gid and gid not in created:
                        created.append(gid)
    return created


# ---------------------------------------------------------------------------
# Silver-level: L3 field fingerprints, lot fingerprints, corroboration,
# and field-disagreement conflicts
# ---------------------------------------------------------------------------

def _representative_artifact(conn, doc_id: str) -> str | None:
    """Artifact id backing this doc's field_fingerprint rows.

    Documented choice: the payer artifact when one exists (the identity
    the fingerprint attests), else the lexicographically-first field
    artifact. The fingerprint INPUT is always doc-level; the row only
    needs a stable, existing artifact to satisfy the FK.
    """
    rows = conn.execute(
        "SELECT artifact_id, artifact_type FROM silver_artifact "
        "WHERE doc_id = ? ORDER BY artifact_id", (doc_id,)).fetchall()
    if not rows:
        return None
    for aid, atype in rows:
        if atype == "payer":
            return aid
    for aid, atype in rows:
        if atype == "field":
            return aid
    return rows[0][0]


def _doc_fingerprint_input(form_type: str, tax_year, fields: dict,
                           lot_fps: list[str]) -> dict:
    payer_ein, payer_name = _payer_identity(fields)
    boxes = {}
    for box in _KEY_BOXES.get(form_type, ()):
        if box == "lots":
            continue
        if box == "broker":
            boxes[box] = _norm_name(_field_value(fields, box))
        else:
            boxes[box] = _canon_scalar(_field_value(fields, box))
    return {
        "v": 1,
        "kind": "doc",
        "form": form_type,
        "year": tax_year,
        "payer_ein": payer_ein,
        "payer_name": payer_name,
        "recipient": _recipient_identity(fields),
        "boxes": boxes,
        "lot_fps": sorted(lot_fps),
    }


def _lot_fingerprint_input(lot: dict) -> dict:
    """R16a lot identity: description/security, dates, proceeds, basis.

    Quantity is not extracted by the current extractors, so it cannot
    participate; term/covered are classification, not identity, and are
    excluded so a scan-vs-digital pair still matches.
    """
    return {
        "v": 1,
        "kind": "lot",
        "description": _norm_name(lot.get("description")),
        "date_acquired": _canon_scalar(lot.get("date_acquired")),
        "date_sold": _canon_scalar(lot.get("date_sold")),
        "proceeds_1d": _canon_scalar(lot.get("proceeds_1d")),
        "basis_1e": _canon_scalar(lot.get("basis_1e")),
    }


def _doc_lots(fields: dict) -> list[dict]:
    lots = _field_value(fields, "lots")
    if isinstance(lots, list):
        return [l for l in lots if isinstance(l, dict)]
    return []


def _lot_member_keys(conn, doc_id: str) -> list[str]:
    """Deterministic member key per lot, in lot order.

    The lot's own artifact id when W2 emitted lot artifacts, else a
    deterministic derived key. The same doc always yields the same keys.
    """
    row = _load_doc(conn, doc_id)
    if row is None:
        return []
    lots = _doc_lots(json.loads(row[4] or "{}"))
    aids = [r[0] for r in conn.execute(
        "SELECT artifact_id FROM silver_artifact "
        "WHERE doc_id = ? AND artifact_type = 'lot' "
        "ORDER BY artifact_id", (doc_id,)).fetchall()]
    return [aids[i] if i < len(aids) else f"{doc_id}:lot:{i}"
            for i in range(len(lots))]


def _lot_fp(conn, salt: str, lot: dict) -> str:
    return _salted_fp(salt, _canon(_lot_fingerprint_input(lot)))


def _load_doc(conn, doc_id: str):
    return conn.execute(
        "SELECT doc_id, bronze_hash, form_type, tax_year, fields_json "
        "FROM silver_doc WHERE doc_id = ?", (doc_id,)).fetchone()


def _fingerprint_doc(conn, salt: str, doc_id: str) -> dict | None:
    """Compute (and idempotently store) a doc's L3 fingerprints.

    Returns {dfp, lot_fps, lot_keys, anchor, fields} or None when the doc
    is unknown. Storage is INSERT OR IGNORE under the representative
    artifact (the field_fingerprint FK requires a real artifact); when
    the doc has no artifacts, fingerprints are computed but not stored.
    """
    row = _load_doc(conn, doc_id)
    if row is None:
        return None
    _, _, form_type, tax_year, fields_json = row
    fields = json.loads(fields_json or "{}")
    anchor = _representative_artifact(conn, doc_id)
    lots = _doc_lots(fields)
    lot_keys = _lot_member_keys(conn, doc_id)
    lot_fps = [_lot_fp(conn, salt, lot) for lot in lots]
    dfp = _salted_fp(
        salt, _canon(_doc_fingerprint_input(
            form_type, tax_year, fields, lot_fps)))
    if anchor is not None:
        for lfp in lot_fps:
            conn.execute(
                "INSERT OR IGNORE INTO field_fingerprint "
                "(artifact_id, fp_hash, salt_id) VALUES (?, ?, ?)",
                (anchor, lfp, SALT_ID))
        conn.execute(
            "INSERT OR IGNORE INTO field_fingerprint "
            "(artifact_id, fp_hash, salt_id) VALUES (?, ?, ?)",
            (anchor, dfp, SALT_ID))
    return {"dfp": dfp, "lot_fps": lot_fps, "lot_keys": lot_keys,
            "anchor": anchor, "fields": fields, "form_type": form_type,
            "tax_year": tax_year}


def _l3_assess(conn, salt: str, doc_id: str) -> list[str]:
    """L3 doc-level + lot-level grouping for one silver doc.

    Fingerprints are recomputed per candidate doc (deterministic,
    idempotent, order-independent): a doc is matched whether or not it
    was assessed before. Doc-level matches pair doc ids; lot-level
    matches pair lot member keys. The "kind" namespace in the
    fingerprint input keeps doc and lot hashes disjoint.
    """
    created: list[str] = []
    mine = _fingerprint_doc(conn, salt, doc_id)
    if mine is None:
        return []
    form_type, tax_year = mine["form_type"], mine["tax_year"]
    others = conn.execute(
        "SELECT doc_id, tax_year FROM silver_doc "
        "WHERE form_type = ? AND doc_id <> ? ORDER BY doc_id",
        (form_type, doc_id)).fetchall()
    for o_id, o_year in others:
        if o_year != tax_year:
            continue
        o = _fingerprint_doc(conn, salt, o_id)
        if o is None:
            continue
        if o["dfp"] == mine["dfp"]:
            gid = _upsert_group(
                conn, "L3", [(doc_id, "candidate"), (o_id, "reference")])
            if gid and gid not in created:
                created.append(gid)
            key_skip = set(_KEY_BOXES.get(form_type, ())) | {"lots"}
            evidence = {doc_id: mine["anchor"] or doc_id,
                        o_id: o["anchor"] or o_id}
            _raise_group_field_conflicts(
                conn, "duplicate", gid,
                {doc_id: mine["fields"], o_id: o["fields"]},
                key_skip, evidence)
        for i, lfp in enumerate(mine["lot_fps"]):
            for j, o_lfp in enumerate(o["lot_fps"]):
                if o_lfp == lfp:
                    gid = _upsert_group(
                        conn, "L3",
                        [(mine["lot_keys"][i], "candidate"),
                         (o["lot_keys"][j], "reference")])
                    if gid and gid not in created:
                        created.append(gid)
    return created


def _compare_value(key: str, value):
    """Comparison value for disagreement detection.

    Payer identity keys compare normalized (the L3 fingerprint already
    attests normalized payer identity, so raw-string case/punctuation
    differences must not raise spurious conflicts).
    """
    if key in _PAYER_NAME_KEYS:
        return _norm_name(value)
    if key in _PAYER_EIN_KEYS:
        return _norm_ein(value)
    return _canon_scalar(value)


def _fields_disagreements(a: dict, b: dict, skip: set[str]) -> list[str]:
    """Field keys present in both docs with differing comparison values."""
    out = []
    for key in sorted(set(a) & set(b)):
        if key in skip:
            continue
        va = _compare_value(key, _field_value(a, key))
        vb = _compare_value(key, _field_value(b, key))
        if va != vb:
            out.append(key)
    return out


def raise_conflict(store, *, cls: str, field: str | None,
                   options: list[dict]) -> str:
    """Raise a conflict to the Operator. Never resolves anything.

    ``options``: [{option_key, value_json, evidence_ref?}]. ``value_json``
    may be any JSON-serializable value; it is canonicalized before
    storage. Re-raising the same (class, field, option keys) is
    idempotent: options are upserted. Returns the stable conflict id.
    """
    if cls not in CONFLICT_CLASSES:
        raise ValueError(
            f"conflict class must be one of {sorted(CONFLICT_CLASSES)}, "
            f"got {cls!r}")
    if not options:
        raise ValueError("conflict requires at least one option")
    normed = []
    for opt in options:
        if not isinstance(opt, dict) or not opt.get("option_key"):
            raise ValueError(
                "each option needs {option_key, value_json, evidence_ref?}")
        normed.append({
            "option_key": str(opt["option_key"]),
            "value_json": _canon(opt.get("value_json")),
            "evidence_ref": opt.get("evidence_ref"),
        })
    keys = [o["option_key"] for o in normed]
    if len(set(keys)) != len(keys):
        raise ValueError(f"duplicate option_key in conflict options: {keys}")
    cid = _conflict_id(cls, field, keys)
    with store.txn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO conflict "
            "(conflict_id, class, field, status, created_at, disposed_at) "
            "VALUES (?, ?, ?, 'open', ?, NULL)",
            (cid, cls, field, _utcnow()))
        for opt in normed:
            conn.execute(
                "INSERT INTO conflict_option "
                "(conflict_id, option_key, value_json, evidence_ref) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT (conflict_id, option_key) DO UPDATE SET "
                "value_json = excluded.value_json, "
                "evidence_ref = excluded.evidence_ref",
                (cid, opt["option_key"], opt["value_json"],
                 opt["evidence_ref"]))
    return cid


def parser_ambiguity(store, doc_id: str, field: str,
                     candidates: list[dict]) -> str:
    """Raise a parser-ambiguity conflict (D4): a line matching several
    labels, or a label matched by several lines.

    ``candidates``: [{option_key, value, evidence_ref?}]. Intended call
    sites are transcript.py / extractors.py (extraction is out of scope
    for this workstream, so no call site is wired here -- the API and its
    tests are the deliverable).
    """
    return raise_conflict(
        store, cls="parser", field=field,
        options=[{
            "option_key": c["option_key"],
            "value_json": c.get("value"),
            "evidence_ref": c.get("evidence_ref"),
        } for c in candidates])


def flag_reextract(store, *, doc_id: str, field: str,
                   validated_value, reextracted_value,
                   evidence_ref: str | None = None) -> str:
    """Raise a re-extraction-vs-validated conflict (R4/I6).

    The validated value stands only as the record; the conflict blocks
    gold until the Operator disposes it via :func:`choose_conflict`.
    W2 sets ``silver_doc.re_review``; this function only raises the
    conflict with options=[validated, re-extracted].
    """
    return raise_conflict(
        store, cls="reextract", field=field,
        options=[
            {"option_key": "validated", "value_json": validated_value,
             "evidence_ref": evidence_ref or doc_id},
            {"option_key": "re-extracted", "value_json": reextracted_value,
             "evidence_ref": evidence_ref or doc_id},
        ])


def _raise_group_field_conflicts(conn, cls: str, group_id: str,
                                 doc_fields: dict[str, dict],
                                 skip_keys: set[str],
                                 evidence: dict[str, str]) -> list[str]:
    """Raise one conflict per field where group members disagree.

    A field present (non-None) in at least two members with differing
    comparison values raises a conflict. A field present in only one
    member is an extraction-coverage difference, not a value
    disagreement, and is not raised. This is the absolute rule made
    mechanical in exactly one direction: disagreement is always RAISED,
    never resolved.
    """
    raised: list[str] = []
    doc_ids = sorted(doc_fields)
    fields = sorted(set().union(*[set(f) for f in doc_fields.values()]))
    for key in fields:
        if key in skip_keys:
            continue
        vals = {d: _compare_value(key, _field_value(doc_fields[d], key))
                for d in doc_ids}
        present = {d: v for d, v in vals.items() if v is not None}
        if len(present) < 2 or len(set(present.values())) < 2:
            continue
        cid = _conflict_id(
            cls, key, [f"{d}:{key}" for d in present])
        conn.execute(
            "INSERT OR IGNORE INTO conflict "
            "(conflict_id, class, field, status, created_at, disposed_at) "
            "VALUES (?, ?, ?, 'open', ?, NULL)",
            (cid, cls, key, _utcnow()))
        for d, v in sorted(present.items()):
            conn.execute(
                "INSERT INTO conflict_option "
                "(conflict_id, option_key, value_json, evidence_ref) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT (conflict_id, option_key) DO UPDATE SET "
                "value_json = excluded.value_json, "
                "evidence_ref = excluded.evidence_ref",
                (cid, f"{d}:{key}", _canon(v), evidence.get(d)))
        raised.append(cid)
    return raised


def _wi_entries(fields: dict) -> list[dict]:
    """Wage & Income transcript payer entries from adapted fields.

    Ingest adapts W&I payers to positional keys (R8): ``payer{i}.name``,
    ``payer{i}.<box>``. Returns [{index, name, boxes}].
    """
    prefixes: dict[str, dict] = {}
    for key in fields:
        m = re.match(r"^(payer\d+)\.(.+)$", str(key))
        if not m:
            continue
        prefix, sub = m.group(1), m.group(2)
        entry = prefixes.setdefault(prefix, {"name": "", "boxes": {}})
        if sub == "name":
            entry["name"] = _field_value(fields, key) or ""
        else:
            entry["boxes"][sub] = _field_value(fields, key)
    out = []
    for prefix in sorted(prefixes, key=lambda p: int(p[5:])):
        out.append({"prefix": prefix, **prefixes[prefix]})
    return out


def _corroboration_pairs(conn, wi_doc_id: str, wi_year,
                         wi_fields: dict) -> list[tuple[str, dict]]:
    """(source_doc_id, wi_entry) pairs sharing payer identity and year."""
    pairs = []
    src_docs = conn.execute(
        "SELECT doc_id, form_type, tax_year, fields_json FROM silver_doc "
        "WHERE form_type IN ({}) AND doc_id <> ? ORDER BY doc_id".format(
            ",".join("?" * len(_SOURCE_FORMS))),
        (*sorted(_SOURCE_FORMS), wi_doc_id)).fetchall()
    for entry in _wi_entries(wi_fields):
        wi_name = _norm_name(entry["name"])
        if not wi_name:
            continue
        for s_id, s_form, s_year, s_fields_json in src_docs:
            if s_year != wi_year:
                continue
            s_fields = json.loads(s_fields_json or "{}")
            s_ein, s_name = _payer_identity(s_fields)
            if s_name and (s_name == wi_name or wi_name in s_name
                           or s_name in wi_name):
                pairs.append((s_id, entry))
    return pairs


def _assess_corroboration(conn, doc_id: str, form_type: str, tax_year,
                          fields: dict) -> list[str]:
    """Corroboration groups for a W&I doc (or a source doc vs W&I docs).

    Never classed as duplicate. Field disagreements between the W&I
    entry and the source doc raise ``corroboration`` conflicts.
    """
    created: list[str] = []
    if form_type == "WAGE_INCOME_TRANSCRIPT":
        wi_id, wi_year, wi_fields = doc_id, tax_year, fields
        pairs = _corroboration_pairs(conn, wi_id, wi_year, wi_fields)
        wi_entry_by_src = {}
        for s_id, entry in pairs:
            wi_entry_by_src.setdefault(s_id, entry)
        for s_id, entry in sorted(wi_entry_by_src.items()):
            gid = _upsert_group(
                conn, "corroboration",
                [(wi_id, "candidate"), (s_id, "reference")])
            if gid and gid not in created:
                created.append(gid)
            s_row = _load_doc(conn, s_id)
            s_fields = json.loads(s_row[4] or "{}")
            # Compare W&I entry boxes against the source doc's boxes.
            disagreements = []
            for box, wi_val in entry["boxes"].items():
                sv = _field_value(s_fields, box)
                if (wi_val is not None and sv is not None
                        and _canon_scalar(wi_val) != _canon_scalar(sv)):
                    disagreements.append(box)
            for box in disagreements:
                raise_conflict_conn(
                    conn, cls="corroboration", field=f"box_{box}",
                    options=[
                        {"option_key": f"{wi_id}:{box}",
                         "value_json": entry["boxes"][box],
                         "evidence_ref": wi_id},
                        {"option_key": f"{s_id}:{box}",
                         "value_json": _field_value(s_fields, box),
                         "evidence_ref": s_id},
                    ])
    elif form_type in _SOURCE_FORMS:
        wi_docs = conn.execute(
            "SELECT doc_id, tax_year, fields_json FROM silver_doc "
            "WHERE form_type = 'WAGE_INCOME_TRANSCRIPT' AND doc_id <> ? "
            "ORDER BY doc_id", (doc_id,)).fetchall()
        for wi_id, wi_year, wi_fields_json in wi_docs:
            if wi_year != tax_year:
                continue
            for gid in _assess_corroboration(
                    conn, wi_id, "WAGE_INCOME_TRANSCRIPT", wi_year,
                    json.loads(wi_fields_json or "{}")):
                # Only report groups this doc belongs to; the W&I-side
                # run is idempotent, so pairs are created exactly once.
                members = [k for k, _ in _group_members(conn, gid)]
                if doc_id in members and gid not in created:
                    created.append(gid)
    return created


def raise_conflict_conn(conn, *, cls: str, field: str | None,
                        options: list[dict]) -> str:
    """Connection-bound :func:`raise_conflict` for use inside a txn."""
    if cls not in CONFLICT_CLASSES:
        raise ValueError(f"bad conflict class: {cls!r}")
    if not options:
        raise ValueError("conflict requires at least one option")
    normed = []
    for opt in options:
        if not isinstance(opt, dict) or not opt.get("option_key"):
            raise ValueError("each option needs option_key")
        normed.append({
            "option_key": str(opt["option_key"]),
            "value_json": _canon(opt.get("value_json")),
            "evidence_ref": opt.get("evidence_ref"),
        })
    keys = [o["option_key"] for o in normed]
    if len(set(keys)) != len(keys):
        raise ValueError(f"duplicate option_key: {keys}")
    cid = _conflict_id(cls, field, keys)
    conn.execute(
        "INSERT OR IGNORE INTO conflict "
        "(conflict_id, class, field, status, created_at, disposed_at) "
        "VALUES (?, ?, ?, 'open', ?, NULL)",
        (cid, cls, field, _utcnow()))
    for opt in normed:
        conn.execute(
            "INSERT INTO conflict_option "
            "(conflict_id, option_key, value_json, evidence_ref) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT (conflict_id, option_key) DO UPDATE SET "
            "value_json = excluded.value_json, "
            "evidence_ref = excluded.evidence_ref",
            (cid, opt["option_key"], opt["value_json"],
             opt["evidence_ref"]))
    return cid


def assess_silver_doc(store, doc_id: str) -> list[str]:
    """Assess a silver doc after the silver write (contract section 8.6).

    - L3 doc-level field fingerprints (salted) -> dup_group class=L3.
    - L3 lot-level fingerprints per lot -> dup_group class=L3 at lot level.
    - Corroboration: W&I entries vs same-payer/year source docs ->
      dup_group class=corroboration (never duplicate).
    - Field disagreements inside L2/L3/corroboration groups -> conflicts
      (absolute rule: raised, never resolved).

    Safe no-op for unknown docs. Returns created group ids.
    """
    created: list[str] = []
    with store.txn() as conn:
        row = _load_doc(conn, doc_id)
        if row is None:
            return []
        _, bronze_hash, form_type, tax_year, fields_json = row
        fields = json.loads(fields_json or "{}")
        salt = _get_salt(conn)

        if form_type != "WAGE_INCOME_TRANSCRIPT":
            # -- L3 doc-level + lot-level fingerprints ------------------
            for gid in _l3_assess(conn, salt, doc_id):
                if gid not in created:
                    created.append(gid)
            # -- L2 field disagreements (bronze-level groups) -----------
            l2 = conn.execute(
                "SELECT g.group_id FROM dup_group g JOIN dup_member m "
                "ON g.group_id = m.group_id "
                "WHERE g.class = 'L2' AND g.status = 'open' "
                "AND m.member_key = ?", (bronze_hash,)).fetchall()
            for (lgid,) in l2:
                others = [k for k, _ in _group_members(conn, lgid)
                          if k != bronze_hash]
                for o_hash in others:
                    o_docs = conn.execute(
                        "SELECT doc_id, fields_json FROM silver_doc "
                        "WHERE bronze_hash = ? ORDER BY doc_id",
                        (o_hash,)).fetchall()
                    for o_id, o_fj in o_docs:
                        o_fields = json.loads(o_fj or "{}")
                        evidence = {doc_id: bronze_hash, o_id: o_hash}
                        _raise_group_field_conflicts(
                            conn, "duplicate", lgid,
                            {doc_id: fields, o_id: o_fields},
                            set(), evidence)
        # -- corroboration (both directions) ----------------------------
        for gid in _assess_corroboration(conn, doc_id, form_type,
                                         tax_year, fields):
            if gid not in created:
                created.append(gid)
    return created


# ---------------------------------------------------------------------------
# Disposition: rulings and conflict choices (always explicit)
# ---------------------------------------------------------------------------

def _log_decision(conn, *, actor: str, kind: str, group_id: str | None,
                  conflict_id: str | None, doc_id: str | None,
                  payload: dict) -> int:
    payload = dict(payload)
    payload["ts"] = _utcnow()
    cur = conn.execute(
        "INSERT INTO decision_log "
        "(ts, actor, kind, artifact_id, doc_id, group_id, payload_json) "
        "VALUES (?, ?, ?, NULL, ?, ?, ?)",
        (_utcnow(), actor, kind, doc_id, group_id,
         _canon(payload)))
    return cur.lastrowid


def rule_on_group(store, group_id: str, *, ruling: str,
                  primary: str | None = None, reason: str | None = None,
                  actor: str = "operator") -> int:
    """Dispose a dup_group by explicit operator ruling.

    Rulings per class: L2/L3 -> keep_one|distinct|merge;
    corroboration -> corroborates|distinct; supersedes -> authoritative.
    ``keep_one``, ``merge`` and ``authoritative`` require ``primary`` to
    name a member key. Writes decision_log ``duplicate_ruling`` /
    ``supersedes_ruling`` (contract section 9) and sets the group
    disposed. Returns the decision_log seq.

    There is no default ruling and no auto-disposition anywhere: an
    unknown group raises KeyError, a bad ruling or missing primary raises
    ValueError, and re-ruling a disposed group raises ValueError.
    """
    if actor not in ("operator", "system"):
        raise ValueError(f"actor must be operator|system, got {actor!r}")
    with store.txn() as conn:
        row = conn.execute(
            "SELECT class, status FROM dup_group WHERE group_id = ?",
            (group_id,)).fetchone()
        if row is None:
            raise KeyError(f"unknown dup_group: {group_id}")
        cls, status = row
        if status != "open":
            raise ValueError(f"dup_group {group_id} already {status}")
        allowed = _RULINGS.get(cls)
        if allowed is None or ruling not in allowed:
            raise ValueError(
                f"ruling for class {cls} must be one of {allowed}, "
                f"got {ruling!r}")
        members = [k for k, _ in _group_members(conn, group_id)]
        needs_primary = ruling in ("keep_one", "merge", "authoritative")
        if needs_primary:
            if primary is None:
                raise ValueError(
                    f"ruling {ruling!r} requires primary=<member key>")
            if primary not in members:
                raise ValueError(
                    f"primary {primary!r} is not a member of {group_id}")
        if cls == "supersedes":
            kind = "supersedes_ruling"
            payload = {"group_id": group_id, "authoritative": primary}
        else:
            kind = "duplicate_ruling"
            payload = {"group_id": group_id, "ruling": ruling,
                       "primary": primary}
        if reason:
            payload["reason"] = reason
        seq = _log_decision(conn, actor=actor, kind=kind,
                            group_id=group_id, conflict_id=None,
                            doc_id=None, payload=payload)
        conn.execute(
            "UPDATE dup_group SET status = 'disposed', disposed_at = ? "
            "WHERE group_id = ?", (_utcnow(), group_id))
        return seq


def choose_conflict(store, conflict_id: str, *, choice: str,
                    reason: str | None = None,
                    actor: str = "operator") -> int:
    """Dispose a conflict by explicit operator choice.

    ``choice`` is REQUIRED and must name one of the recorded option keys
    -- there is no default and no auto-pick. Writes decision_log
    ``conflict_choice`` {conflict_id, options_shown, choice, reason, ts}
    (contract section 9) and sets the conflict disposed. Returns the
    decision_log seq.

    Unknown conflict -> KeyError; choice not among the recorded options
    -> ValueError; re-choosing a disposed conflict -> ValueError.
    """
    if actor not in ("operator", "system"):
        raise ValueError(f"actor must be operator|system, got {actor!r}")
    with store.txn() as conn:
        row = conn.execute(
            "SELECT status FROM conflict WHERE conflict_id = ?",
            (conflict_id,)).fetchone()
        if row is None:
            raise KeyError(f"unknown conflict: {conflict_id}")
        if row[0] != "open":
            raise ValueError(f"conflict {conflict_id} already {row[0]}")
        shown = [r[0] for r in conn.execute(
            "SELECT option_key FROM conflict_option "
            "WHERE conflict_id = ? ORDER BY option_key",
            (conflict_id,)).fetchall()]
        if choice not in shown:
            raise ValueError(
                f"choice {choice!r} is not one of the recorded options "
                f"{shown} -- no default selection exists")
        payload = {"conflict_id": conflict_id,
                   "options_shown": shown, "choice": choice}
        if reason:
            payload["reason"] = reason
        seq = _log_decision(conn, actor=actor, kind="conflict_choice",
                            group_id=None, conflict_id=conflict_id,
                            doc_id=None, payload=payload)
        conn.execute(
            "UPDATE conflict SET status = 'disposed', disposed_at = ? "
            "WHERE conflict_id = ?", (_utcnow(), conflict_id))
        return seq


# ---------------------------------------------------------------------------
# Blind-contract query helpers: counts only, never values
# ---------------------------------------------------------------------------

def open_groups(store) -> dict[str, int]:
    """Open dup_group counts by class. Counts only -- no member keys."""
    with store.txn() as conn:
        rows = conn.execute(
            "SELECT class, COUNT(*) FROM dup_group "
            "WHERE status = 'open' GROUP BY class").fetchall()
    return {str(cls): int(n) for cls, n in sorted(
        ((r[0], r[1]) for r in rows), key=lambda kv: kv[0])}


def open_conflicts(store) -> dict[str, int]:
    """Open conflict counts by class. Counts only -- no values."""
    with store.txn() as conn:
        rows = conn.execute(
            "SELECT class, COUNT(*) FROM conflict "
            "WHERE status = 'open' GROUP BY class").fetchall()
    return {str(cls): int(n) for cls, n in sorted(
        ((r[0], r[1]) for r in rows), key=lambda kv: kv[0])}
