"""R18 content-vs-filename classification (R23 stream E).

All fixtures synthetic; results asserted PII-free (doc_ids and form
labels only, never values). The check NEVER auto-reclassifies -- every
test also asserts the stored doc's form_type is untouched.
"""

from taxprep.models import Document
from taxprep.store import DocumentStore
from taxprep import verify as V


def _field(value, confidence="high", raw=""):
    return {"value": value, "confidence": confidence, "raw_text": raw}


def _store(tmp_path):
    return DocumentStore(tmp_path / "data")


def _upsert(store, doc_id, form_type, fields, ocr_text, source_path):
    d = Document(doc_id=doc_id, tax_year=2023, form_type=form_type,
                 source_path=source_path,
                 ocr_text_ref=f"ocr/{doc_id}.txt",
                 fields=fields, status="transcribed")
    store.save_ocr(doc_id, ocr_text)
    store.upsert(d)
    return d


def _pii_free(obj):
    """Blind-orchestrator assertion: no value/raw_text keys, no money."""
    import re
    if isinstance(obj, dict):
        for k, v in obj.items():
            assert k not in ("value", "raw_text"), f"PII key leaked: {k!r}"
            _pii_free(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _pii_free(v)
    elif isinstance(obj, str):
        assert not re.search(r"\$\d", obj), f"money leaked: {obj!r}"


# -- the "ALSO NOTED" shape: filed as ACCOUNT_TRANSCRIPT, content is ROA --
_ROA_OCR = "\n".join([
    "RECORD OF ACCOUNT",
    "TAX RETURN TRANSCRIPT",
    "ADJUSTED GROSS INCOME .......... $52,000.00",
    "TAXABLE INCOME ................. $40,000.00",
    "150 Tax return filed 04-15-2024 $1,234.00",
    "TAX ACCOUNT TRANSCRIPT",
    "ACCOUNT BALANCE ................ $200.00",
    "ACCRUED INTEREST ............... $12.34",
])

_ROA_FIELDS = {
    "agi": _field("52000.00"),
    "taxable_income": _field("40000.00"),
    "total_tax": _field("6100.00"),
    "withholding": _field("5900.00"),
    "refund": _field("0.00"),
    "account_balance": _field("200.00"),
    "accrued_interest": _field("12.34"),
    "tc_150": _field("1234.00"),
    "tc_806": _field("-1000.00"),
}


def test_content_mismatch_roa_filed_as_account(tmp_path):
    """The spec's real-world shape: filename hint agrees with the
    (wrong) form_type, but the label profile is decisively ROA --
    classification by content wins, raised to the Operator."""
    store = _store(tmp_path)
    _upsert(store, "roa1", "ACCOUNT_TRANSCRIPT", _ROA_FIELDS, _ROA_OCR,
            "account_transcript_2023.pdf")
    r = V.verify_type_hint_mismatch(store, 2023)
    assert r["passed"] is False
    assert r["mismatched"] == [{
        "doc_id": "roa1",
        "hint": "ACCOUNT_TRANSCRIPT",   # filename agrees with form_type
        "form_type": "ACCOUNT_TRANSCRIPT",
        "content_type": "RECORD_OF_ACCOUNT",
        "overlap": 1.0,                # every label shape is ROA-explained
    }]
    _pii_free(r)
    # never auto-reclassifies: the stored doc is untouched
    assert store.get("roa1").form_type == "ACCOUNT_TRANSCRIPT"


def test_genuine_account_transcript_no_mismatch(tmp_path):
    """A real account transcript saturates the small account vocabulary;
    ROA explains no more, so the tie resolves to the declared type."""
    store = _store(tmp_path)
    fields = {
        "account_balance": _field("0.00"),
        "accrued_interest": _field("0.00"),
        "accrued_penalty": _field("0.00"),
        "tc_150": _field("1234.00"),
    }
    ocr = "\n".join([
        "TAX ACCOUNT TRANSCRIPT",
        "ACCOUNT BALANCE: $0.00",
        "ACCRUED INTEREST: $0.00 as of 09/22/2025",
        "ACCRUED PENALTY: $0.00 as of 09/22/2025",
        "150 Tax return filed 04-15-2024 $1,234.00",
    ])
    _upsert(store, "acct1", "ACCOUNT_TRANSCRIPT", fields, ocr,
            "tax_account_transcript_2023.pdf")
    r = V.verify_type_hint_mismatch(store, 2023)
    assert r["passed"] is True
    assert r["mismatched"] == []
    _pii_free(r)


def test_thin_margin_no_mismatch_deterministic(tmp_path):
    """A genuine return transcript carries TC lines, so ROA explains one
    label more than RETURN -- but the margin is thin, so nothing is
    raised. Deterministic across repeated runs."""
    store = _store(tmp_path)
    fields = {
        "agi": _field("52000.00"),
        "taxable_income": _field("40000.00"),
        "total_tax": _field("6100.00"),
        "withholding": _field("5900.00"),
        "refund": _field("0.00"),
        "wages": _field("60000.00"),
        "tc_150": _field("1234.00"),
        "tc_806": _field("-1000.00"),
    }
    ocr = "\n".join([
        "TAX RETURN TRANSCRIPT",
        "ADJUSTED GROSS INCOME .......... $52,000.00",
        "WAGES, SALARIES, TIPS, ETC. .... $60,000.00",
        "150 Tax return filed 04-15-2024 $1,234.00",
        "806 Withholding credit 04-15-2024 $1,000.00",
    ])
    _upsert(store, "ret1", "RETURN_TRANSCRIPT", fields, ocr,
            "return_transcript_2023.pdf")
    r1 = V.verify_type_hint_mismatch(store, 2023)
    r2 = V.verify_type_hint_mismatch(store, 2023)
    assert r1 == r2  # deterministic
    assert r1["passed"] is True
    assert r1["mismatched"] == []
    _pii_free(r1)


def test_filename_hint_behavior_unchanged(tmp_path):
    """The historic filename-hint signal keeps its exact entry shape
    (no content_type key) when the content agrees with form_type."""
    store = _store(tmp_path)
    fields = {
        "agi": _field("52000.00"),
        "taxable_income": _field("40000.00"),
        "total_tax": _field("6100.00"),
        "withholding": _field("5900.00"),
        "refund": _field("0.00"),
    }
    ocr = "\n".join([
        "TAX RETURN TRANSCRIPT",
        "ADJUSTED GROSS INCOME .......... $52,000.00",
    ])
    _upsert(store, "fn1", "RETURN_TRANSCRIPT", fields, ocr,
            "account_transcript_2023.pdf")
    r = V.verify_type_hint_mismatch(store, 2023)
    assert r["passed"] is False
    assert r["mismatched"] == [{
        "doc_id": "fn1",
        "hint": "ACCOUNT_TRANSCRIPT",
        "form_type": "RETURN_TRANSCRIPT",
    }]
    _pii_free(r)
    assert store.get("fn1").form_type == "RETURN_TRANSCRIPT"
