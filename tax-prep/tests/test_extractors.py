"""Extractor tests — all fixtures synthetic (fake names, EINs, amounts)."""

import pytest

from taxprep.extractors import classify_form, detect_tax_year, extract_fields


def field(fields, code):
    assert code in fields, f"missing box {code}"
    return fields[code]


# ---------------------------------------------------------------- W-2

W2_FULL = """Form W-2 Wage and Tax Statement  Tax Year 2024
Employer: ACME CORPORATION EIN 12-3456789
Box 1 Wages, tips, other compensation: $85,000.00
Box 2 Federal income tax withheld: $12,340.00
Box 3 Social security wages: $85,000.00
Box 4 Social security tax withheld: $5,270.00
Box 5 Medicare wages and tips: $85,000.00
Box 6 Medicare tax withheld: $1,232.50
"""

W2_SECOND_JOB = """W-2 WAGE AND TAX STATEMENT FOR CALENDAR YEAR 2023
Employer: SECOND JOB LLC EIN 98-7654321
Box 1 Wages: $12,000.00
Box 2 Federal withholding: $1,100.00
"""

W2_SPARSE = """Form W-2 Tax Year 2024
Some unreadable scan fragment with no boxes at all
"""


def test_w2_full_exact():
    fields, status = extract_fields("W-2", W2_FULL)
    assert status == "transcribed"
    assert field(fields, "1")["value"] == "85000.00"
    assert field(fields, "1")["confidence"] == "high"
    assert field(fields, "2")["value"] == "12340.00"
    assert field(fields, "3")["value"] == "85000.00"
    assert field(fields, "4")["value"] == "5270.00"
    assert field(fields, "5")["value"] == "85000.00"
    assert field(fields, "6")["value"] == "1232.50"
    assert field(fields, "employer_ein")["value"] == "12-3456789"
    assert field(fields, "employer_ein")["confidence"] == "high"


def test_w2_second_job_year_and_key_boxes():
    assert detect_tax_year(W2_SECOND_JOB) == 2023
    fields, status = extract_fields("W-2", W2_SECOND_JOB)
    assert status == "transcribed"
    assert field(fields, "1")["value"] == "12000.00"
    assert field(fields, "2")["value"] == "1100.00"
    assert field(fields, "employer_ein")["value"] == "98-7654321"


def test_w2_sparse_needs_review():
    fields, status = extract_fields("W-2", W2_SPARSE)
    assert status == "needs_review"
    assert field(fields, "1")["value"] is None
    assert field(fields, "1")["confidence"] == "low"


# ---------------------------------------------------------------- 1099-B

B1099_FULL = """Form 1099-B Proceeds From Broker Transactions Tax Year 2024
Broker: EXAMPLE BROKERAGE
Box 1d Proceeds: $12,500.00
Box 1e Cost basis: $9,800.00
Date acquired: 03/15/2022 Date sold: 06/20/2024
Holding period: long term
"""

B1099_SHORT = """1099-B Tax Year 2023
Broker: SAMPLE SECURITIES
Box 1d Proceeds: $2,000.00
Date acquired 01/05/2023 Date sold 11/30/2023 short term
"""


def _lots(fields):
    return field(fields, "lots")["value"]


def test_1099b_full_exact():
    fields, status = extract_fields("1099-B", B1099_FULL)
    assert status == "transcribed"
    lots = _lots(fields)
    assert len(lots) == 1
    lot = lots[0]
    assert lot["proceeds_1d"] == "12500.00"
    assert lot["basis_1e"] == "9800.00"
    assert lot["date_acquired"] == "03/15/2022"
    assert lot["date_sold"] == "06/20/2024"
    assert lot["term"] == "long"
    assert "EXAMPLE BROKERAGE" in field(fields, "broker")["value"]


def test_1099b_short_term():
    fields, status = extract_fields("1099-B", B1099_SHORT)
    lots = _lots(fields)
    assert len(lots) == 1
    assert lots[0]["proceeds_1d"] == "2000.00"
    assert lots[0]["term"] == "short"


