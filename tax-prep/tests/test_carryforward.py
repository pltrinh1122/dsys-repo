"""Carryforward engine tests -- all amounts synthetic."""

from decimal import Decimal

import pytest

from taxprep.carryforward import compute_chain, compute_year, from_store
from taxprep.models import Document
from taxprep.store import DocumentStore

D = Decimal


def b1099(doc_id, year, proceeds, basis, term, status="validated"):
    return Document(
        doc_id=doc_id,
        tax_year=year,
        form_type="1099-B",
        source_path=f"{doc_id}.pdf",
        ocr_text_ref=f"ocr/{doc_id}.txt",
        fields={
            "1d_proceeds": {"value": proceeds, "confidence": "high", "raw_text": ""},
            "1e_basis": {"value": basis, "confidence": "high", "raw_text": ""},
            "term": {"value": term, "confidence": "high", "raw_text": ""},
            "broker": {"value": "Synthetic Broker", "confidence": "high", "raw_text": ""},
        },
        status=status,
    )


# (a) pure ST loss 9000, single -> deductible 3000, ST carry 6000
def test_pure_st_loss_single():
    r = compute_year(D(0), D(0), D("-9000"), D(0), "single")
    assert r["deductible_loss"] == D("3000")
    assert r["st_carry_out"] == D("6000")
    assert r["lt_carry_out"] == D("0")
    assert r["st_net"] == D("-9000")


# (b) chain: 2024 adds ST loss 1000 -> carry 4000 to 2025
def test_chain_two_years():
    res = compute_chain(
        {
            2023: {"st_current": D("-9000"), "lt_current": D(0)},
            2024: {"st_current": D("-1000"), "lt_current": D(0)},
        },
        {2023: "single", 2024: "single"},
    )
    assert res["years"][2023]["st_carry_out"] == D("6000")
    assert res["years"][2024]["st_carry_in"] == D("6000")
    assert res["years"][2024]["st_net"] == D("-7000")
    assert res["years"][2024]["deductible_loss"] == D("3000")
    assert res["years"][2024]["st_carry_out"] == D("4000")


# (c) mixed: ST gain 5000 + LT loss 12000 -> worksheet: line 7 = +5000
# gain, line 15 = -12000 loss, line 16 = -7000, deduction 3000.
# L9=12000, L10=5000, L11=3000, L12=8000 -> LT carry 4000, ST carry 0.
def test_mixed_gain_loss():
    r = compute_year(D(0), D(0), D("5000"), D("-12000"), "single")
    assert r["deductible_loss"] == D("3000")
    assert r["lt_carry_out"] == D("4000")
    assert r["st_carry_out"] == D("0")


# Mixed with carry-in: ST pool 7000 loss, LT gain 5000 -> the LT gain
# absorbs ST loss on worksheet line 6 before any carryover is figured:
# L5=7000, L6=5000, L7=2000+5000=7000 -> ST carry 0 (not 5000).
def test_mixed_cross_term_absorption():
    r = compute_year(D("6000"), D(0), D("-1000"), D("5000"), "single")
    assert r["deductible_loss"] == D("2000")
    assert r["st_carry_out"] == D("0")
    assert r["lt_carry_out"] == D("0")
    assert r["worksheet_lines"]["L6_lt_gain"] == D("5000")


# (d) loss fully absorbed by gains -> zero carry-out
def test_loss_absorbed_by_gains():
    r = compute_year(D(0), D(0), D("-2000"), D("5000"), "single")
    assert r["deductible_loss"] == D("0")
    assert r["st_carry_out"] == D("0")
    assert r["lt_carry_out"] == D("0")


# invariant: net gain across terms -> nothing deducted, nothing carried,
# even when a single term's loss exceeds the annual limit
def test_invariant_net_gain_large_term_loss():
    r = compute_year(D(0), D(0), D("-5000"), D("6000"), "single")
    assert r["deductible_loss"] == D("0")
    assert r["st_carry_out"] == D("0")
    assert r["lt_carry_out"] == D("0")


# (e) MFS limit 1500
def test_mfs_limit():
    r = compute_year(D(0), D(0), D("-9000"), D(0), "mfs")
    assert r["deductible_loss"] == D("1500")
    assert r["st_carry_out"] == D("7500")


