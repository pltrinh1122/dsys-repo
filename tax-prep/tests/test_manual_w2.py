"""Tests for taxprep.manual_w2 (Operator-keyed W-2 ingest).

All fixtures are SYNTHETIC -- no real taxpayer PII anywhere.
"""

import pytest

from taxprep.manual_w2 import (
    TEXT_SOURCE_MANUAL_W2,
    ingest_manual_w2,
    latest_manual_w2_doc,
)
from taxprep.operator_csv import AUDIT_NOTES_KEY, SUPERSEDED_BY_KEY
from taxprep.store import DocumentStore

EXAMPLE = (
    "label,value\n"
    "# W-2 2024 \u2014 Acme Corp,\n"
    "tax_year,2024\n"
    "employer_name,Acme Corp\n"
    "employer_ein,12-3456789\n"
    "1 Wages tips other compensation,52345.67\n"
    "2 Federal income tax withheld,4321.00\n"
    "3 Social security wages,52345.67\n"
    "4 Social security tax withheld,3245.43\n"
    "5 Medicare wages and tips,52345.67\n"
    "6 Medicare tax withheld,758.99\n"
    "12a,D 19500.00\n"
    "12b,W 2500.00\n"
    "13 Retirement plan,X\n"
    "14,CA SDI 612.34\n"
    "15 State,CA\n"
    "16 State wages,52345.67\n"
    "17 State income tax,2100.00\n"
)

MINIMAL = (
    "label,value\n"
    "tax_year,2024\n"
    "employer_name,Acme Corp\n"
    "employer_ein,12-3456789\n"
    "1 Wages tips other compensation,52345.67\n"
    "2 Federal income tax withheld,4321.00\n"
    "3 Social security wages,52345.67\n"
    "4 Social security tax withheld,3245.43\n"
    "5 Medicare wages and tips,52345.67\n"
    "6 Medicare tax withheld,758.99\n"
)


@pytest.fixture()
def store(tmp_path):
    return DocumentStore(tmp_path / "data")


def _ingest(store, text, filename="w2-manual-2024-acme.csv"):
    return ingest_manual_w2(store, text, filename)


def test_example_ingests_to_expected_keys(store):
    res = _ingest(store, EXAMPLE)
    doc = store.get(res["doc_id"])
    assert doc.form_type == "W-2"
    assert doc.tax_year == 2024
    assert doc.text_source == TEXT_SOURCE_MANUAL_W2
    assert doc.status == "needs_review"
    assert doc.parent_doc_id is None
    f = doc.fields
    # verify.py / transcript reconciliation keys.
    assert f["1"]["value"] == "52345.67"
    assert f["2"]["value"] == "4321.00"
    assert f["3"]["value"] == "52345.67"
    assert f["4"]["value"] == "3245.43"
    assert f["5"]["value"] == "52345.67"
    assert f["6"]["value"] == "758.99"
    assert f["employer_name"]["value"] == "Acme Corp"
    assert f["employer_ein"]["value"] == "12-3456789"
    assert f["tax_year"]["value"] == "2024"
    assert f["12a"]["value"] == "D 19500.00"
    assert f["12b"]["value"] == "W 2500.00"
    assert f["13_retirement"]["value"] == "X"
    assert f["14"]["value"] == "CA SDI 612.34"
    assert f["15_state"]["value"] == "CA"
    assert f["16"]["value"] == "52345.67"
    assert f["17"]["value"] == "2100.00"
    # Field shape: medium confidence, manual text_source, csv_row provenance.
    f1 = f["1"]
    assert f1["confidence"] == "medium"
    assert f1["text_source"] == TEXT_SOURCE_MANUAL_W2
    assert f1["provenance"] == {"csv_row": 6}
    assert f1["csv_row"] == 6
    # Unused optional boxes stay absent.
    assert "12c" not in f and "12d" not in f
    assert "13_statutory" not in f and "13_sick" not in f
    assert "14_2" not in f
    # Bronze: exact bytes, content-hash doc_id.
    import hashlib
    sha = hashlib.sha256(EXAMPLE.encode("utf-8")).hexdigest()
    assert res["doc_id"] == sha[:16]
    assert doc.source_sha256 == sha
    bronze = store.get_bronze(sha)
    assert bronze is not None
    assert res["superseded"] == []


@pytest.mark.parametrize("bad", ["52,345.67", "$100", "(5.00)", "52345.6",
                                 "52345.678", "-100.00", ""])
def test_bad_money_fails_loud(store, bad):
    text = MINIMAL.replace("1 Wages tips other compensation,52345.67",
                           f"1 Wages tips other compensation,{bad}")
    with pytest.raises(ValueError):
        _ingest(store, text)


def test_bad_box12_fails_loud(store):
    text = MINIMAL + "12a,D19500.00\n"
    with pytest.raises(ValueError):
        _ingest(store, text)


def test_unknown_label_fails_loud(store):
    with pytest.raises(ValueError, match="[Uu]nknown"):
        _ingest(store, MINIMAL + "99 Something new,1.00\n")


def test_missing_tax_year_fails_loud(store):
    text = "\n".join(l for l in MINIMAL.splitlines()
                    if not l.startswith("tax_year,"))
    with pytest.raises(ValueError, match="tax_year"):
        _ingest(store, text + "\n")


def test_missing_employer_name_fails_loud(store):
    text = "\n".join(l for l in MINIMAL.splitlines()
                    if not l.startswith("employer_name,"))
    with pytest.raises(ValueError, match="employer_name"):
        _ingest(store, text + "\n")


@pytest.mark.parametrize("bad_ein", ["123456789", "1-2345678", "12-345678",
                                     "AB-CDEFGHI", "12-34567890"])