# F1: multi-lot labeled layout -- every lot extracted, never just the first.
B1099_THREE_LOTS = """Form 1099-B Proceeds From Broker Transactions Tax Year 2024
Broker: EXAMPLE BROKERAGE
Lot 1 1d Proceeds $1000.00 1e Cost or other basis $1500.00 1g Wash sale loss disallowed $0.00 short term
Lot 2 1d Proceeds $2000.00 1e Cost or other basis $2600.00 1g Wash sale loss disallowed $300.00 short term
Lot 3 1d Proceeds $500.00 1e Cost or other basis $400.00 1g Wash sale loss disallowed $0.00 short term
"""


def test_1099b_three_lots_all_extracted():
    fields, status = extract_fields("1099-B", B1099_THREE_LOTS)
    assert status == "transcribed"
    lots = _lots(fields)
    assert len(lots) == 3
    assert [l["proceeds_1d"] for l in lots] == ["1000.00", "2000.00", "500.00"]
    assert [l["basis_1e"] for l in lots] == ["1500.00", "2600.00", "400.00"]
    # F3: 1g extracted per lot
    assert [l["wash_1g"] for l in lots] == ["0.00", "300.00", "0.00"]
    assert all(l["term"] == "short" for l in lots)
    # money values are Decimal-safe strings, never floats
    for l in lots:
        for k in ("proceeds_1d", "basis_1e", "wash_1g"):
            assert isinstance(l[k], str) and not isinstance(l[k], float)


B1099_REPEATED_BLOCKS = """Form 1099-B Proceeds From Broker Transactions Tax Year 2024
Broker: EXAMPLE BROKERAGE
Description: 100 SHARES XYZ CORP
Date acquired: 01/15/2022 Date sold: 06/20/2024
Box 1d Proceeds: $12,500.00
Box 1e Cost basis: $9,800.00
Holding period: long term
Description: 50 SHARES ABC INC
Date acquired: 02/10/2023 Date sold: 07/22/2024
Box 1d Proceeds: $3,000.00
Box 1e Cost basis: $3,400.00
Holding period: long term
"""


def test_1099b_repeated_labeled_blocks():
    fields, status = extract_fields("1099-B", B1099_REPEATED_BLOCKS)
    assert status == "transcribed"
    lots = _lots(fields)
    assert len(lots) == 2
    assert lots[0]["proceeds_1d"] == "12500.00"
    assert lots[0]["basis_1e"] == "9800.00"
    assert lots[0]["description"] == "100 SHARES XYZ CORP"
    assert lots[1]["proceeds_1d"] == "3000.00"
    assert lots[1]["basis_1e"] == "3400.00"
    assert lots[1]["description"] == "50 SHARES ABC INC"
    assert all(l["term"] == "long" for l in lots)


# F1b: section headings propagate term/covered to every lot in the
# section. All fixtures synthetic.
B1099_HEADING_SHORT_COVERED = """Form 1099-B Proceeds From Broker Transactions Tax Year 2024
Broker: EXAMPLE BROKERAGE
Short-term covered
Lot 1 1d Proceeds $1000.00 1e Cost or other basis $1500.00
Lot 2 1d Proceeds $2000.00 1e Cost or other basis $2400.00
Lot 3 1d Proceeds $500.00 1e Cost or other basis $300.00
"""


def test_1099b_section_heading_propagates_term_covered():
    # workstation probe: 3 lots under "Short-term covered" -- all lots
    # get term=short, covered=covered
    fields, status = extract_fields("1099-B", B1099_HEADING_SHORT_COVERED)
    assert status == "transcribed"
    lots = _lots(fields)
    assert len(lots) == 3
    assert all(l["term"] == "short" for l in lots)
    assert all(l["covered"] == "covered" for l in lots)


