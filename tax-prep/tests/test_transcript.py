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


# ---------------------------------------------------------------------------
# D4: exact-label table -- longest/most-specific wins, never
# first-match-wins on substrings. All fixtures synthetic.
# ---------------------------------------------------------------------------

D4_PAYMENTS = "Total Tax Payments: $5,000.00"
D4_LIABILITY = "Total Tax Liability: $12,340.00"
D4_SS_WITHHELD = "Social Security Tax Withheld: $3,100.00"
D4_FED_WITHHELD = "Federal Income Tax Withheld: $12,340.00"


def _d4_transcript(*summary_lines):
    return "TAX RETURN TRANSCRIPT\nTax Year: 2024\n" + "\n".join(summary_lines) + "\n"


def test_label_order_payments_before_liability():
    r = parse_return_transcript(
        _d4_transcript(D4_PAYMENTS, D4_LIABILITY))
    assert r["lines"]["total_tax"] == 12340.0
    assert r["lines"]["total_payments"] == 5000.0
    assert not r["unparsed_lines"]


def test_label_order_liability_before_payments():
    r = parse_return_transcript(
        _d4_transcript(D4_LIABILITY, D4_PAYMENTS))
    assert r["lines"]["total_tax"] == 12340.0
    assert r["lines"]["total_payments"] == 5000.0
    assert not r["unparsed_lines"]


def test_withholding_ss_before_federal():
    r = parse_return_transcript(
        _d4_transcript(D4_SS_WITHHELD, D4_FED_WITHHELD))
    assert r["lines"]["withholding"] == 12340.0
    assert r["lines"]["ss_tax_withheld"] == 3100.0


def test_withholding_federal_before_ss():
    r = parse_return_transcript(
        _d4_transcript(D4_FED_WITHHELD, D4_SS_WITHHELD))
    assert r["lines"]["withholding"] == 12340.0
    assert r["lines"]["ss_tax_withheld"] == 3100.0


EXTENDED_VOCAB_TRANSCRIPT = """TAX RETURN TRANSCRIPT
Tax Year: 2023
Filing Status: Married Filing Jointly
Wages, Salaries, Tips, Etc.: $120,000.00
Taxable Interest: $1,250.50
Ordinary Dividends: $3,400.00
Capital Gain or (Loss): ($2,500.00)
Short-Term Capital Gain or (Loss): ($1,000.00)
Long-Term Capital Gain or (Loss): ($1,500.00)
Short-Term Capital Loss Carryover: ($4,000.00)
Long-Term Capital Loss Carryover: ($6,000.00)
Adjusted Gross Income: $115,000.00
Taxable Income: $90,000.00
Total Tax: $15,000.00
Federal Income Tax Withheld: $14,000.00
Estimated Tax Payments: $2,000.00
Total Payments: $16,000.00
Refund Amount: $1,000.00
Number of Exemptions: 2
"""


def test_extended_vocabulary_keys():
    r = parse_return_transcript(EXTENDED_VOCAB_TRANSCRIPT)
    assert r["tax_year"] == 2023
    assert r["lines"]["wages"] == 120000.0
    assert r["lines"]["taxable_interest"] == 1250.50
    assert r["lines"]["ordinary_dividends"] == 3400.0
    assert r["lines"]["capital_gain_loss"] == -2500.0
    assert r["lines"]["short_term_gain_loss"] == -1000.0
    assert r["lines"]["long_term_gain_loss"] == -1500.0
    assert r["lines"]["short_term_carryover"] == -4000.0
    assert r["lines"]["long_term_carryover"] == -6000.0
    assert r["lines"]["agi"] == 115000.0
    assert r["lines"]["taxable_income"] == 90000.0
    assert r["lines"]["total_tax"] == 15000.0
    assert r["lines"]["withholding"] == 14000.0
    assert r["lines"]["estimated_payments"] == 2000.0
    assert r["lines"]["total_payments"] == 16000.0
    assert r["lines"]["refund"] == 1000.0
    assert r["lines"]["exemptions"] == 2
    assert r["lines"]["filing_status"] == "Married Filing Jointly"
    assert not r["unparsed_lines"]


