"""Tests for taxprep.operator_csv (R23 addendum: format v2 + medallion).

All fixtures synthetic. Covers: v2 prefix parsing (@page, #/## headings,
% boilerplate, ! source errors, \\ escape), the prefixed-empty-value
invariant, blank-printed fields, trailing-colon stripping, transaction
tables (multi-line explanations, @page inside, table end), the CSV as a
new Bronze source document (content hash, PDF linkage, extractor
version), Silver fields with CSV-row/@page provenance, R16a
corroboration conflicts, idempotent re-import, supersede-by-hash, and
explicit unresolved-filename handling.
"""

import hashlib
import json

import pytest

from taxprep import duplicates
from taxprep.models import Document
from taxprep.operator_csv import (
    AUDIT_NOTES_KEY,
    CSV_META_KEY,
    FORM_TYPE_OPERATOR_CSV,
    OPERATOR_CSV_VERSION,
    SUPERSEDED_BY_KEY,
    TEXT_SOURCE_OPERATOR_CSV,
    csv_import_hash,
    ingest_operator_csv,
    latest_operator_csv_doc,
    parse_operator_csv,
    values_agree,
)
from taxprep.store import DocumentStore
from taxprep.twocol import normalize_label

CSV_V2_BASIC = (
    "label,value\n"
    "@page 1\n"
    "# Return Transcript\n"
    "Adjusted Gross Income:,\"12,345.67\"\n"
    "Filing Status,Single\n"
    "@page 2\n"
    "## Tax and Credits\n"
    "Total Tax,2345.00\n"
)


def _machine_field(value, text_source="native"):
    return {"value": value, "confidence": "medium",
            "raw_text": f"printed: {value}", "text_source": text_source}


@pytest.fixture()
def store(tmp_path):
    return DocumentStore(tmp_path / "data")


def _make_pdf_doc(store, stem="2024-return-transcript", machine_fields=None):
    doc = Document(
        doc_id=f"doc-{stem}",
        tax_year=2024,
        form_type="RETURN_TRANSCRIPT",
        source_path=f"/synthetic/{stem}.pdf",
        ocr_text_ref=f"ocr/doc-{stem}.txt",
        fields=dict(machine_fields or {}),
        source_sha256="ab" * 32,
    )
    store.upsert(doc)
    return doc.doc_id


def _conflict_rows(store):
    with store.txn() as conn:
        conflicts = conn.execute(
            "SELECT conflict_id, class, field, status FROM conflict"
        ).fetchall()
        options = conn.execute(
            "SELECT conflict_id, option_key, value_json, evidence_ref "
            "FROM conflict_option"
        ).fetchall()
    return conflicts, options


# -- v2 format parsing ---------------------------------------------------


def test_parse_at_page_markers_and_order():
    parsed = parse_operator_csv(CSV_V2_BASIC)
    assert parsed["format"] == "v2"
    assert parsed["pages"] == [1, 2]
    rows = parsed["data_rows"]
    assert [(r["label"], r["value"], r["page"]) for r in rows] == [
        ("Adjusted Gross Income", "12,345.67", 1),
        ("Filing Status", "Single", 1),
        ("Total Tax", "2345.00", 2),
    ]
    assert all(r["csv_row"] >= 2 for r in rows)
    assert parsed["headings"] == [
        {"level": 1, "text": "Return Transcript", "page": 1,
         "csv_row": 3},
        {"level": 2, "text": "Tax and Credits", "page": 2,
         "csv_row": 7},
    ]


def test_parse_trailing_colon_stripped():
    parsed = parse_operator_csv("label,value\nWages:,100.00\n")
    (row,) = parsed["data_rows"]
    assert row["label"] == "Wages"
    assert row["printed_label"] == "Wages:"
    assert row["normalized"] == "WAGES"
    assert row["is_blank"] is False


def test_parse_blank_printed_field_keeps_colon():
    parsed = parse_operator_csv("label,value\nSpouse occupation:,\n")
    (row,) = parsed["data_rows"]
    assert row["label"] == "Spouse occupation:"
    assert row["value"] is None
    assert row["is_blank"] is True


