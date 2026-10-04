-- Medallion store DDL (v1) -- Arc B, workstream W1 owns this file.
--
-- Single source of truth for the medallion SQLite schema. Contract §3.
-- Applied by taxprep/mstore.py on first open of <data_dir>/medallion.sqlite.
--
-- Notes:
--   * SQLite location: <data_dir>/medallion.sqlite, journal_mode=WAL,
--     busy_timeout=5000, file mode 0600 on creation (see mstore.py).
--   * decision_log is append-only (I6): the two triggers below REFUSE any
--     UPDATE or DELETE at the database level, not just through the API.
--   * Volatile bookkeeping columns (first_seen/last_seen/ts/created_at/
--     updated_at) are EXCLUDED from db_digest() so that ingest-twice
--     idempotency comparisons stay stable (see mstore._DIGEST_COLS).
--   * silver_doc carries no doc-level text-provenance columns (text_source,
--     ocr_engine, engine_version, ocr_mode, attempts, mean_confidence):
--     contract §3 v1 has no such columns. They live in doc_provenance
--     (W1 addition, additive only -- no §3 table is altered), so the
--     Document facade round-trips them exactly as the JSONL store did.
--     R5 provenance lives in bronze_text rows (W2).

CREATE TABLE doc_provenance (         -- W1: doc-level text provenance (R5)
    doc_id TEXT PRIMARY KEY REFERENCES silver_doc(doc_id) ON DELETE CASCADE,
    text_source TEXT,                 -- native|sidecar|form-field|ocr|
                                      -- image-pdf|broker-csv|error|blocked
    reason_code TEXT,
    ocr_engine TEXT,
    engine_version TEXT,
    ocr_mode TEXT,                    -- skip-text|redo-ocr|force-ocr
    attempts_json TEXT NOT NULL DEFAULT '[]',
    mean_confidence REAL
);
CREATE TABLE bronze (
    hash TEXT PRIMARY KEY,            -- sha256 hex of source bytes
    size INTEGER NOT NULL,            -- -1 = unknown (legacy tombstones)
    source_root TEXT,                 -- R11 source root, nullable
    first_seen TEXT NOT NULL,         -- ISO-8601 UTC
    last_seen TEXT NOT NULL,
    selection_state TEXT NOT NULL DEFAULT 'selected',  -- selected|deselected
    encryption TEXT,                  -- 'owner-only' or NULL (X1)
    text_fingerprint TEXT,            -- sha256 of normalized per-page text (L2)
    blocked_reason TEXT               -- NULL when ingestible; else reason code
);
CREATE TABLE bronze_alias (
    hash TEXT NOT NULL REFERENCES bronze(hash),
    path TEXT NOT NULL,               -- path as seen at ingest
    last_seen TEXT NOT NULL,
    PRIMARY KEY (hash, path)
);
CREATE TABLE bronze_bytes_ref (       -- where the content-addressed bytes live
    hash TEXT PRIMARY KEY REFERENCES bronze(hash),
    rel_path TEXT NOT NULL            -- e.g. bronze/ab/abcdef... (read-only)
);
CREATE TABLE bronze_text (            -- per-page derived text, keyed per I5
    hash TEXT NOT NULL REFERENCES bronze(hash),
    page INTEGER NOT NULL,            -- 1-based; 0 = whole-doc pseudo page
    text_source TEXT NOT NULL,        -- native|form-field|ocr|sidecar|broker-csv
    engine TEXT,
    engine_version TEXT,
    ocr_mode TEXT,
    derivation_version TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    text TEXT NOT NULL,
    PRIMARY KEY (hash, page, derivation_version, config_hash)
);
CREATE TABLE silver_doc (             -- mirrors the current Document record
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
    fields_json TEXT NOT NULL DEFAULT '{}',  -- operational field store (compat)
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE silver_artifact (
    artifact_id TEXT PRIMARY KEY,     -- sha256(bronze_hash:page:type:anchor)[:32]
    doc_id TEXT NOT NULL REFERENCES silver_doc(doc_id),
    bronze_hash TEXT NOT NULL,
    page INTEGER NOT NULL,
    artifact_type TEXT NOT NULL,      -- field|payer|lot|section
    anchor TEXT NOT NULL,             -- field key | lot key | payer key | section id
    value_json TEXT NOT NULL,         -- canonical JSON
    offsets_json TEXT,                -- R15 geometry when available
    derivation_version TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE decision_log (           -- append-only (I6); never UPDATE/DELETE
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    actor TEXT NOT NULL,              -- operator|system
    kind TEXT NOT NULL,               -- validate|edit|exclude|duplicate_ruling|
                                      -- supersedes_ruling|conflict_choice|
                                      -- relevance_override
    artifact_id TEXT,
    doc_id TEXT,
    group_id TEXT,
    payload_json TEXT NOT NULL
);
-- I6 enforcement: refuse UPDATE/DELETE on decision_log at the DB level.
CREATE TRIGGER decision_log_no_update BEFORE UPDATE ON decision_log
BEGIN
    SELECT RAISE(ABORT, 'decision_log is append-only: UPDATE refused');
END;
CREATE TRIGGER decision_log_no_delete BEFORE DELETE ON decision_log
BEGIN
    SELECT RAISE(ABORT, 'decision_log is append-only: DELETE refused');
END;
CREATE TABLE dup_group (
    group_id TEXT PRIMARY KEY,        -- stable: sha256(class:sorted member keys)[:32]
    class TEXT NOT NULL,              -- L1|L2|L3|corroboration|supersedes
    status TEXT NOT NULL DEFAULT 'open',
    created_at TEXT NOT NULL,
    disposed_at TEXT
);
CREATE TABLE dup_member (
    group_id TEXT NOT NULL REFERENCES dup_group(group_id),
    member_key TEXT NOT NULL,         -- bronze hash | artifact id | doc id
    role TEXT,                        -- candidate|reference
    PRIMARY KEY (group_id, member_key)
);
CREATE TABLE conflict (
    conflict_id TEXT PRIMARY KEY,     -- stable sha256(class:field:sorted options)[:32]
    class TEXT NOT NULL,              -- duplicate|corroboration|reextract|ocr|parser|supersedes
    field TEXT,                       -- disputed field path, nullable
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
CREATE TABLE field_fingerprint (      -- L3 salted hashes; agent sees counts only
    artifact_id TEXT NOT NULL REFERENCES silver_artifact(artifact_id)
        ON DELETE CASCADE,  -- fingerprints are derived data, recomputed
                             -- per assessment; artifact replace drops them
    fp_hash TEXT NOT NULL,
    salt_id TEXT NOT NULL,
    PRIMARY KEY (artifact_id, fp_hash)
);
CREATE TABLE gold_run (
    run_id TEXT PRIMARY KEY,          -- sha256(kind:ts:input_digest)[:32]
    ts TEXT NOT NULL,
    kind TEXT NOT NULL,               -- carryforward|schedule_d|delta_1040x|gap_report
    params_json TEXT NOT NULL,
    input_digest TEXT NOT NULL,
    output_json TEXT NOT NULL,
    output_digest TEXT NOT NULL
);