def test_label_table_has_no_conflicting_duplicates():
    import taxprep.transcript as tr
    seen = {}
    for label, key in tr._RETURN_LABEL_TABLE:
        # table entries must be pre-normalized
        assert label == label.strip().upper()
        assert "  " not in label
        if label in seen:
            assert seen[label] == key, f"conflicting duplicate: {label}"
        seen[label] = key


def test_ambiguous_line_leaves_field_unset(monkeypatch):
    import taxprep.transcript as tr
    # a line matching several table entries with different keys
    conflicted = list(tr._RETURN_LABEL_TABLE) + [("TOTAL TAX", "withholding")]
    monkeypatch.setattr(tr, "_RETURN_LABEL_TABLE", conflicted)
    r = parse_return_transcript(_d4_transcript("Total Tax: $5,000.00"))
    assert "total_tax" not in r["lines"]
    assert "withholding" not in r["lines"]
    assert any(line.startswith("AMBIGUOUS: ") and "Total Tax" in line
               for line in r["unparsed_lines"])


def test_duplicate_key_first_wins_and_visible():
    r = parse_return_transcript(
        _d4_transcript("Total Tax: $1.00", "Total Tax: $2.00"))
    assert r["lines"]["total_tax"] == 1.0
    assert any(line.startswith("DUPLICATE total_tax: ")
               for line in r["unparsed_lines"])


def test_line_raw_text_is_verbatim():
    r = parse_return_transcript(RETURN_TRANSCRIPT)
    assert r["line_raw_text"]["agi"] == "Adjusted Gross Income: $85,420.00"
    assert r["line_raw_text"]["filing_status"] == "Filing Status: Single"
    assert set(r["line_raw_text"]) == set(r["lines"])


def test_leading_whitespace_line_maps_and_keeps_verbatim():
    r = parse_return_transcript(
        _d4_transcript("   Total Tax: $12,340.00"))
    assert r["lines"]["total_tax"] == 12340.0
    assert r["line_raw_text"]["total_tax"] == "   Total Tax: $12,340.00"


D4_MESSY_TRANSCRIPT = """TAX RETURN TRANSCRIPT
Tax Year: 2024

Filing Status:   Married Filing Jointly
   Total Tax: $12,340.00
total tax payments: $5,000.00
WAGES, SALARIES, TIPS, ETC.: $85,000.00
Capital Gain or (Loss): ($3,000.00)
SHORT-TERM CAPITAL LOSS CARRYOVER: ($4,000.00)
LONG-TERM CAPITAL LOSS CARRYOVER: ($6,000.00)
agi: $50,000.00
AGI: $51,000.00
Total Tax: $9,999.00
Total Tax:
Some total mystery line 123
150 Tax return filed 04-15-2025 $12,340.00
Random footer junk
"""


def test_fuzz_every_line_accounted():
    """Every non-blank, non-structural, non-transaction line is either
    mapped (verbatim raw line recorded) or listed in unparsed_lines."""
    import taxprep.transcript as tr
    r = parse_return_transcript(D4_MESSY_TRANSCRIPT)
    mapped_raws = list(r["line_raw_text"].values())
    unparsed = r["unparsed_lines"]
    eligible = [raw for raw in D4_MESSY_TRANSCRIPT.splitlines()
                if raw.strip()
                and not tr._is_structural(raw)
                and not tr._is_structural(
                    tr._LEADING_YEAR_RE.sub("", tr._normalize_line(raw)))
                and not tr._TRANSACTION_CODE_RE.match(raw)]
    assert len(mapped_raws) + len(unparsed) == len(eligible)
    for raw in eligible:
        assert (raw in mapped_raws or raw in unparsed
                or any(u != raw and u.endswith(raw) for u in unparsed)), raw
    # spot-check the interesting outcomes
    assert r["lines"]["total_tax"] == 12340.0      # keep-first
    assert r["lines"]["total_payments"] == 5000.0  # lowercase label still maps
    assert r["lines"]["agi"] == 50000.0            # keep-first
    assert r["lines"]["wages"] == 85000.0
    assert r["lines"]["capital_gain_loss"] == -3000.0
    assert any(u.startswith("DUPLICATE agi: ") for u in unparsed)
    assert any(u.startswith("DUPLICATE total_tax: ") for u in unparsed)
    assert "Total Tax:" in unparsed  # label recognized, no usable value
    assert "Some total mystery line 123" in unparsed
    assert "Random footer junk" in unparsed