B1099_TWO_SECTIONS = """Form 1099-B Proceeds From Broker Transactions Tax Year 2024
Broker: EXAMPLE BROKERAGE
Short-term covered
Lot 1 1d Proceeds $1000.00 1e Cost or other basis $1500.00
Lot 2 1d Proceeds $2000.00 1e Cost or other basis $2400.00
Long-term noncovered
Lot 3 1d Proceeds $500.00 1e Cost or other basis $300.00
"""


def test_1099b_two_sections_assign_per_section():
    # the long-term heading sits between lot 2 and lot 3: it must not
    # leak back onto lot 2, and lot 3 takes it
    fields, status = extract_fields("1099-B", B1099_TWO_SECTIONS)
    assert status == "transcribed"
    lots = _lots(fields)
    assert len(lots) == 3
    assert [l["term"] for l in lots] == ["short", "short", "long"]
    assert [l["covered"] for l in lots] == ["covered", "covered",
                                            "noncovered"]


def test_1099b_no_heading_term_stays_none():
    # genuinely unknown stays None -- G2 raises it to the Operator
    text = """Form 1099-B Proceeds From Broker Transactions Tax Year 2024
Broker: EXAMPLE BROKERAGE
Lot 1 1d Proceeds $1000.00 1e Cost or other basis $1500.00
Lot 2 1d Proceeds $2000.00 1e Cost or other basis $2400.00
"""
    fields, _ = extract_fields("1099-B", text)
    lots = _lots(fields)
    assert len(lots) == 2
    assert all(l["term"] is None for l in lots)
    assert all(l["covered"] is None for l in lots)


def test_1099b_box2_term_fallback_without_headings():
    # form box 2 ("Short-term/Long-term gain or loss") is the fallback
    # term source when no section headings exist
    text = """Form 1099-B Proceeds From Broker Transactions Tax Year 2024
Broker: EXAMPLE BROKERAGE
Box 2: Short-term gain or loss
Lot 1 1d Proceeds $1000.00 1e Cost or other basis $1500.00
"""
    fields, _ = extract_fields("1099-B", text)
    lots = _lots(fields)
    assert lots[0]["term"] == "short"
    assert lots[0]["covered"] is None  # box 2 carries no covered info


def test_1099b_lot_own_term_beats_heading():
    # a lot's own segment wins over the section heading
    text = """Form 1099-B Proceeds From Broker Transactions Tax Year 2024
Broker: EXAMPLE BROKERAGE
Short-term covered
Lot 1 1d Proceeds $1000.00 1e Cost or other basis $1500.00 long term
"""
    fields, _ = extract_fields("1099-B", text)
    lots = _lots(fields)
    assert lots[0]["term"] == "long"      # segment wins
    assert lots[0]["covered"] == "covered"  # inherited


# B1F: box 1f is accrued market discount (Schedule B interest income),
# NOT federal income tax withheld -- that is box 4.
B1099_1F_AND_4 = """Form 1099-B Proceeds From Broker Transactions Tax Year 2024
Broker: EXAMPLE BROKERAGE
Lot 1 1d Proceeds $1000.00 1e Cost or other basis $1500.00 short term
Accrued market discount $25.00
Federal income tax withheld $28.00
"""


def test_1099b_box1f_is_accrued_market_discount_not_withholding():
    fields, _ = extract_fields("1099-B", B1099_1F_AND_4)
    lot = _lots(fields)[0]
    assert lot["accrued_market_discount_1f"] == "25.00"
    assert lot["fed_withheld_4"] == "28.00"
    assert "fed_withheld_1f" not in lot  # the old mis-mapping is gone
    # Decimal-safe strings, never floats
    assert isinstance(lot["accrued_market_discount_1f"], str)
    assert isinstance(lot["fed_withheld_4"], str)


