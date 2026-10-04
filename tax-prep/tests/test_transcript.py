"""Transcript parser tests — all fixtures synthetic."""

import pytest

from taxprep.transcript import parse_return_transcript, parse_wage_income_transcript

RETURN_TRANSCRIPT = """TAX RETURN TRANSCRIPT
Tax Year: 2024
Tax Period Ending: Dec. 31, 2024
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
Tax Period Ending: Dec. 31, 2023
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
    # D5: every generated fixture carries the tax-period header line,
    # so a header->total_tax regression fails loudly here first.
    return ("TAX RETURN TRANSCRIPT\nTax Year: 2024\n"
            "Tax Period Ending: Dec. 31, 2024\n"
            + "\n".join(summary_lines) + "\n")


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
Tax Period Ending: Dec. 31, 2023
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
Tax Period Ending: Dec. 31, 2024

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


# ---------------------------------------------------------------------------
# D5: header lines are never label-matched; date digits are never
# money. Workstation probes, verbatim. All fixtures synthetic.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("probe", [
    "Tax Period Ending: Dec. 31, 2024",
    "TAX PERIOD ENDING: Dec. 31, 2024",
])
def test_d5_period_header_never_total_tax(probe):
    r = parse_return_transcript(
        "TAX RETURN TRANSCRIPT\nTax Year: 2024\n" + probe + "\n")
    assert "total_tax" not in r["lines"], probe
    # structural: consumed, not unparsed and not mapped
    assert probe not in r["unparsed_lines"], probe
    assert r["tax_year"] == 2024


def test_d5_period_header_split_across_lines():
    r = parse_return_transcript(
        "TAX RETURN TRANSCRIPT\nTax Year: 2024\n"
        "Tax Period Ending:\n12-31-2024\n")
    assert "total_tax" not in r["lines"]
    # the dateline has no label: visible in unparsed, never money
    assert "12-31-2024" in r["unparsed_lines"]


def test_d5_real_total_tax_line_still_maps_with_header_present():
    # the audit's live case: a real TOTAL TAX LIABILITY line must win
    # over the header line
    r = parse_return_transcript(
        "TAX RETURN TRANSCRIPT\nTax Year: 2024\n"
        "Tax Period Ending: Dec. 31, 2024\n"
        "Total Tax Liability: $12,340.00\n")
    assert r["lines"]["total_tax"] == 12340.0
    assert not any("Period Ending" in u for u in r["unparsed_lines"])


def test_d5_summary_value_ignores_date_digits():
    import taxprep.transcript as tr
    # before the fix the day number read as money
    assert tr._summary_value(
        "Total Tax: Dec. 31, 2024", "total_tax", "TOTAL TAX") is None
    assert tr._summary_value(
        "Total Tax: 12-31-2024", "total_tax", "TOTAL TAX") is None
    # a real amount next to a date still extracts
    assert tr._summary_value(
        "Total Tax: $5,000.00 as of Dec. 31, 2024",
        "total_tax", "TOTAL TAX") == 5000.0


# ---------------------------------------------------------------------------
# R17: account transcript + record of account. All fixtures synthetic.
# ---------------------------------------------------------------------------

from decimal import Decimal

from taxprep.transcript import (
    parse_account_transcript,
    parse_record_of_account,
    parse_return_transcript as _parse_return_transcript,
)

ACCOUNT_TRANSCRIPT = """TAX ACCOUNT TRANSCRIPT
Tax Year: 2024
Account Balance: $1,234.56
Accrued Interest: $12.34 as of 09/22/2025
Accrued Penalty: $0.00 as of 09/22/2025
150 Tax return filed 20241205 04-15-2025 $1,234.56
806 W-2 or 1099 withholding 20241205 04-15-2025 $1,000.00
290 Additional tax assessed 20241803 06-02-2025 $150.00
291 Reduction of tax 20242004 07-14-2025 $50.00
971 Notice issued 20242505 08-01-2025
977 Amended return filed 20243006 09-10-2025
766 Credit to your account 20241205 04-15-2025 $200.00
768 Earned income credit 20241205 04-15-2025 $300.00
846 Refund issued 20243207 10-05-2025 $384.56
Some unrecognized account footer
"""

ACCOUNT_TRANSCRIPT_AS_OF_FIRST = """TAX ACCOUNT TRANSCRIPT
Tax Period: 2023
Accrued interest as of 09/22/2024: $45.67
Accrued penalty as of 09/22/2024: ($10.00)
Account Balance: $500.00
"""


def test_account_transcript_exact_shape():
    r = parse_account_transcript(ACCOUNT_TRANSCRIPT)
    assert set(r) == {"lines", "line_raw_text", "transactions",
                      "unparsed_lines"}


def test_account_transcript_lines_decimal_safe():
    r = parse_account_transcript(ACCOUNT_TRANSCRIPT)
    assert r["lines"]["account_balance"] == "1234.56"
    assert r["lines"]["accrued_interest"] == "12.34"
    assert r["lines"]["accrued_penalty"] == "0.00"
    # Decimal-safe strings: exact digits, never floated
    for v in r["lines"].values():
        assert isinstance(v, str)
        Decimal(v)
    # R15: verbatim evidence per mapped key
    assert r["line_raw_text"]["account_balance"] == \
        "Account Balance: $1,234.56"
    assert set(r["line_raw_text"]) == set(r["lines"])


def test_account_transcript_as_of_first_layout():
    # "Accrued interest as of <date>:" -- prefix-match layout
    r = parse_account_transcript(ACCOUNT_TRANSCRIPT_AS_OF_FIRST)
    assert r["lines"]["accrued_interest"] == "45.67"
    assert r["lines"]["accrued_penalty"] == "-10.00"
    assert r["lines"]["account_balance"] == "500.00"
    assert not r["unparsed_lines"]


def test_account_transcript_transactions_all_code_families():
    r = parse_account_transcript(ACCOUNT_TRANSCRIPT)
    by_code = {t["code"]: t for t in r["transactions"]}
    assert set(by_code) == {"150", "806", "290", "291", "971", "977",
                            "766", "768", "846"}
    t150 = by_code["150"]
    assert t150["description"] == "Tax return filed"
    assert t150["cycle"] == "20241205"
    assert t150["date"] == "04-15-2025"
    assert t150["amount"] == "1234.56"
    assert by_code["806"]["amount"] == "1000.00"
    assert by_code["290"]["amount"] == "150.00"
    assert by_code["291"]["amount"] == "50.00"
    assert by_code["766"]["amount"] == "200.00"
    assert by_code["768"]["amount"] == "300.00"
    assert by_code["846"]["cycle"] == "20243207"
    assert by_code["846"]["amount"] == "384.56"
    # amountless TC lines keep code/description/cycle/date, amount None
    assert by_code["971"]["description"] == "Notice issued"
    assert by_code["971"]["cycle"] == "20242505"
    assert by_code["971"]["date"] == "08-01-2025"
    assert by_code["971"]["amount"] is None
    assert by_code["977"]["amount"] is None
    # every transaction carries exactly the contract keys
    for t in r["transactions"]:
        assert set(t) == {"code", "description", "cycle", "date",
                          "amount"}


def test_account_transcript_unparsed_kept():
    r = parse_account_transcript(ACCOUNT_TRANSCRIPT)
    assert any("unrecognized account footer" in line
               for line in r["unparsed_lines"])
    assert not any("Account Balance" in line
                   for line in r["unparsed_lines"])


def test_account_label_table_has_no_conflicting_duplicates():
    import taxprep.transcript as tr
    seen = {}
    for label, key in tr._ACCOUNT_LABEL_TABLE:
        assert label == label.strip().upper()
        assert "  " not in label
        if label in seen:
            assert seen[label] == key, f"conflicting duplicate: {label}"
        seen[label] = key


def test_account_ambiguous_line_leaves_field_unset(monkeypatch):
    import taxprep.transcript as tr
    conflicted = list(tr._ACCOUNT_LABEL_TABLE) + [
        ("ACCOUNT BALANCE", "accrued_interest")]
    monkeypatch.setattr(tr, "_ACCOUNT_LABEL_TABLE", conflicted)
    r = parse_account_transcript("Account Balance: $5,000.00\n")
    assert "account_balance" not in r["lines"]
    assert "accrued_interest" not in r["lines"]
    assert any(line.startswith("AMBIGUOUS: ") and "Account Balance" in line
               for line in r["unparsed_lines"])


def test_account_duplicate_key_first_wins_and_visible():
    r = parse_account_transcript(
        "Account Balance: $1.00\nAccount Balance: $2.00\n")
    assert r["lines"]["account_balance"] == "1.00"
    assert any(line.startswith("DUPLICATE account_balance: ")
               for line in r["unparsed_lines"])


def test_account_fuzz_every_line_accounted():
    """Every non-blank, non-structural, non-transaction line is either
    mapped (verbatim raw line recorded) or listed in unparsed_lines."""
    import taxprep.transcript as tr
    messy = ("TAX ACCOUNT TRANSCRIPT\nTax Year: 2024\n"
             "Account Balance: $1,234.56\n"
             "account balance: $9.99\n"
             "Accrued Interest: $12.34 as of 09/22/2025\n"
             "Accrued Penalty:\n"
             "150 Tax return filed 20241205 04-15-2025 $1,234.56\n"
             "Random account junk\n")
    r = parse_account_transcript(messy)
    mapped_raws = list(r["line_raw_text"].values())
    unparsed = r["unparsed_lines"]
    eligible = [raw for raw in messy.splitlines()
                if raw.strip()
                and not tr._is_structural(raw)
                and not tr._is_structural(
                    tr._LEADING_YEAR_RE.sub("", tr._normalize_line(raw)))
                and not tr._TRANSACTION_CODE_RE.match(raw)]
    assert len(mapped_raws) + len(unparsed) == len(eligible)
    for raw in eligible:
        assert (raw in mapped_raws or raw in unparsed
                or any(u != raw and u.endswith(raw) for u in unparsed)), raw
    assert r["lines"]["account_balance"] == "1234.56"  # keep-first
    assert any(u.startswith("DUPLICATE account_balance: ")
               for u in unparsed)
    assert "Accrued Penalty:" in unparsed  # label known, no usable value
    assert "Random account junk" in unparsed


# ---------------------------------------------------------------------------
# Record of Account
# ---------------------------------------------------------------------------

ROA = """RECORD OF ACCOUNT
Tax Year: 2024
TAX RETURN TRANSCRIPT
Adjusted Gross Income: $85,420.00
Total Tax: $12,340.00
150 Tax return filed 04-15-2025 $12,340.00
806 W-2 or 1099 withholding 04-15-2025 $12,340.00
TAX ACCOUNT TRANSCRIPT
Account Balance: $0.00
Accrued Interest: $0.00 as of 09/22/2025
150 Tax return filed 20241205 04-15-2025 $12,340.00
846 Refund issued 20243207 10-05-2025 $0.00
"""

ROA_WITH_DOC_LEVEL_LINE = """RECORD OF ACCOUNT
Tax Year: 2024
Some cover-page notice
TAX RETURN TRANSCRIPT
Adjusted Gross Income: $85,420.00
TAX ACCOUNT TRANSCRIPT
Account Balance: $0.00
"""


def test_roa_exact_shape():
    r = parse_record_of_account(ROA)
    assert set(r) == {"return_section", "account_section",
                      "unparsed_lines"}
    assert r["unparsed_lines"] == []


def test_roa_sections_reuse_parsers():
    # the sections are parsed by the same functions on the section text
    lines = ROA.splitlines()
    acct_idx = next(i for i, line in enumerate(lines)
                    if line.strip().upper() == "TAX ACCOUNT TRANSCRIPT")
    ret_idx = next(i for i, line in enumerate(lines)
                   if line.strip().upper() == "TAX RETURN TRANSCRIPT")
    return_text = "\n".join(lines[ret_idx:acct_idx])
    account_text = "\n".join(lines[acct_idx:])
    r = parse_record_of_account(ROA)
    assert r["return_section"] == _parse_return_transcript(return_text)
    assert r["account_section"] == parse_account_transcript(account_text)


def test_roa_return_section_content():
    r = parse_record_of_account(ROA)
    sec = r["return_section"]
    assert sec["lines"]["agi"] == 85420.0
    assert sec["lines"]["total_tax"] == 12340.0
    assert {t["code"] for t in sec["transactions"]} == {"150", "806"}
    assert sec["unparsed_lines"] == []


def test_roa_account_section_content():
    r = parse_record_of_account(ROA)
    sec = r["account_section"]
    assert sec["lines"]["account_balance"] == "0.00"
    assert sec["lines"]["accrued_interest"] == "0.00"
    by_code = {t["code"]: t for t in sec["transactions"]}
    assert by_code["150"]["cycle"] == "20241205"
    assert by_code["846"]["amount"] == "0.00"


def test_roa_doc_level_lines_go_top_level():
    r = parse_record_of_account(ROA_WITH_DOC_LEVEL_LINE)
    assert r["unparsed_lines"] == ["Some cover-page notice"]
    # sections unaffected by the doc-level line
    assert r["return_section"]["lines"]["agi"] == 85420.0
    assert r["account_section"]["lines"]["account_balance"] == "0.00"


def test_roa_overlap_sanity_against_standalone_return():
    # the ROA's return section must match a standalone return transcript
    # of the same year carrying the same content
    standalone = ("TAX RETURN TRANSCRIPT\nTax Year: 2024\n"
                  "Adjusted Gross Income: $85,420.00\n"
                  "Total Tax: $12,340.00\n"
                  "150 Tax return filed 04-15-2025 $12,340.00\n"
                  "806 W-2 or 1099 withholding 04-15-2025 $12,340.00\n")
    r = parse_record_of_account(ROA, tax_year=2024)
    s = _parse_return_transcript(standalone, tax_year=2024)
    assert r["return_section"]["tax_year"] == s["tax_year"] == 2024
    assert r["return_section"]["lines"] == s["lines"]
    assert r["return_section"]["transactions"] == s["transactions"]


# ---------------------------------------------------------------------------
# Blind-orchestrator sweep over the new parser outputs: the shapes are
# metadata-only. Keys must come from the fixed contract vocabulary (R8:
# a name/value can only ever appear in a VALUE, never as a key); money
# may only appear inside verbatim evidence strings (line_raw_text /
# unparsed_lines), never in a description or key.
# ---------------------------------------------------------------------------

import re as _re

_MONEY_LEAK_RE = _re.compile(r"\$\d")

_ACCOUNT_TOP_KEYS = {"lines", "line_raw_text", "transactions",
                     "unparsed_lines"}
_ROA_TOP_KEYS = {"return_section", "account_section", "unparsed_lines"}
_TXN_KEYS = {"code", "description", "cycle", "date", "amount"}
_RETURN_LINE_VOCAB = {key for _, key in
                      __import__("taxprep.transcript",
                                 fromlist=["_RETURN_LABEL_TABLE"])
                      ._RETURN_LABEL_TABLE}
_ACCOUNT_LINE_VOCAB = {key for _, key in
                       __import__("taxprep.transcript",
                                  fromlist=["_ACCOUNT_LABEL_TABLE"])
                       ._ACCOUNT_LABEL_TABLE}


def _sweep_section(parsed, top_keys, line_vocab, txn_keys=_TXN_KEYS,
                   decimal_safe_amounts=True):
    assert set(parsed) == top_keys, set(parsed) ^ top_keys
    lines, raw = parsed["lines"], parsed["line_raw_text"]
    assert set(lines) <= line_vocab, set(lines) - line_vocab
    assert set(raw) == set(lines)  # R15: every mapped key has evidence
    for t in parsed["transactions"]:
        assert set(t) == txn_keys, set(t) ^ txn_keys
        assert not _MONEY_LEAK_RE.search(t["description"]), t
        amt = t["amount"]
        if amt is not None and decimal_safe_amounts:
            assert isinstance(amt, str), t
            Decimal(amt)  # Decimal-safe, never floated
        for v in (t["code"], t.get("cycle"), t["date"]):
            if v is not None:
                assert not _MONEY_LEAK_RE.search(v), t
    for u in parsed["unparsed_lines"]:
        assert isinstance(u, str)


def test_blind_sweep_account_parser_output():
    r = parse_account_transcript(ACCOUNT_TRANSCRIPT)
    _sweep_section(r, _ACCOUNT_TOP_KEYS, _ACCOUNT_LINE_VOCAB)


def test_blind_sweep_roa_parser_output():
    r = parse_record_of_account(ROA_WITH_DOC_LEVEL_LINE)
    assert set(r) == _ROA_TOP_KEYS
    _sweep_section(r["return_section"],
                   _ACCOUNT_TOP_KEYS | {"tax_year"}, _RETURN_LINE_VOCAB,
                   txn_keys={"code", "description", "date", "amount"},
                   decimal_safe_amounts=False)
    _sweep_section(r["account_section"], _ACCOUNT_TOP_KEYS,
                   _ACCOUNT_LINE_VOCAB)
    for u in r["unparsed_lines"]:
        assert isinstance(u, str)