def test_parse_unprefixed_empty_value_without_colon_raises():
    with pytest.raises(ValueError):
        parse_operator_csv("label,value\nSome Label,\n")


def test_parse_boilerplate_ignored():
    parsed = parse_operator_csv(
        "label,value\n"
        "% Request Date: 2024-01-15\n"
        "A,1\n")
    assert [r["label"] for r in parsed["data_rows"]] == ["A"]
    assert parsed["source_errors"] == []


def test_parse_source_error_is_audit_note_only():
    parsed = parse_operator_csv(
        "label,value\n"
        "! Transposed digits here,\n"
        "A,1\n")
    assert parsed["data_rows"][0]["label"] == "A"
    assert parsed["source_errors"] == [
        {"text": "! Transposed digits here", "page": 1, "csv_row": 2}]
    # never a field: no normalized key leaks
    assert all("TRANSPOSED" not in r["normalized"]
               for r in parsed["data_rows"])


def test_parse_escape_prefix_chars():
    parsed = parse_operator_csv(
        "label,value\n"
        "\\#NotAHeading,5.00\n"
        "\\@page,6.00\n"
        "\\\\Backslash,7.00\n")
    labels = [r["label"] for r in parsed["data_rows"]]
    assert labels == ["#NotAHeading", "@page", "\\Backslash"]


def test_parse_prefixed_row_with_value_raises():
    with pytest.raises(ValueError):
        parse_operator_csv("label,value\n# Heading,oops\n")
    with pytest.raises(ValueError):
        parse_operator_csv("label,value\n@page 1,oops\n")
    with pytest.raises(ValueError):
        parse_operator_csv("label,value\n! error,oops\n")
    with pytest.raises(ValueError):
        parse_operator_csv("label,value\n% boiler,oops\n")


def test_parse_quoted_commas_and_embedded_newlines():
    parsed = parse_operator_csv(
        'label,value\n"Wages, salaries, tips","1,234.56"\n'
        '"Note:","line one\nline two"\n')
    rows = parsed["data_rows"]
    assert rows[0]["label"] == "Wages, salaries, tips"
    assert rows[0]["value"] == "1,234.56"
    # value description: first line is the value, rest is description
    assert rows[1]["value"] == "line one\nline two"


def test_parse_implicit_first_page():
    parsed = parse_operator_csv("label,value\nA,1\n@page 3\nB,2\n")
    assert parsed["pages"] == [1, 3]
    assert [r["page"] for r in parsed["data_rows"]] == [1, 3]


def test_parse_requires_header():
    with pytest.raises(ValueError):
        parse_operator_csv("Adjusted Gross Income,100.00\n")
    with pytest.raises(ValueError):
        parse_operator_csv("")


def test_parse_value_without_label_raises():
    with pytest.raises(ValueError):
        parse_operator_csv("label,value\n,100.00\n")


def test_parse_extra_cells_raise():
    with pytest.raises(ValueError):
        parse_operator_csv("label,value\nA,1,EXTRA\n")


def test_csv_import_hash_normalizes_line_endings_and_trailing_space():
    a = "label,value\r\nA,1  \r\nB,2\r\n"
    b = "label,value\nA,1\nB,2\n"
    assert csv_import_hash(a) == csv_import_hash(b)
    assert csv_import_hash(b) != csv_import_hash(b + "C,3\n")


# -- transaction tables --------------------------------------------------


TXN_CSV = (
    "label,value\n"
    "@page 2\n"
    "# TRANSACTIONS\n"
    "CODE,EXPLANATION OF TRANSACTION,CYCLE,DATE,AMOUNT\n"
    "806,\"W-2 withholding\",20241205,04-15-2025,\"1,234.00\"\n"
    "766,\"Credit to account\",,,500.00\n"
    "Total,999.00\n"
)