def test_bad_ein_fails_loud(store, bad_ein):
    text = MINIMAL.replace("employer_ein,12-3456789",
                           f"employer_ein,{bad_ein}")
    with pytest.raises(ValueError, match="[Ee][Ii][Nn]"):
        _ingest(store, text)


def test_checkbox_value_yes_fails_loud(store):
    with pytest.raises(ValueError, match="[Cc]heckbox"):
        _ingest(store, MINIMAL + "13 Retirement plan,yes\n")


def test_blank_row_fails_loud(store):
    # Blank boxes are omitted, not written with a trailing colon.
    with pytest.raises(ValueError):
        _ingest(store, MINIMAL + "13 Retirement plan:,\n")


def test_duplicate_nonrepeatable_fails_loud(store):
    with pytest.raises(ValueError, match="[Dd]uplicate"):
        _ingest(store, MINIMAL + "1 Wages tips other compensation,1.00\n")


def test_repeatable_box14_and_box12(store):
    text = (MINIMAL
            + "14,First item 100.00\n"
            + "14,Second item 200.00\n"
            + "12a,D 100.00\n"
            + "12a,E 200.00\n")
    res = _ingest(store, text)
    f = store.get(res["doc_id"]).fields
    assert f["14"]["value"] == "First item 100.00"
    assert f["14_2"]["value"] == "Second item 200.00"
    assert f["12a"]["value"] == "D 100.00"
    assert f["12a_2"]["value"] == "E 200.00"


def test_reingest_identical_bytes_is_noop(store):
    res1 = _ingest(store, EXAMPLE)
    res2 = _ingest(store, EXAMPLE)
    assert res2 == {"duplicate_import": True, "doc_id": res1["doc_id"]}
    # Exactly one manual W-2 doc for the year.
    docs = [d for d in store.list(year=2024, form="W-2")
            if d.text_source == TEXT_SOURCE_MANUAL_W2]
    assert len(docs) == 1


def test_edited_file_supersedes_same_year_ein(store):
    res1 = _ingest(store, MINIMAL)
    edited = MINIMAL.replace("1 Wages tips other compensation,52345.67",
                             "1 Wages tips other compensation,52345.68")
    res2 = _ingest(store, edited)
    assert res2["doc_id"] != res1["doc_id"]
    assert res2["superseded"] == [res1["doc_id"]]
    old = store.get(res1["doc_id"])
    assert old.fields[SUPERSEDED_BY_KEY] == res2["doc_id"]
    # Old bytes kept for audit.
    assert store.get_bronze(old.source_sha256) is not None
    # Lookup skips the superseded doc.
    latest = latest_manual_w2_doc(store, 2024, "12-3456789")
    assert latest.doc_id == res2["doc_id"]
    assert latest.fields["1"]["value"] == "52345.68"
    # Re-ingesting the OLD bytes does not un-supersede.
    res3 = _ingest(store, MINIMAL)
    assert res3 == {"duplicate_import": True, "doc_id": res1["doc_id"]}
    assert latest_manual_w2_doc(store, 2024, "12-3456789").doc_id == \
        res2["doc_id"]


def test_different_ein_does_not_supersede(store):
    res1 = _ingest(store, MINIMAL)
    other = MINIMAL.replace("employer_ein,12-3456789",
                            "employer_ein,98-7654321")
    res2 = _ingest(store, other)
    assert res2["superseded"] == []
    assert latest_manual_w2_doc(store, 2024, "12-3456789").doc_id == \
        res1["doc_id"]
    assert latest_manual_w2_doc(store, 2024, "98-7654321").doc_id == \
        res2["doc_id"]


def test_omitted_optional_rows_have_no_phantom_fields(store):
    res = _ingest(store, MINIMAL)
    f = store.get(res["doc_id"]).fields
    for phantom in ("12a", "12b", "12c", "12d", "13_statutory",
                    "13_retirement", "13_sick", "14", "14_2",
                    "15_state", "16", "17"):
        assert phantom not in f, phantom
    # Required keys are all present.
    for key in ("1", "2", "3", "4", "5", "6", "employer_name",
                "employer_ein", "tax_year"):
        assert key in f, key


def test_source_error_rows_kept_as_audit_notes(store):
    text = MINIMAL + "! Form shows a corrected box 1 on the reissue\n"
    res = _ingest(store, text)
    notes = store.get(res["doc_id"]).fields[AUDIT_NOTES_KEY]
    assert len(notes) == 1
    assert notes[0]["kind"] == "source_error"
    assert "corrected box 1" in notes[0]["text"]
    # Audit notes never become fields.
    assert all("corrected" not in str(v.get("value", ""))
               for k, v in store.get(res["doc_id"]).fields.items()
               if isinstance(v, dict) and k != AUDIT_NOTES_KEY)


def test_case_insensitive_collapsed_labels(store):
    text = MINIMAL.replace("1 Wages tips other compensation,52345.67",
                           "1  wages   TIPS other Compensation,52345.67")
    res = _ingest(store, text)
    assert store.get(res["doc_id"]).fields["1"]["value"] == "52345.67"


def test_machine_w2_docs_not_touched_by_supersede(store):
    # A machine-extracted W-2 with the same year/ein is a different
    # source; manual ingest must not supersede it.
    from taxprep.models import Document
    machine = Document(
        doc_id="machine-w2-1", tax_year=2024, form_type="W-2",
        source_path="/synthetic/w2.pdf", ocr_text_ref="",
        fields={"1": {"value": "1.00"}, "employer_ein": {"value": "12-3456789"}},
        text_source="native", status="needs_review")
    store.upsert(machine)
    res = _ingest(store, MINIMAL)
    assert res["superseded"] == []
    assert SUPERSEDED_BY_KEY not in store.get("machine-w2-1").fields