def test_1099b_box4_labeled_withholding():
    text = """Form 1099-B Proceeds From Broker Transactions Tax Year 2024
Broker: EXAMPLE BROKERAGE
Lot 1 1d Proceeds $1000.00 1e Cost or other basis $1500.00 short term
Box 4: $28.00
"""
    fields, _ = extract_fields("1099-B", text)
    lot = _lots(fields)[0]
    assert lot["fed_withheld_4"] == "28.00"
    assert lot["accrued_market_discount_1f"] is None


def test_1099b_1f_box_code_maps_to_discount():
    text = """Form 1099-B Proceeds From Broker Transactions Tax Year 2024
Broker: EXAMPLE BROKERAGE
Lot 1 1d Proceeds $1000.00 1e Cost or other basis $1500.00 short term 1f $12.50
"""
    fields, _ = extract_fields("1099-B", text)
    lot = _lots(fields)[0]
    assert lot["accrued_market_discount_1f"] == "12.50"
    assert lot["fed_withheld_4"] is None


# D3: workstation probes, verbatim -- the greedy-gap truncation bug made
# "52,345.67" extract as "5.67" and "100.00" as "0.0".
@pytest.mark.parametrize("text,expected", [
    ("Form 1099-B\nBroker: X\nLot 1 1d Proceeds 52,345.67", "52345.67"),
    ("Form 1099-B\nBroker: X\nLot 1 1d Proceeds 100.00", "100.00"),
    ("Form 1099-B\nBroker: X\nLot 1 1d Proceeds 1234.56", "1234.56"),
    ("Form 1099-B\nBroker: X\nLot 1 1d Proceeds $52,345.67", "52345.67"),
    ("Form 1099-B\nBroker: X\nLot 1 1d Proceeds $ 1,234.00", "1234.00"),
    ("Form 1099-B\nBroker: X\nLot 1 1d Proceeds 8.50", "8.50"),
    # parenthesized negatives
    ("Form 1099-B\nBroker: X\nLot 1 1d Proceeds ($1,234.56)", "-1234.56"),
])
def test_d3_money_truncation_probes(text, expected):
    fields, _ = extract_fields("1099-B", text)
    assert _lots(fields)[0]["proceeds_1d"] == expected


@pytest.mark.parametrize("form_type,text,box,expected", [
    # amounts >= 10 without "$" across W-2 and 1099 box extractors
    ("W-2", "Form W-2 Tax Year 2024\nWages, tips, other compensation 52,345.67\nEIN 12-3456789\n",
     "1", "52345.67"),
    ("W-2", "Form W-2 Tax Year 2024\nFederal income tax withheld 12340.00\nEIN 12-3456789\n",
     "2", "12340.00"),
    ("1099-INT", "Form 1099-INT Tax Year 2024\nInterest income 420.50", "1", "420.50"),
    ("1099-DIV", "Form 1099-DIV Tax Year 2024\nTotal ordinary dividends 1200.00", "1a", "1200.00"),
    ("1099-NEC", "Form 1099-NEC Tax Year 2024\nNonemployee compensation 8750.00", "1", "8750.00"),
    ("1099-R", "Form 1099-R Tax Year 2024\nGross distribution 25000.00", "1", "25000.00"),
    ("1098", "Form 1098 Tax Year 2024\nMortgage interest received 12400.00", "1", "12400.00"),
    ("1099-MISC", "Form 1099-MISC Tax Year 2024\nRents 3600.00", "1", "3600.00"),
])
def test_d3_bare_amounts_across_forms(form_type, text, box, expected):
    fields, _ = extract_fields(form_type, text)
    assert field(fields, box)["value"] == expected