def test_parse_transaction_table():
    parsed = parse_operator_csv(TXN_CSV)
    trows = parsed["transaction_rows"]
    assert [(t["code"], t["amount"], t["page"]) for t in trows] == [
        ("806", "1,234.00", 2), ("766", "500.00", 2)]
    assert trows[0]["explanation"] == "W-2 withholding"
    assert trows[0]["cycle"] == "20241205"
    assert trows[0]["date"] == "04-15-2025"
    assert trows[1]["cycle"] is None
    # table ends at the first unprefixed non-CODE row
    assert [r["label"] for r in parsed["data_rows"]] == ["Total"]


def test_parse_transaction_multiline_explanation_and_page_marker():
    parsed = parse_operator_csv(
        "label,value\n"
        "# TRANSACTIONS\n"
        "CODE,EXPLANATION OF TRANSACTION,CYCLE,DATE,AMOUNT\n"
        "806,\"line one\nline two\",20241205,04-15-2025,100.00\n"
        "@page 3\n"
        "% repeated header\n"
        "806,\"continued\",,,200.00\n")
    trows = parsed["transaction_rows"]
    assert len(trows) == 2
    assert trows[0]["explanation"] == "line one\nline two"
    assert trows[0]["page"] == 1
    assert trows[1]["page"] == 3  # @page inside the table updates provenance
    assert trows[1]["explanation"] == "continued"


def test_parse_transaction_table_needs_header():
    with pytest.raises(ValueError):
        parse_operator_csv(
            "label,value\n# TRANSACTIONS\n806,x,,,1.00\n")


def test_parse_transaction_table_ends_on_eof():
    parsed = parse_operator_csv(
        "label,value\n# TRANSACTIONS\n"
        "CODE,EXPLANATION OF TRANSACTION,CYCLE,DATE,AMOUNT\n"
        "806,x,,,1.00\n")
    assert len(parsed["transaction_rows"]) == 1


def test_parse_transaction_row_needs_five_cells():
    with pytest.raises(ValueError):
        parse_operator_csv(
            "label,value\n# TRANSACTIONS\n"
            "CODE,EXPLANATION OF TRANSACTION,CYCLE,DATE,AMOUNT\n"
            "806,only-two\n")


# -- ingest: CSV as a new source document ---------------------------------


def test_ingest_creates_bronze_csv_document(store):
    pdf_id = _make_pdf_doc(
        store, machine_fields={"ADJUSTED GROSS INCOME":
                               _machine_field("12,345.67")})
    csv_text = (
        "label,value\n"
        "@page 2\n"
        "Adjusted    Gross Income,12345.67\n"  # Decimal-agrees w/ machine
        "Filing Status,Single\n"               # machine-absent: quiet write
    )
    result = ingest_operator_csv(
        store, pdf_id, csv_text, "2024-return-transcript.csv",
        rule_files=["op-rules-v3.txt"])
    assert result["n_rows"] == 2
    assert result["n_conflicts"] == 0
    assert result["pdf_doc_id"] == pdf_id
    assert result["superseded"] == []
    assert result["csv_hash"] == hashlib.sha256(
        csv_text.encode("utf-8")).hexdigest()

    csv_doc = store.get(result["doc_id"])
    assert csv_doc.form_type == FORM_TYPE_OPERATOR_CSV
    assert csv_doc.parent_doc_id == pdf_id
    assert csv_doc.tax_year == 2024
    assert csv_doc.text_source == TEXT_SOURCE_OPERATOR_CSV
    assert csv_doc.status == "needs_review"  # Operator decision: review UI
    assert csv_doc.source_sha256 == result["csv_hash"]
    # R4: doc_id derives from the CSV bytes
    assert csv_doc.doc_id == result["csv_hash"][:16]
    # Bronze holds the exact bytes
    assert store.get_bronze(result["csv_hash"]) is not None

    entry = csv_doc.fields["ADJUSTED GROSS INCOME"]
    assert entry["value"] == "12345.67"
    assert entry["text_source"] == TEXT_SOURCE_OPERATOR_CSV
    assert entry["confidence"] == "medium"
    assert entry["page"] == 2  # @page linkage
    assert entry["printed_label"] == "Adjusted    Gross Income"
    assert entry["provenance"]["pdf_doc_id"] == pdf_id
    assert entry["provenance"]["csv_row"] >= 2
    assert csv_doc.fields["FILING STATUS"]["value"] == "Single"

    meta = csv_doc.fields[CSV_META_KEY]
    assert meta["pdf_doc_id"] == pdf_id
    assert meta["filename"] == "2024-return-transcript.csv"
    assert meta["csv_hash"] == result["csv_hash"]
    assert meta["csv_format_version"] == OPERATOR_CSV_VERSION
    assert meta["rule_files"] == ["op-rules-v3.txt"]
    assert meta["machine_extractor"]  # twocol version recorded

    # the PDF doc is untouched: no operator namespace, machine kept
    pdf_doc = store.get(pdf_id)
    assert "ADJUSTED GROSS INCOME" in pdf_doc.fields
    assert pdf_doc.fields["ADJUSTED GROSS INCOME"]["value"] == "12,345.67"
    conflicts, _ = _conflict_rows(store)
    assert conflicts == []


