"""Arc B workstream W3: duplicate taxonomy L0-L4 + conflicts.

Tests taxprep/duplicates.py against a minimal in-memory store implementing
the contract section 4 surface this module uses (``txn()`` yielding a
DB-API connection over the contract section 3 DDL). Synthetic fixtures
only; no PII.
"""

from __future__ import annotations

import contextlib
import hashlib
import inspect
import json
import sqlite3

import pytest

from taxprep import duplicates as D

# Contract section 3 DDL, verbatim, for the tables this workstream uses.
DDL = """
CREATE TABLE bronze (
    hash TEXT PRIMARY KEY,
    size INTEGER NOT NULL,
    source_root TEXT,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    selection_state TEXT NOT NULL DEFAULT 'selected',
    encryption TEXT,
    text_fingerprint TEXT,
    blocked_reason TEXT
);
CREATE TABLE bronze_alias (
    hash TEXT NOT NULL REFERENCES bronze(hash),
    path TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    PRIMARY KEY (hash, path)
);
CREATE TABLE bronze_text (
    hash TEXT NOT NULL REFERENCES bronze(hash),
    page INTEGER NOT NULL,
    text_source TEXT NOT NULL,
    engine TEXT,
    engine_version TEXT,
    ocr_mode TEXT,
    derivation_version TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    text TEXT NOT NULL,
    PRIMARY KEY (hash, page, derivation_version, config_hash)
);
CREATE TABLE silver_doc (
    doc_id TEXT PRIMARY KEY,
    bronze_hash TEXT NOT NULL REFERENCES bronze(hash),
    form_type TEXT NOT NULL,
    tax_year INTEGER,
    status TEXT NOT NULL,
    status_reason TEXT,
    page_range TEXT,
    parent_doc_id TEXT,
    relevance TEXT NOT NULL DEFAULT 'unassessed',
    validated_at TEXT,
    re_review INTEGER NOT NULL DEFAULT 0,
    derivation_version TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    derivation_digest TEXT NOT NULL,
    fields_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE silver_artifact (
    artifact_id TEXT PRIMARY KEY,
    doc_id TEXT NOT NULL REFERENCES silver_doc(doc_id),
    bronze_hash TEXT NOT NULL,
    page INTEGER NOT NULL,
    artifact_type TEXT NOT NULL,
    anchor TEXT NOT NULL,
    value_json TEXT NOT NULL,
    offsets_json TEXT,
    derivation_version TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE decision_log (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    actor TEXT NOT NULL,
    kind TEXT NOT NULL,
    artifact_id TEXT,
    doc_id TEXT,
    group_id TEXT,
    payload_json TEXT NOT NULL
);
CREATE TABLE dup_group (
    group_id TEXT PRIMARY KEY,
    class TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    created_at TEXT NOT NULL,
    disposed_at TEXT
);
CREATE TABLE dup_member (
    group_id TEXT NOT NULL REFERENCES dup_group(group_id),
    member_key TEXT NOT NULL,
    role TEXT,
    PRIMARY KEY (group_id, member_key)
);
CREATE TABLE conflict (
    conflict_id TEXT PRIMARY KEY,
    class TEXT NOT NULL,
    field TEXT,
    status TEXT NOT NULL DEFAULT 'open',
    created_at TEXT NOT NULL,
    disposed_at TEXT
);
CREATE TABLE conflict_option (
    conflict_id TEXT NOT NULL REFERENCES conflict(conflict_id),
    option_key TEXT NOT NULL,
    value_json TEXT NOT NULL,
    evidence_ref TEXT,
    PRIMARY KEY (conflict_id, option_key)
);
CREATE TABLE field_fingerprint (
    artifact_id TEXT NOT NULL REFERENCES silver_artifact(artifact_id),
    fp_hash TEXT NOT NULL,
    salt_id TEXT NOT NULL,
    PRIMARY KEY (artifact_id, fp_hash)
);
"""

NOW = "2026-10-03T22:00:00+00:00"