# (f) Decimal exactness: no float artifacts; floats rejected loudly
def test_decimal_exactness():
    r = compute_year(D("0"), D("0"), D("-1234.56"), D("-0.07"), "single")
    assert r["st_net"] == D("-1234.56")
    assert r["deductible_loss"] == D("1234.63")
    assert r["st_carry_out"] == D("0")
    assert r["lt_carry_out"] == D("0")
    # 0.1 + 0.2 style artifacts must not appear
    r2 = compute_year(D("0.10"), D("0.20"), D("-0.30"), D("0"), "single")
    assert r2["st_net"] == D("-0.40")
    assert r2["deductible_loss"] == D("0.60")


def test_float_rejected():
    with pytest.raises(TypeError, match="float"):
        compute_year(0.1, 0, 0, 0, "single")


def test_unknown_status_rejected():
    with pytest.raises(ValueError, match="filing_status"):
        compute_year(D(0), D(0), D("-100"), D(0), "not-a-status")


# (g) from_store refuses on unvalidated docs
def test_from_store_refuses_unvalidated(tmp_path):
    store = DocumentStore(tmp_path / "data")
    store.upsert(b1099("b1", 2024, "1000.00", "1500.00", "short",
                       status="transcribed"))
    with pytest.raises(ValueError, match="not yet validated"):
        from_store(store, 2024)


def test_from_store_sums_and_excludes_unknown_term(tmp_path):
    store = DocumentStore(tmp_path / "data")
    store.upsert(b1099("b1", 2024, "1,000.00", "1,500.00", "short"))   # -500 ST
    store.upsert(b1099("b2", 2024, "2,000.00", "1,200.00", "long"))    # +800 LT
    store.upsert(b1099("b3", 2024, "500.00", "400.00", None))          # unknown term
    r = from_store(store, 2024)
    assert r["st_current"] == D("-500")
    assert r["lt_current"] == D("800")
    assert r["lots_included"] == 2
    assert r["lots_excluded"] == 1
    assert any("unknown" in w for w in r["warnings"])


def test_from_store_empty_year_is_zero(tmp_path):
    store = DocumentStore(tmp_path / "data")
    r = from_store(store, 2025)
    assert r["st_current"] == D("0") and r["lt_current"] == D("0")


def test_chain_into_2026_and_table(tmp_path):
    res = compute_chain(
        {
            2023: {"st_current": D("-9000"), "lt_current": D(0)},
            2024: {"st_current": D("-1000"), "lt_current": D(0)},
            2025: {"st_current": D("0"), "lt_current": D("0")},
        },
        {2023: "single", 2024: "single", 2025: "single"},
    )
    assert res["carryforward_into_2026"] == {"st": D("1000"), "lt": D("0")}
    assert "Carryforward into 2026" in res["table"]
    assert "2023" in res["table"] and "2025" in res["table"]


def test_prior_carryover_seeds_first_year():
    res = compute_chain(
        {2023: {"st_current": D("0"), "lt_current": D("0")}},
        {2023: "single"},
        prior_carryover={"st": D("4500"), "lt": D("0")},
    )
    r = res["years"][2023]
    assert r["st_carry_in"] == D("4500")
    assert r["deductible_loss"] == D("3000")
    assert r["st_carry_out"] == D("1500")


def test_flags_produce_warnings():
    r = compute_year(D(0), D(0), D("-9000"), D(0), "single",
                     flags={"unrecaptured_1250": True, "collectibles": False})
    assert any("1250" in w for w in r["warnings"])
    assert any("taxable income not supplied" in w for w in r["warnings"])


def test_taxable_income_limits_used_deduction():
    # Would-be negative taxable income: L1=(2000), L2=3000, L3=1000,
    # L4=1000 -> only 1000 of the deduction was used -> ST carry 8000.
    r = compute_year(D(0), D(0), D("-9000"), D(0), "single",
                     taxable_income=D("-2000"))
    assert r["worksheet_lines"]["L4_used_deduction"] == D("1000")
    assert r["st_carry_out"] == D("8000")
    assert not any("taxable income not supplied" in w for w in r["warnings"])


def test_taxable_income_none_warns():
    r = compute_year(D(0), D(0), D("-9000"), D(0), "single")
    assert any("taxable income not supplied" in w for w in r["warnings"])
    # assumption path: L4 = L2
    assert r["worksheet_lines"]["L4_used_deduction"] == D("3000")