def test_d3_amount_is_whole_token_in_raw_text():
    """Invariant: every extracted money string appears as a whole token
    (comma/space-insensitive) in its field's raw_text -- no truncation."""
    import re as _re
    texts = [B1099_FULL, B1099_SHORT, B1099_THREE_LOTS, B1099_REPEATED_BLOCKS,
             W2_FULL, INT_FULL, DIV_FULL, NEC, R1099, F1098, MISC]
    forms = ["1099-B"] * 4 + ["W-2", "1099-INT", "1099-DIV", "1099-NEC",
                              "1099-R", "1098", "1099-MISC"]

    def check_value(value, raw_text):
        if not isinstance(value, str):
            return
        if not _re.fullmatch(r"-?\d+\.\d{2}", value):
            return
        # parenthesized negatives carry the "-" outside the raw token
        token = value.lstrip("-")
        cleaned = raw_text.replace(",", "")
        assert _re.search(r"(?<![\d.,])" + _re.escape(token) + r"(?![\d.])",
                          cleaned), (value, raw_text)

    for form_type, text in zip(forms, texts):
        fields, _ = extract_fields(form_type, text)
        for code, f in fields.items():
            if not isinstance(f, dict):
                continue
            v = f.get("value")
            if code == "lots" and isinstance(v, list):
                for lot in v:
                    for lv in lot.values():
                        check_value(lv, f.get("raw_text") or "")
            else:
                check_value(v, f.get("raw_text") or "")


# Summary totals (statement-level, feeds verify_summary_reconciliation).
B1099_WITH_TOTALS = B1099_THREE_LOTS + \
    "Short-term totals: Proceeds $3500.00 Basis $4500.00\n"


def test_1099b_summary_totals_extracted():
    fields, _ = extract_fields("1099-B", B1099_WITH_TOTALS)
    totals = field(fields, "summary_totals")["value"]
    assert totals == {"short": {"proceeds_1d": "3500.00",
                                "basis_1e": "4500.00"}}
    # the totals line must not become a fourth lot
    assert len(_lots(fields)) == 3


def test_1099b_summary_totals_absent_is_missing():
    fields, _ = extract_fields("1099-B", B1099_THREE_LOTS)
    f = field(fields, "summary_totals")
    assert f["value"] is None and f["confidence"] == "low"


def test_1099b_long_term_totals_form():
    text = (B1099_THREE_LOTS +
            "Total Long-Term Proceeds $9000.00\nTotal Long-Term Basis $8100.00\n")
    fields, _ = extract_fields("1099-B", text)
    totals = field(fields, "summary_totals")["value"]
    assert totals["long"] == {"proceeds_1d": "9000.00", "basis_1e": "8100.00"}
    assert len(_lots(fields)) == 3


# ---------------------------------------------------------------- 1099-INT

INT_FULL = """Form 1099-INT Interest Income Tax Year 2024
Box 1 Interest income: $420.50
Box 3 Interest on U.S. Savings Bonds: $100.00
"""

INT_SIMPLE = """1099-INT 2025
Box 1 Interest income $15.25
"""


def test_1099int_full_exact():
    fields, status = extract_fields("1099-INT", INT_FULL)
    assert status == "transcribed"
    assert field(fields, "1")["value"] == "420.50"
    assert field(fields, "3")["value"] == "100.00"


def test_1099int_simple():
    fields, status = extract_fields("1099-INT", INT_SIMPLE)
    assert field(fields, "1")["value"] == "15.25"


# ---------------------------------------------------------------- 1099-DIV

DIV_FULL = """Form 1099-DIV Dividends and Distributions Tax Year 2024
Box 1a Total ordinary dividends: $1,200.00
Box 1b Qualified dividends: $1,000.00
Box 2a Total capital gain distr.: $300.00
"""

DIV_SIMPLE = """1099-DIV 2023
Box 1a Ordinary dividends $250.00
Box 1b Qualified $200.00
"""


def test_1099div_full_exact():
    fields, status = extract_fields("1099-DIV", DIV_FULL)
    assert status == "transcribed"
    assert field(fields, "1a")["value"] == "1200.00"
    assert field(fields, "1b")["value"] == "1000.00"
    assert field(fields, "2a")["value"] == "300.00"


def test_1099div_simple():
    fields, status = extract_fields("1099-DIV", DIV_SIMPLE)
    assert field(fields, "1a")["value"] == "250.00"
    assert field(fields, "1b")["value"] == "200.00"