def test_ingest_source_error_never_becomes_field(store):
    pdf_id = _make_pdf_doc(store)
    result = ingest_operator_csv(
        store, pdf_id, "label,value\n! bad row,\nA,1\n",
        "2024-return-transcript.csv")
    csv_doc = store.get(result["doc_id"])
    assert "A" in csv_doc.fields
    assert all("BAD" not in k for k in csv_doc.fields)
    assert csv_doc.fields[AUDIT_NOTES_KEY] == [
        {"kind": "source_error", "text": "! bad row",
         "page": 1, "csv_row": 2}]


def test_ingest_conflict_on_machine_operator_diff(store):
    pdf_id = _make_pdf_doc(
        store, machine_fields={"TOTAL TAX": _machine_field("2345.00")})
    result = ingest_operator_csv(
        store, pdf_id, "label,value\nTotal Tax,2400.00\n",
        "2024-return-transcript.csv")
    assert result["n_conflicts"] == 1

    conflicts, options = _conflict_rows(store)
    assert len(conflicts) == 1
    cid, cls, field, status = conflicts[0]
    assert cls == "corroboration"
    assert field == "TOTAL TAX"
    assert status == "open"
    by_key = {o[1]: o for o in options if o[0] == cid}
    assert set(by_key) == {"machine", "operator_csv"}
    assert json.loads(by_key["machine"][2]) == "2345.00"
    assert json.loads(by_key["operator_csv"][2]) == "2400.00"
    # evidence_refs: machine -> PDF doc, operator -> CSV doc
    assert by_key["machine"][3] == pdf_id
    assert by_key["operator_csv"][3] == result["doc_id"]

    # neither side silently overwritten
    assert store.get(pdf_id).fields["TOTAL TAX"]["value"] == "2345.00"
    csv_doc = store.get(result["doc_id"])
    assert csv_doc.fields["TOTAL TAX"]["value"] == "2400.00"


def test_ingest_transaction_row_conflict_by_code(store):
    pdf_id = _make_pdf_doc(
        store, machine_fields={"tc_806": _machine_field("1234.00")})
    result = ingest_operator_csv(
        store, pdf_id,
        "label,value\n# TRANSACTIONS\n"
        "CODE,EXPLANATION OF TRANSACTION,CYCLE,DATE,AMOUNT\n"
        "806,W-2 withholding,20241205,04-15-2025,1500.00\n",
        "2024-return-transcript.csv")
    assert result["n_conflicts"] == 1
    conflicts, _ = _conflict_rows(store)
    assert [c[1] for c in conflicts] == ["corroboration"]
    assert conflicts[0][2] == "tc_806"
    csv_doc = store.get(result["doc_id"])
    assert csv_doc.fields["tc_806"]["value"] == "1500.00"
    assert csv_doc.fields["tc_806"]["transaction"]["code"] == "806"


