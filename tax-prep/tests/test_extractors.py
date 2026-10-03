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
    assert field(fields, "1")["value"] == 85000.0
    assert field(fields, "1")["confidence"] == "high"
    assert field(fields, "2")["value"] == 12340.0
    assert field(fields, "3")["value"] == 85000.0
    assert field(fields, "4")["value"] == 5270.0
    assert field(fields, "5")["value"] == 85000.0
    assert field(fields, "6")["value"] == 1232.5
    assert field(fields, "employer_ein")["value"] == "12-3456789"
    assert field(fields, "employer_ein")["confidence"] == "high"


def test_w2_second_job_year_and_key_boxes():
    assert detect_tax_year(W2_SECOND_JOB) == 2023
    fields, status = extract_fields("W-2", W2_SECOND_JOB)
    assert status == "transcribed"
    assert field(fields, "1")["value"] == 12000.0
    assert field(fields, "2")["value"] == 1100.0
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


def test_1099b_full_exact():
    fields, status = extract_fields("1099-B", B1099_FULL)
    assert status == "transcribed"
    assert field(fields, "1d_proceeds")["value"] == 12500.0
    assert field(fields, "1e_basis")["value"] == 9800.0
    assert field(fields, "date_acquired")["value"] == "03/15/2022"
    assert field(fields, "date_sold")["value"] == "06/20/2024"
    assert field(fields, "term")["value"] == "long"
    assert "EXAMPLE BROKERAGE" in field(fields, "broker")["value"]


def test_1099b_short_term():
    fields, status = extract_fields("1099-B", B1099_SHORT)
    assert field(fields, "1d_proceeds")["value"] == 2000.0
    assert field(fields, "term")["value"] == "short"


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
    assert field(fields, "1")["value"] == 420.50
    assert field(fields, "3")["value"] == 100.00


def test_1099int_simple():
    fields, status = extract_fields("1099-INT", INT_SIMPLE)
    assert field(fields, "1")["value"] == 15.25


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
    assert field(fields, "1a")["value"] == 1200.0
    assert field(fields, "1b")["value"] == 1000.0
    assert field(fields, "2a")["value"] == 300.0


def test_1099div_simple():
    fields, status = extract_fields("1099-DIV", DIV_SIMPLE)
    assert field(fields, "1a")["value"] == 250.0
    assert field(fields, "1b")["value"] == 200.0


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
    for txt, expected in ((NEC, 8750.0), (NEC_SMALL, 600.0)):
        fields, status = extract_fields("1099-NEC", txt)
        assert field(fields, "1")["value"] == expected


def test_1099r():
    fields, status = extract_fields("1099-R", R1099)
    assert status == "transcribed"
    assert field(fields, "1")["value"] == 25000.0
    assert field(fields, "2a")["value"] == 25000.0
    assert field(fields, "7")["value"] == "1"
    fields2, _ = extract_fields("1099-R", R1099_ROLLOVER)
    assert field(fields2, "7")["value"] == "G"


def test_1098():
    for txt, expected in ((F1098, 12400.0), (F1098_SMALL, 9800.0)):
        fields, status = extract_fields("1098", txt)
        assert field(fields, "1")["value"] == expected


def test_1099misc():
    fields, status = extract_fields("1099-MISC", MISC)
    assert status == "transcribed"
    assert field(fields, "1")["value"] == 6000.0
    assert field(fields, "3")["value"] == 500.0
    fields2, _ = extract_fields("1099-MISC", MISC_RENTS)
    assert field(fields2, "1")["value"] == 3600.0


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
