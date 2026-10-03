"""Transcript parser tests — all fixtures synthetic."""

from taxprep.transcript import parse_return_transcript, parse_wage_income_transcript

RETURN_TRANSCRIPT = """TAX RETURN TRANSCRIPT
Tax Year: 2024
Filing Status: Single
Adjusted Gross Income: $85,420.00
Taxable Income: $71,220.00
Total Tax: $12,340.00
Federal Income Tax Withheld: $12,340.00
Estimated Tax Payments: $0.00
150 Tax return filed 04-15-2025 $12,340.00
806 W-2 or 1099 withholding 04-15-2025 $12,340.00
Some unrecognized footer line 999
"""

RETURN_TRANSCRIPT_REFUND = """TAX RETURN TRANSCRIPT
Tax Period: 2023
AGI: $50,000.00
Withholding: $6,000.00
Refund: $1,200.00
"""


def test_return_transcript_lines():
    r = parse_return_transcript(RETURN_TRANSCRIPT)
    assert r["tax_year"] == 2024
    assert r["lines"]["agi"] == 85420.0
    assert r["lines"]["taxable_income"] == 71220.0
    assert r["lines"]["total_tax"] == 12340.0
    assert r["lines"]["withholding"] == 12340.0
    assert r["lines"]["filing_status"] == "Single"


def test_return_transcript_transactions():
    r = parse_return_transcript(RETURN_TRANSCRIPT)
    codes = {t["code"]: t for t in r["transactions"]}
    assert codes["150"]["amount"] == 12340.0
    assert codes["150"]["date"] == "04-15-2025"
    assert codes["806"]["amount"] == 12340.0


def test_return_transcript_unparsed_kept():
    r = parse_return_transcript(RETURN_TRANSCRIPT)
    assert any("unrecognized footer" in line for line in r["unparsed_lines"])
    # summary lines consumed by the parser must NOT appear as unparsed
    assert not any("Adjusted Gross Income" in line for line in r["unparsed_lines"])


def test_return_transcript_variant_labels():
    r = parse_return_transcript(RETURN_TRANSCRIPT_REFUND)
    assert r["tax_year"] == 2023
    assert r["lines"]["agi"] == 50000.0
    assert r["lines"]["withholding"] == 6000.0
    assert r["lines"]["refund"] == 1200.0


WAGE_INCOME = """WAGE AND INCOME TRANSCRIPT Tax Year 2024
Payer: ACME CORPORATION 12-3456789
Form W-2
Box 1 Wages: $85,000.00
Box 2 Withheld: $12,340.00
Payer: EXAMPLE BANK
Form 1099-INT
Box 1 Interest: $420.50
random stray line here
"""

WAGE_INCOME_FORM_FIRST = """WAGE AND INCOME TRANSCRIPT
Form W-2
Payer: ACME CORPORATION 12-3456789
Box 1 Wages: $85,000.00
"""


def test_wage_income_payer_first_layout():
    w = parse_wage_income_transcript(WAGE_INCOME)
    assert w["tax_year"] == 2024
    assert len(w["payers"]) == 2
    p1, p2 = w["payers"]
    assert p1["payer"] == "ACME CORPORATION"
    assert p1["payer_ein"] == "12-3456789"
    assert p1["form_type"] == "W-2"
    assert p1["boxes"]["1"] == 85000.0
    assert p1["boxes"]["2"] == 12340.0
    assert p2["payer"] == "EXAMPLE BANK"
    assert p2["form_type"] == "1099-INT"
    assert p2["boxes"]["1"] == 420.50


def test_wage_income_form_first_layout():
    w = parse_wage_income_transcript(WAGE_INCOME_FORM_FIRST)
    assert len(w["payers"]) == 1
    p = w["payers"][0]
    assert p["payer"] == "ACME CORPORATION"
    assert p["form_type"] == "W-2"
    assert p["boxes"]["1"] == 85000.0


def test_wage_income_unparsed_kept():
    w = parse_wage_income_transcript(WAGE_INCOME)
    assert any("stray line" in line for line in w["unparsed_lines"])