def test_ingest_transaction_row_agreement_quiet(store):
    pdf_id = _make_pdf_doc(
        store, machine_fields={"tc_806": _machine_field("1234.00")})
    result = ingest_operator_csv(
        store, pdf_id,
        "label,value\n# TRANSACTIONS\n"
        "CODE,EXPLANATION OF TRANSACTION,CYCLE,DATE,AMOUNT\n"
        "806,W-2 withholding,20241205,04-15-2025,\"1,234.00\"\n",
        "2024-return-transcript.csv")
    assert result["n_conflicts"] == 0


def test_ingest_idempotent_reimport(store):
    pdf_id = _make_pdf_doc(
        store, machine_fields={"TOTAL TAX": _machine_field("2345.00")})
    csv_text = "label,value\nTotal Tax,2400.00\n"
    first = ingest_operator_csv(
        store, pdf_id, csv_text, "2024-return-transcript.csv")
    assert first["n_conflicts"] == 1
    conflicts_before, _ = _conflict_rows(store)

    second = ingest_operator_csv(
        store, pdf_id, csv_text, "2024-return-transcript.csv")
    assert second == {"duplicate_import": True, "doc_id": first["doc_id"]}

    conflicts_after, _ = _conflict_rows(store)
    assert len(conflicts_after) == len(conflicts_before)


def test_ingest_reedited_csv_supersedes(store):
    pdf_id = _make_pdf_doc(store)
    first = ingest_operator_csv(
        store, pdf_id, "label,value\nA,1\n",
        "2024-return-transcript.csv")
    second = ingest_operator_csv(
        store, pdf_id, "label,value\nA,2\n",
        "2024-return-transcript.csv")
    assert second["superseded"] == [first["doc_id"]]

    old = store.get(first["doc_id"])
    assert old.fields[SUPERSEDED_BY_KEY] == second["doc_id"]
    # old bytes and audit trail preserved
    assert store.get_bronze(first["csv_hash"]) is not None

    latest = latest_operator_csv_doc(store, pdf_id)
    assert latest.doc_id == second["doc_id"]
    assert latest.fields["A"]["value"] == "2"

    # re-ingesting the old bytes is a no-op: never un-supersedes
    third = ingest_operator_csv(
        store, pdf_id, "label,value\nA,1\n",
        "2024-return-transcript.csv")
    assert third["duplicate_import"] is True
    assert latest_operator_csv_doc(store, pdf_id).doc_id == second["doc_id"]


def test_latest_operator_csv_doc_none_when_absent(store):
    pdf_id = _make_pdf_doc(store)
    assert latest_operator_csv_doc(store, pdf_id) is None
    assert latest_operator_csv_doc(store, "no-such-doc") is None


def test_ingest_unresolved_filename_stem_mismatch(store):
    pdf_id = _make_pdf_doc(store, stem="2024-return-transcript")
    result = ingest_operator_csv(
        store, pdf_id, "label,value\nA,1\n", "2023-return-transcript.csv")
    assert result == {"unresolved": "2023-return-transcript.csv"}
    assert latest_operator_csv_doc(store, pdf_id) is None
    conflicts, _ = _conflict_rows(store)
    assert conflicts == []


def test_ingest_unresolved_missing_doc(store):
    result = ingest_operator_csv(
        store, "doc-does-not-exist", "label,value\nA,1\n",
        "2024-return-transcript.csv")
    assert result == {"unresolved": "2024-return-transcript.csv"}


def test_values_agree_decimal_safe():
    assert values_agree("12,345.67", "12345.67")
    assert values_agree("$100.00", "100.00")
    assert not values_agree("100.00", "200.00")
    assert values_agree("Single", "Single")
    assert not values_agree("Single", "Married")


def test_open_conflicts_counts_corroboration(store):
    pdf_id = _make_pdf_doc(
        store, machine_fields={"TOTAL TAX": _machine_field("2345.00")})
    ingest_operator_csv(
        store, pdf_id, "label,value\nTotal Tax,2400.00\n",
        "2024-return-transcript.csv")
    assert duplicates.open_conflicts(store) == {"corroboration": 1}