class FakeStore:
    """Minimal contract-section-4 surface: txn() only (nested = savepoint)."""

    def __init__(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.executescript(DDL)
        self._depth = 0

    @contextlib.contextmanager
    def txn(self):
        self._depth += 1
        try:
            if self._depth == 1:
                yield self.conn
                self.conn.commit()
            else:
                sp = f"w3_sp_{self._depth}"
                self.conn.execute(f"SAVEPOINT {sp}")
                try:
                    yield self.conn
                except Exception:
                    self.conn.execute(f"ROLLBACK TO {sp}")
                    raise
                else:
                    self.conn.execute(f"RELEASE {sp}")
        except Exception:
            if self._depth == 1:
                self.conn.rollback()
            raise
        finally:
            self._depth -= 1

    # -- contract section 4 facade bits used by the tests -----------------
    def register_bronze(self, sha, size, source_root=None, encryption=None):
        with self.txn() as c:
            cur = c.execute(
                "INSERT OR IGNORE INTO bronze "
                "(hash, size, source_root, first_seen, last_seen, encryption)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (sha, size, source_root, NOW, NOW, encryption))
            return cur.rowcount == 1

    def add_alias(self, sha, path):
        with self.txn() as c:
            c.execute(
                "INSERT INTO bronze_alias (hash, path, last_seen)"
                " VALUES (?, ?, ?)"
                " ON CONFLICT (hash, path) DO UPDATE SET"
                " last_seen = excluded.last_seen",
                (sha, path, NOW))

    def table_counts(self):
        with self.txn() as c:
            out = {}
            for (t,) in c.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                    " AND name NOT LIKE 'sqlite_%'").fetchall():
                out[t] = c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            return out


def _field(value, confidence="high", raw="raw"):
    return {"value": value, "confidence": confidence, "raw_text": raw}


def add_bronze(store, sha, texts, size=100):
    store.register_bronze(sha, size)
    with store.txn() as c:
        for i, t in enumerate(texts, start=1):
            c.execute(
                "INSERT INTO bronze_text (hash, page, text_source,"
                " derivation_version, config_hash, text)"
                " VALUES (?, ?, 'native', '2', 'cfg', ?)",
                (sha, i, t))


def add_doc(store, doc_id, bronze_hash, form_type, year, fields,
            status="transcribed"):
    with store.txn() as c:
        c.execute(
            "INSERT INTO silver_doc (doc_id, bronze_hash, form_type,"
            " tax_year, status, derivation_version, config_hash,"
            " derivation_digest, fields_json, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, '2', 'cfg', 'dig', ?, ?, ?)",
            (doc_id, bronze_hash, form_type, year, status,
             json.dumps(fields), NOW, NOW))


def add_artifact(store, doc_id, bronze_hash, page, atype, anchor, value):
    aid = hashlib.sha256(
        f"{bronze_hash}:{page}:{atype}:{anchor}".encode()).hexdigest()[:32]
    with store.txn() as c:
        c.execute(
            "INSERT OR IGNORE INTO silver_artifact (artifact_id, doc_id,"
            " bronze_hash, page, artifact_type, anchor, value_json,"
            " derivation_version, config_hash, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, '2', 'cfg', ?, ?)",
            (aid, doc_id, bronze_hash, page, atype, anchor,
             json.dumps(value), NOW, NOW))
    return aid


W2_A = {
    "1": _field("52345.67"),
    "2": _field("4100.00"),
    "employer_ein": _field("12-3456789"),
    "employer_name": _field("Acme Corp"),
}
W2_B_SAME = {
    "1": _field("52345.67"),
    "2": _field("4100.00"),
    "employer_ein": _field("12-3456789"),
    "employer_name": _field("ACME CORP"),  # case differs: same identity
}
W2_C_DIFF = {
    "1": _field("99999.99"),  # different key value
    "2": _field("4100.00"),
    "employer_ein": _field("12-3456789"),
    "employer_name": _field("Acme Corp"),
}

TEXT_A = ["Form W-2  Wage and Tax Statement\nBox 1  52345.67\nEIN 12-3456789"]
# Same normalized text as TEXT_A, different bytes (PDF metadata differs).
TEXT_A2 = ["  FORM w-2\tWage and Tax Statement\nBox 1: 52345.67\nEIN 12-3456789  "]
TEXT_OTHER = ["Form 1099-INT\nBox 1  12.34"]
# Amended W-2 text: different bytes AND different text (new box 1 value).
TEXT_AMENDED = ["Form W-2  Wage and Tax Statement\nBox 1  99999.99\nEIN 12-3456789"]
# Same values, different layout text (no L2 relation to TEXT_A).
TEXT_RESEND = ["W-2 Wage and Tax Statement copy\nEIN: 12-3456789\nBox 1 = 52345.67"]


def _w2_doc(store, doc_id, sha, fields, texts, year=2024, with_artifacts=True):
    add_bronze(store, sha, texts)
    add_doc(store, doc_id, sha, "W-2", year, fields)
    if with_artifacts:
        add_artifact(store, doc_id, sha, 1, "payer", "employer",
                     {"ein": "12-3456789"})
        add_artifact(store, doc_id, sha, 1, "field", "1",
                     {"value": fields["1"]["value"]})


# ---------------------------------------------------------------------------
# normalize_text / text_fingerprint
# ---------------------------------------------------------------------------

def test_normalize_text_collapses_whitespace_case_punctuation():
    assert D.normalize_text(["  Hello,   WORLD! "]) == "hello world"
    assert D.normalize_text(["end.start"]) == "end start"
    assert D.normalize_text(["a\t\nb"]) == "a b"
    # deterministic across calls and page splits
    assert (D.normalize_text(["ab", "cd"])
            == D.normalize_text(["ab\ncd"])
            == D.normalize_text(["  AB\nCD  "]))

def test_text_fingerprint_stable_and_sensitive():
    assert D.text_fingerprint(TEXT_A) == D.text_fingerprint(TEXT_A2)
    assert D.text_fingerprint(TEXT_A) != D.text_fingerprint(TEXT_OTHER)
    assert len(D.text_fingerprint(TEXT_A)) == 64


# ---------------------------------------------------------------------------
# L1: structural -- no group, one bronze, N aliases
# ---------------------------------------------------------------------------

def test_l1_same_bytes_two_paths_one_bronze_two_aliases_no_group():
    store = FakeStore()
    sha = "a" * 64
    assert store.register_bronze(sha, 50) is True
    assert store.register_bronze(sha, 50) is False  # already there
    store.add_alias(sha, "/inbox/w2.pdf")
    store.add_alias(sha, "/vault/w2-copy.pdf")
    assert D.assess_new_bronze(store, sha) == []
    counts = store.table_counts()
    assert counts["bronze"] == 1
    assert counts["bronze_alias"] == 2
    assert counts["dup_group"] == 0
    assert D.open_groups(store) == {}


def test_assess_new_bronze_unknown_hash_safe():
    store = FakeStore()
    assert D.assess_new_bronze(store, "0" * 64) == []
    assert D.assess_silver_doc(store, "nope") == []


def test_assess_safe_on_empty_tables():
    store = FakeStore()
    assert D.open_groups(store) == {}
    assert D.open_conflicts(store) == {}


# ---------------------------------------------------------------------------
# L2: text-identical, different bytes
# ---------------------------------------------------------------------------

def test_l2_same_text_diff_bytes_group_open():
    store = FakeStore()
    sha1, sha2 = "1" * 64, "2" * 64
    add_bronze(store, sha1, TEXT_A)
    add_bronze(store, sha2, TEXT_A2)
    D.compute_and_store_text_fingerprint(store, sha1)
    created = D.assess_new_bronze(store, sha2)
    assert len(created) == 1
    gid = created[0]
    with store.txn() as c:
        cls, status = c.execute(
            "SELECT class, status FROM dup_group WHERE group_id = ?",
            (gid,)).fetchone()
        members = dict(c.execute(
            "SELECT member_key, role FROM dup_member WHERE group_id = ?",
            (gid,)).fetchall())
    assert cls == "L2" and status == "open"
    assert members == {sha2: "candidate", sha1: "reference"}
    # gold-relevant "unresolved" state visible via counts only
    assert D.open_groups(store) == {"L2": 1}


def test_l2_idempotent_rerun_same_group_id():
    store = FakeStore()
    sha1, sha2 = "1" * 64, "2" * 64
    add_bronze(store, sha1, TEXT_A)
    add_bronze(store, sha2, TEXT_A2)
    first = D.assess_new_bronze(store, sha2)
    second = D.assess_new_bronze(store, sha2)
    assert first == second and len(first) == 1
    assert store.table_counts()["dup_group"] == 1


def test_l2_distinct_text_no_group():
    store = FakeStore()
    add_bronze(store, "1" * 64, TEXT_A)
    add_bronze(store, "2" * 64, TEXT_OTHER)
    assert D.assess_new_bronze(store, "2" * 64) == []
    assert D.open_groups(store) == {}


def test_compute_and_store_text_fingerprint_hook():
    store = FakeStore()
    sha = "1" * 64
    add_bronze(store, sha, TEXT_A)
    fp = D.compute_and_store_text_fingerprint(store, sha)
    assert fp == D.text_fingerprint(TEXT_A)
    with store.txn() as c:
        stored = c.execute(
            "SELECT text_fingerprint FROM bronze WHERE hash = ?",
            (sha,)).fetchone()[0]
    assert stored == fp
    # no derived text -> safe None
    store.register_bronze("9" * 64, 10)
    assert D.compute_and_store_text_fingerprint(store, "9" * 64) is None
    assert D.compute_and_store_text_fingerprint(store, "0" * 64) is None


# ---------------------------------------------------------------------------
# L3: field-identical
# ---------------------------------------------------------------------------

def test_l3_same_w2_values_different_layout_group():
    store = FakeStore()
    _w2_doc(store, "doc1", "a" * 64, W2_A, TEXT_A)
    _w2_doc(store, "doc2", "b" * 64, W2_B_SAME, TEXT_A2)
    created = D.assess_silver_doc(store, "doc2")
    assert len(created) == 1
    gid = created[0]
    with store.txn() as c:
        cls, status = c.execute(
            "SELECT class, status FROM dup_group WHERE group_id = ?",
            (gid,)).fetchone()
        members = sorted(r[0] for r in c.execute(
            "SELECT member_key FROM dup_member WHERE group_id = ?",
            (gid,)).fetchall())
        n_fp = c.execute(
            "SELECT COUNT(*) FROM field_fingerprint").fetchone()[0]
    assert cls == "L3" and status == "open"
    assert members == ["doc1", "doc2"]
    assert n_fp >= 2  # one doc-level fingerprint per doc
    assert D.open_groups(store) == {"L3": 1}


def test_l3_salted_hashes_not_raw():
    store = FakeStore()
    _w2_doc(store, "doc1", "a" * 64, W2_A, TEXT_A)
    D.assess_silver_doc(store, "doc1")
    with store.txn() as c:
        fps = [r[0] for r in c.execute(
            "SELECT fp_hash FROM field_fingerprint").fetchall()]
        salt = c.execute(
            "SELECT salt_hex FROM dup_salt WHERE salt_id = 'v1'").fetchone()[0]
    assert len(salt) == 64  # secrets.token_hex(32)
    # same input, same store -> same salted hash across docs (matchable)
    _w2_doc(store, "doc2", "b" * 64, W2_B_SAME, TEXT_A2)
    D.assess_silver_doc(store, "doc2")
    with store.txn() as c:
        fps2 = [r[0] for r in c.execute(
            "SELECT fp_hash FROM field_fingerprint").fetchall()]
    assert set(fps) & set(fps2)  # the doc-level fingerprint collides
    # and it is NOT the unsalted hash of the canonical input
    raw = hashlib.sha256(D._canon(
        D._doc_fingerprint_input("W-2", 2024, W2_A, [])).encode()).hexdigest()
    assert raw not in fps2


def test_l3_different_values_no_group():
    store = FakeStore()
    _w2_doc(store, "doc1", "a" * 64, W2_A, TEXT_A)
    _w2_doc(store, "doc2", "b" * 64, W2_C_DIFF, TEXT_A2)
    # box 1 differs -> L3 must NOT fire (L4 supersedes may, at bronze level)
    created = D.assess_silver_doc(store, "doc2")
    assert created == []
    assert "L3" not in D.open_groups(store)


def _lot(desc, acq, sold, proceeds, basis):
    return {"description": desc, "date_acquired": acq, "date_sold": sold,
            "proceeds_1d": proceeds, "basis_1e": basis,
            "wash_1g": None, "term": "long", "covered": True}


def test_l3_lot_level_same_lot_across_statements():
    store = FakeStore()
    lot_shared = _lot("ACME 100 SH", "2020-01-15", "2024-03-01",
                      "12345.67", "10000.00")
    f1 = {"broker": _field("Brokerage Inc"),
          "lots": _field([lot_shared, _lot("OTHER 10 SH", "2021-06-01",
                                           "2024-04-01", "999.00",
                                           "800.00")])}
    f2 = {"broker": _field("Brokerage Inc"),
          "lots": _field([dict(lot_shared),  # same values, new dict
                          _lot("THIRD 5 SH", "2022-01-01", "2024-05-01",
                               "111.00", "100.00")])}
    add_bronze(store, "a" * 64, ["1099-B one"])
    add_doc(store, "stmt1", "a" * 64, "1099-B", 2024, f1)
    add_bronze(store, "b" * 64, ["1099-B two"])
    add_doc(store, "stmt2", "b" * 64, "1099-B", 2024, f2)
    created = D.assess_silver_doc(store, "stmt2")
    assert len(created) == 1  # one lot group; doc fps differ (lot sets differ)
    gid = created[0]
    with store.txn() as c:
        cls = c.execute(
            "SELECT class FROM dup_group WHERE group_id = ?",
            (gid,)).fetchone()[0]
        members = sorted(r[0] for r in c.execute(
            "SELECT member_key FROM dup_member WHERE group_id = ?",
            (gid,)).fetchall())
    assert cls == "L3"
    assert members == ["stmt1:lot:0", "stmt2:lot:0"]


# ---------------------------------------------------------------------------
# Corroboration (never duplicate)
# ---------------------------------------------------------------------------

def _wi_doc(store, doc_id, sha, year, entries):
    fields = {}
    for i, (name, boxes) in enumerate(entries, start=1):
        fields[f"payer{i}.name"] = _field(name)
        for box, val in boxes.items():
            fields[f"payer{i}.{box}"] = _field(val)
    add_bronze(store, sha, ["wage and income transcript"])
    add_doc(store, doc_id, sha, "WAGE_INCOME_TRANSCRIPT", year, fields)


def test_corroboration_wi_entry_vs_w2_not_duplicate():
    store = FakeStore()
    _w2_doc(store, "w2", "a" * 64, W2_A, TEXT_A)
    _wi_doc(store, "wi", "c" * 64, 2024,
            [("Acme Corp", {"1": "52345.67", "2": "4100.00"})])
    created = D.assess_silver_doc(store, "wi")
    assert len(created) == 1
    gid = created[0]
    with store.txn() as c:
        cls = c.execute(
            "SELECT class FROM dup_group WHERE group_id = ?",
            (gid,)).fetchone()[0]
    assert cls == "corroboration"
    assert cls != "duplicate"
    assert D.open_groups(store) == {"corroboration": 1}


def test_corroboration_disagreement_raises_conflict():
    store = FakeStore()
    _w2_doc(store, "w2", "a" * 64, W2_A, TEXT_A)
    _wi_doc(store, "wi", "c" * 64, 2024,
            [("Acme Corp", {"1": "52000.00"})])  # wages disagree
    D.assess_silver_doc(store, "wi")
    assert D.open_conflicts(store) == {"corroboration": 1}
    with store.txn() as c:
        row = c.execute(
            "SELECT conflict_id, field FROM conflict").fetchone()
        opts = c.execute(
            "SELECT option_key FROM conflict_option WHERE conflict_id = ?"
            " ORDER BY option_key", (row[0],)).fetchall()
    assert row[1] == "box_1"
    assert [o[0] for o in opts] == ["w2:1", "wi:1"]


def test_corroboration_no_payer_match_no_group():
    store = FakeStore()
    _w2_doc(store, "w2", "a" * 64, W2_A, TEXT_A)
    _wi_doc(store, "wi", "c" * 64, 2024,
            [("Unrelated LLC", {"1": "100.00"})])
    assert D.assess_silver_doc(store, "wi") == []
    assert D.open_groups(store) == {}


# ---------------------------------------------------------------------------
# L4: supersedes
# ---------------------------------------------------------------------------

def test_l4_corrected_marker_supersedes_candidate():
    store = FakeStore()
    _w2_doc(store, "orig", "a" * 64, W2_A, TEXT_A)
    _w2_doc(store, "corr", "b" * 64, W2_B_SAME,
            ["Form W-2  CORRECTED\nBox 1  52345.67\nEIN 12-3456789"])
    created = D.assess_new_bronze(store, "b" * 64)
    assert len(created) == 1
    gid = created[0]
    with store.txn() as c:
        cls, status = c.execute(
            "SELECT class, status FROM dup_group WHERE group_id = ?",
            (gid,)).fetchone()
        members = dict(c.execute(
            "SELECT member_key, role FROM dup_member WHERE group_id = ?",
            (gid,)).fetchall())
    assert cls == "supersedes" and status == "open"
    assert members == {"corr": "candidate", "orig": "reference"}


def test_l4_changed_values_no_marker_supersedes_candidate():
    store = FakeStore()
    _w2_doc(store, "orig", "a" * 64, W2_A, TEXT_A)
    _w2_doc(store, "amended", "b" * 64, W2_C_DIFF, TEXT_AMENDED)
    created = D.assess_new_bronze(store, "b" * 64)
    assert created and len(created) == 1
    with store.txn() as c:
        cls = c.execute(
            "SELECT class FROM dup_group WHERE group_id = ?",
            (created[0],)).fetchone()[0]
    assert cls == "supersedes"


def test_l4_identical_no_marker_no_supersedes():
    store = FakeStore()
    _w2_doc(store, "orig", "a" * 64, W2_A, TEXT_A)
    _w2_doc(store, "same", "b" * 64, W2_B_SAME, TEXT_RESEND)
    # identical values, no marker -> no L4 action at bronze level
    # (L3 fires at silver level instead)    assert D.assess_new_bronze(store, "b" * 64) == []


def test_l4_corrected_first_still_supersedes():
    # Order-independence: the CORRECTED doc may arrive before the
    # original; assessing the original must still raise supersedes.
    store = FakeStore()
    _w2_doc(store, "corr", "b" * 64, W2_B_SAME,
            ["Form W-2  CORRECTED\nBox 1  52345.67\nEIN 12-3456789"])
    _w2_doc(store, "orig", "a" * 64, W2_A, TEXT_A)
    created = D.assess_new_bronze(store, "a" * 64)
    assert len(created) == 1
    with store.txn() as c:
        cls = c.execute(
            "SELECT class FROM dup_group WHERE group_id = ?",
            (created[0],)).fetchone()[0]
    assert cls == "supersedes"


def _b1099_fields(proceeds):
    return {
        "broker": _field("EXAMPLE BROKERAGE"),
        "lots": {"value": [{
            "description": "10 SH XYZ", "date_acquired": "01/15/2024",
            "date_sold": "06/15/2024", "proceeds_1d": proceeds,
            "basis_1e": "1500.00", "wash_1g": "0.00",
            "term": "short", "covered": "covered"}]},
    }


def _b1099_doc(store, doc_id, sha, proceeds, note=""):
    texts = ["Form 1099-B Tax Year 2024\nBroker: EXAMPLE BROKERAGE\n"
             f"Lot 1 proceeds {proceeds}\n{note}"]
    add_bronze(store, sha, texts)
    add_doc(store, doc_id, sha, "1099-B", 2024, _b1099_fields(proceeds))


def test_l4_1099b_changed_lot_values_supersedes():
    # 1099-B key boxes carry no amounts; lot comparison drives L4.
    store = FakeStore()
    _b1099_doc(store, "orig", "a" * 64, "1000.00")
    _b1099_doc(store, "amended", "b" * 64, "1100.00")
    created = D.assess_new_bronze(store, "b" * 64)
    assert len(created) == 1
    with store.txn() as c:
        cls = c.execute(
            "SELECT class FROM dup_group WHERE group_id = ?",
            (created[0],)).fetchone()[0]
    assert cls == "supersedes"


def test_l4_1099b_identical_lots_no_supersedes():
    store = FakeStore()
    _b1099_doc(store, "orig", "a" * 64, "1000.00", note="Page 1 of 1.")
    _b1099_doc(store, "resend", "b" * 64, "1000.00", note="Page 1 of 2.")
    assert D.assess_new_bronze(store, "b" * 64) == []


# ---------------------------------------------------------------------------
# Conflicts: raised on disagreement, never auto-resolved
# ---------------------------------------------------------------------------

def test_l3_nonkey_disagreement_raises_duplicate_conflict():
    store = FakeStore()
    f_a = dict(W2_A)
    f_a["12"] = _field("111.11")
    f_b = dict(W2_B_SAME)
    f_b["12"] = _field("999.99")  # non-key box disagrees, both present
    _w2_doc(store, "doc1", "a" * 64, f_a, TEXT_A)
    _w2_doc(store, "doc2", "b" * 64, f_b, TEXT_A2)
    D.assess_silver_doc(store, "doc2")
    assert D.open_groups(store) == {"L3": 1}
    assert D.open_conflicts(store) == {"duplicate": 1}
    with store.txn() as c:
        field = c.execute("SELECT field FROM conflict").fetchone()[0]
    assert field == "12"


def test_l2_field_disagreement_raises_conflict():
    store = FakeStore()
    _w2_doc(store, "doc1", "a" * 64, W2_A, TEXT_A)
    _w2_doc(store, "doc2", "b" * 64, W2_C_DIFF, TEXT_A2)
    D.assess_new_bronze(store, "b" * 64)   # L2 group at bronze level
    D.assess_silver_doc(store, "doc2")     # field disagreement -> conflict
    assert D.open_conflicts(store).get("duplicate", 0) >= 1


def test_flag_reextract_options_validated_and_reextracted():
    store = FakeStore()
    cid = D.flag_reextract(store, doc_id="d1", field="fields.1",
                           validated_value="52345.67",
                           reextracted_value="52345.76")
    with store.txn() as c:
        cls, status = c.execute(
            "SELECT class, status FROM conflict WHERE conflict_id = ?",
            (cid,)).fetchone()
        opts = dict(c.execute(
            "SELECT option_key, value_json FROM conflict_option"
            " WHERE conflict_id = ?", (cid,)).fetchall())
    assert cls == "reextract" and status == "open"
    assert set(opts) == {"validated", "re-extracted"}
    assert D.open_conflicts(store) == {"reextract": 1}


def test_parser_ambiguity_raises_parser_conflict():
    store = FakeStore()
    cid = D.parser_ambiguity(store, "d1", "total_tax", [
        {"option_key": "line:total_tax_liability", "value_json": "1200.00",
         "evidence_ref": "d1:p3"},
        {"option_key": "line:total_tax_payments", "value_json": "1500.00",
         "evidence_ref": "d1:p5"},
    ])
    with store.txn() as c:
        cls, field = c.execute(
            "SELECT class, field FROM conflict WHERE conflict_id = ?",
            (cid,)).fetchone()
    assert cls == "parser" and field == "total_tax"


def test_raise_conflict_idempotent_reraise():
    store = FakeStore()
    opts = [{"option_key": "a", "value_json": "1"},
            {"option_key": "b", "value_json": "2"}]
    c1 = D.raise_conflict(store, cls="duplicate", field="f", options=opts)
    c2 = D.raise_conflict(store, cls="duplicate", field="f", options=opts)
    assert c1 == c2
    assert store.table_counts()["conflict"] == 1


def test_raise_conflict_rejects_bad_class_and_empty_options():
    store = FakeStore()
    with pytest.raises(ValueError):
        D.raise_conflict(store, cls="latest-wins", field="f",
                         options=[{"option_key": "a", "value_json": "1"}])
    with pytest.raises(ValueError):
        D.raise_conflict(store, cls="duplicate", field="f", options=[])


# ---------------------------------------------------------------------------
# Disposition: rule_on_group / choose_conflict (explicit only)
# ---------------------------------------------------------------------------

def test_rule_on_group_keep_one_disposes_with_decision_log():
    store = FakeStore()
    _w2_doc(store, "doc1", "a" * 64, W2_A, TEXT_A)
    _w2_doc(store, "doc2", "b" * 64, W2_B_SAME, TEXT_A2)
    gid = D.assess_silver_doc(store, "doc2")[0]
    seq = D.rule_on_group(store, gid, ruling="keep_one", primary="doc1",
                          reason="operator kept the digital copy")
    assert isinstance(seq, int) and seq >= 1
    with store.txn() as c:
        status = c.execute(
            "SELECT status FROM dup_group WHERE group_id = ?",
            (gid,)).fetchone()[0]
        kind, payload = c.execute(
            "SELECT kind, payload_json FROM decision_log"
            " WHERE group_id = ? ORDER BY seq DESC LIMIT 1",
            (gid,)).fetchone()
    assert status == "disposed"
    assert kind == "duplicate_ruling"
    p = json.loads(payload)
    assert p["group_id"] == gid and p["ruling"] == "keep_one"
    assert p["primary"] == "doc1"
    assert p["reason"] == "operator kept the digital copy"
    assert "ts" in p
    assert D.open_groups(store) == {}


def test_rule_on_group_supersedes_authoritative():
    store = FakeStore()
    _w2_doc(store, "orig", "a" * 64, W2_A, TEXT_A)
    _w2_doc(store, "corr", "b" * 64, W2_B_SAME,
            ["Form W-2  CORRECTED\nBox 1  52345.67\nEIN 12-3456789"])
    gid = D.assess_new_bronze(store, "b" * 64)[0]
    D.rule_on_group(store, gid, ruling="authoritative", primary="corr",
                    reason="corrected form supersedes")
    with store.txn() as c:
        kind, payload = c.execute(
            "SELECT kind, payload_json FROM decision_log").fetchone()
    assert kind == "supersedes_ruling"
    p = json.loads(payload)
    assert p["authoritative"] == "corr"


def test_rule_on_group_rejects():
    store = FakeStore()
    _w2_doc(store, "doc1", "a" * 64, W2_A, TEXT_A)
    _w2_doc(store, "doc2", "b" * 64, W2_B_SAME, TEXT_A2)
    gid = D.assess_silver_doc(store, "doc2")[0]
    with pytest.raises(KeyError):
        D.rule_on_group(store, "0" * 32, ruling="distinct")
    with pytest.raises(ValueError):  # bad ruling for class
        D.rule_on_group(store, gid, ruling="authoritative", primary="doc1")
    with pytest.raises(ValueError):  # keep_one needs a primary
        D.rule_on_group(store, gid, ruling="keep_one")
    with pytest.raises(ValueError):  # primary must be a member
        D.rule_on_group(store, gid, ruling="keep_one", primary="nope")
    D.rule_on_group(store, gid, ruling="distinct")
    with pytest.raises(ValueError):  # already disposed
        D.rule_on_group(store, gid, ruling="distinct")


def test_choose_conflict_records_options_shown_choice_reason():
    store = FakeStore()
    cid = D.flag_reextract(store, doc_id="d1", field="fields.1",
                           validated_value="52345.67",
                           reextracted_value="52345.76")
    seq = D.choose_conflict(store, cid, choice="validated",
                            reason="operator confirmed the page")
    assert isinstance(seq, int)
    with store.txn() as c:
        status = c.execute(
            "SELECT status FROM conflict WHERE conflict_id = ?",
            (cid,)).fetchone()[0]
        kind, payload = c.execute(
            "SELECT kind, payload_json FROM decision_log").fetchone()
    assert status == "disposed"
    assert kind == "conflict_choice"
    p = json.loads(payload)
    assert p["conflict_id"] == cid
    assert p["options_shown"] == ["re-extracted", "validated"]
    assert p["choice"] == "validated"
    assert p["reason"] == "operator confirmed the page"
    assert "ts" in p
    assert D.open_conflicts(store) == {}


def test_choose_conflict_no_default_no_autopick():
    store = FakeStore()
    cid = D.flag_reextract(store, doc_id="d1", field="fields.1",
                           validated_value="1", reextracted_value="2")
    with pytest.raises(ValueError):  # not one of the recorded options
        D.choose_conflict(store, cid, choice="latest")
    with pytest.raises(TypeError):  # choice is required: no default exists
        D.choose_conflict(store, cid)
    with pytest.raises(KeyError):
        D.choose_conflict(store, "0" * 32, choice="validated")
    D.choose_conflict(store, cid, choice="validated")
    with pytest.raises(ValueError):  # already disposed
        D.choose_conflict(store, cid, choice="validated")


def test_no_mechanical_resolution_paths_in_module():
    # choose_conflict and rule_on_group must require explicit disposition;
    # no default, no auto-pick parameter anywhere in their signatures.
    for fn, required in ((D.choose_conflict, "choice"),
                         (D.rule_on_group, "ruling")):
        params = inspect.signature(fn).parameters
        assert params[required].default is inspect.Parameter.empty
    # Banned policies must not appear as code identifiers. Docstrings and
    # comments are stripped first: the module docstring names these
    # policies precisely to forbid them.
    import re
    src = inspect.getsource(D)
    code = re.sub(r'"""[\s\S]*?"""', "", src)
    code = re.sub(r"#[^\n]*", "", code)
    for banned in ("latest_wins", "latest-wins", "confidence_wins",
                   "first_match_wins", "auto_resolve", "autoresolve",
                   "default_choice", "preselect"):
        assert banned not in code, banned


# ---------------------------------------------------------------------------
# Blind contract: counts only, never values
# ---------------------------------------------------------------------------

def test_open_groups_conflicts_counts_only_no_pii():
    store = FakeStore()
    _w2_doc(store, "doc1", "a" * 64, W2_A, TEXT_A)
    _w2_doc(store, "doc2", "b" * 64, W2_B_SAME, TEXT_A2)
    D.assess_new_bronze(store, "b" * 64)
    D.assess_silver_doc(store, "doc2")
    D.flag_reextract(store, doc_id="doc1", field="fields.1",
                     validated_value="52345.67", reextracted_value="1.00")
    groups = D.open_groups(store)
    conflicts = D.open_conflicts(store)

    def sweep(obj, path="root"):
        if isinstance(obj, dict):
            for k, v in obj.items():
                assert isinstance(k, str), path
                # keys are class names only -- never hashes, ids, or values
                assert k in {"L1", "L2", "L3", "corroboration", "supersedes",
                             "duplicate", "reextract", "ocr", "parser"}, \
                    f"{path}: unexpected key {k!r}"
                sweep(v, f"{path}.{k}")
        elif isinstance(obj, (list, tuple)):
            for i, v in enumerate(obj):
                sweep(v, f"{path}[{i}]")
        else:
            assert isinstance(obj, int), f"{path}: non-count {obj!r}"

    sweep(groups)
    sweep(conflicts)
    blob = json.dumps({"groups": groups, "conflicts": conflicts})
    assert "52345.67" not in blob and "Acme" not in blob


def test_salt_one_per_store_persisted():
    s1, s2 = FakeStore(), FakeStore()
    with s1.txn() as c:
        a = D._get_salt(c)
        b = D._get_salt(c)
    assert a == b and len(a) == 64
    with s1.txn() as c:
        n = c.execute("SELECT COUNT(*) FROM dup_salt").fetchone()[0]
    assert n == 1
    with s2.txn() as c:
        assert D._get_salt(c) != a  # per-store salt


# ---------------------------------------------------------------------------
# Hook signatures (contract section 8 -- W2 calls these)
# ---------------------------------------------------------------------------

def test_hook_signatures_match_contract_section_8():
    # assess_new_bronze(store, bronze_hash) -- contract 8 step 5
    assert (list(inspect.signature(D.assess_new_bronze).parameters)
            == ["store", "bronze_hash"])
    # assess_silver_doc(store, doc_id) -- contract 8 step 6
    assert (list(inspect.signature(D.assess_silver_doc).parameters)
            == ["store", "doc_id"])
    store = FakeStore()
    assert D.assess_new_bronze(store, "0" * 64) == []  # positional call
    assert D.assess_silver_doc(store, "x") == []