# ---------------------------------------------------------------- 1099-NEC / 1099-R / 1098 / 1099-MISC

NEC = """Form 1099-NEC Nonemployee Compensation Tax Year 2024
Box 1 Nonemployee compensation: $8,750.00
"""

NEC_SMALL = """1099-NEC 2023 Box 1 $600.00"""

R1099 = """Form 1099-R Distributions From Pensions Tax Year 2024
Box 1 Gross distribution: $25,000.00
Box 2a Taxable amount: $25,000.00
Box 7 Distribution code: 1
"""

R1099_ROLLOVER = """1099-R 2023
Box 1 Gross distribution: $10,000.00
Box 7 Distribution code: G
"""

F1098 = """Form 1098 Mortgage Interest Statement Tax Year 2024
Box 1 Mortgage interest received: $12,400.00
"""

F1098_SMALL = """1098 2023 Box 1 $9,800.00"""

MISC = """Form 1099-MISC Miscellaneous Income Tax Year 2024
Box 1 Rents: $6,000.00
Box 3 Other income: $500.00
"""

MISC_RENTS = """1099-MISC 2023 Box 1 Rents $3,600.00"""


def test_1099nec():
    for txt, expected in ((NEC, "8750.00"), (NEC_SMALL, "600.00")):
        fields, status = extract_fields("1099-NEC", txt)
        assert field(fields, "1")["value"] == expected


def test_1099r():
    fields, status = extract_fields("1099-R", R1099)
    assert status == "transcribed"
    assert field(fields, "1")["value"] == "25000.00"
    assert field(fields, "2a")["value"] == "25000.00"
    assert field(fields, "7")["value"] == "1"
    fields2, _ = extract_fields("1099-R", R1099_ROLLOVER)
    assert field(fields2, "7")["value"] == "G"


def test_1098():
    for txt, expected in ((F1098, "12400.00"), (F1098_SMALL, "9800.00")):
        fields, status = extract_fields("1098", txt)
        assert field(fields, "1")["value"] == expected


def test_1099misc():
    fields, status = extract_fields("1099-MISC", MISC)
    assert status == "transcribed"
    assert field(fields, "1")["value"] == "6000.00"
    assert field(fields, "3")["value"] == "500.00"
    fields2, _ = extract_fields("1099-MISC", MISC_RENTS)
    assert field(fields2, "1")["value"] == "3600.00"


# ---------------------------------------------------------------- classification / misc


def test_classify_form_types():
    assert classify_form("FORM W-2 WAGE AND TAX STATEMENT") == "W-2"
    assert classify_form("Form 1099-B Proceeds From Broker") == "1099-B"
    assert classify_form("Form 1099-INT Interest Income") == "1099-INT"
    assert classify_form("Form 1099-DIV Dividends") == "1099-DIV"
    assert classify_form("Form 1099-NEC") == "1099-NEC"
    assert classify_form("Form 1099-R Distributions") == "1099-R"
    assert classify_form("Form 1098 Mortgage Interest") == "1098"
    assert classify_form("Form 1099-MISC Miscellaneous") == "1099-MISC"
    assert classify_form("WAGE AND INCOME TRANSCRIPT") == "WAGE_INCOME_TRANSCRIPT"
    assert classify_form("TAX RETURN TRANSCRIPT") == "RETURN_TRANSCRIPT"
    assert classify_form("FORM 1040-X Amended Return") == "1040-X"
    assert classify_form("FORM 1040 U.S. Individual Income Tax Return") == "1040"
    assert classify_form("random letter with no tax content") == "UNKNOWN"


def test_detect_tax_year():
    assert detect_tax_year("Form W-2 for Tax Year 2024") == 2024
    assert detect_tax_year("FOR CALENDAR YEAR 2023") == 2023
    assert detect_tax_year("no year here") is None


def test_unknown_form_type():
    fields, status = extract_fields("NOPE", "whatever")
    assert fields == {}
    assert status == "needs_review"
