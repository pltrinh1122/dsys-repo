"""R24 rev1 (part b): header parse + scope on the REAL broker wordings.

Synthetic reportlab PDFs only (digits invented). Covers:
  - tax-year rules by name ('<YEAR> TAX REPORTING STATEMENT',
    'Form 1099-DIV* <YEAR> ...' incl. the pdfplumber 'F orm' split,
    'Form 1099 <YEAR>', a bare '<YEAR>' line, most-frequent fallback);
  - payer EIN anchored on "Payer's Fed ID Number:" / "Federal
    Identification Number:" with a recipient TIN earlier on the same
    line, an EIN-shaped recipient TIN above it, and the absent case
    (payer_ein 'unknown' + flag);
  - whole tax-year folder: W-2 / 1098 -> not_applicable, not failed;
  - dated ORIGINAL/CORRECTED triples: latest corrected kept;
  - layout 1 (Fidelity) with the unknown-term row; layout 2 (Robinhood)
    with the combined 'Realized Gain/Loss' row, the '(basis not reported
    to IRS)' rows and the 'Total ...' cross-check.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from taxprep.stmt_summary import (
    _NotApplicable,
    dedupe,
    load_vocab,
    parse_statement_pdf,
    run as stmt_run,
    seed_rows,
)

PAYER_FID = "04-1234567"
PAYER_RH = "46-7654321"
ACCT = "123-456789"


def _pdf(path: Path, *page_draws):
    c = canvas.Canvas(str(path), pagesize=letter)
    for draw in page_draws:
        draw(c)
        c.showPage()
    c.save()


def _lines(c, lines, *, x=40, y=760, step=14, font=("Helvetica", 9)):
    c.setFont(*font)
    for ln in lines:
        c.drawString(x, y, ln)
        y -= step
    return y


# ---------------------------------------------------------------------------
# Layout 1 (Fidelity): two-line wrapped header + the five summary rows.
# ---------------------------------------------------------------------------

COLS = ["Proceeds", "Cost Basis", "Market", "Wash", "Gain/Loss", "Income Tax"]
COL_KEYS = ["Proceeds", "Cost", "Market", "Wash", "Gain/Loss", "Income"]
WRAP = {"Market": "Discount", "Wash": "Sales Disallowed",
        "Income": "Withheld"}


def _header1(c, y):
    c.setFont("Helvetica", 8)
    xs = {}
    x = 362
    for col, key in zip(COLS, COL_KEYS):
        xs[key] = x
        c.drawString(x, y, col)
        x += c.stringWidth(col, "Helvetica", 8) + 10
    for key, word in WRAP.items():
        c.drawString(xs[key], y - 11, word)
    return xs


def _row1(c, y, label, vals, xs):
    c.setFont("Helvetica", 7)
    c.drawString(40, y, label)
    c.setFont("Helvetica", 8)
    for v, key in zip(vals, COL_KEYS):
        if v is not None:
            c.drawString(xs[key], y, v)


ROW_A = "Short-term transactions for which basis is reported to the IRS"
ROW_B = "Short-term transactions for which basis is not reported to the IRS"
ROW_D = "Long-term transactions for which basis is reported to the IRS"
ROW_E = "Long-term transactions for which basis is not reported to the IRS"
ROW_U = ("Transactions for which basis is not reported to the IRS and "
         "Term is Unknown")

FID_ROWS = {
    ROW_A: ["1000.00", "800.00", "0.00", "50.00", "250.00", "10.00"],
    ROW_B: ["600.00", "500.00", "0.00", "0.00", "100.00", "0.00"],
    ROW_D: ["3000.00", "2000.00", "0.00", "100.00", "1100.00", "0.00"],
    ROW_E: ["400.00", "450.00", "0.00", "0.00", "-50.00", "0.00"],
    ROW_U: ["0.00", "0.00", "0.00", "0.00", "0.00", "0.00"],
}


def fidelity_pdf(path: Path, *, year=2023, header_lines=None,
                 ein_line=None, status_line=None, rows=None,
                 extra_page=None, form_year=True):
    """Fidelity-style consolidated statement, one summary page.

    ``form_year=False`` prints the 1099-B / 1099-DIV form lines without
    a year so the header alone decides the tax year.
    """
    rows = FID_ROWS if rows is None else rows
    fy = f" {year}" if form_year else ""
    head = list(header_lines) if header_lines is not None else [
        f"{year} TAX REPORTING STATEMENT"]
    head.append(ein_line if ein_line is not None else
                f"Recipient ID No. ***-**-6789 Payer's Fed ID Number: "
                f"{PAYER_FID}")
    head.append(f"Account No. {ACCT}")
    head.append("Jane Q Sample")
    if status_line:
        head.append(status_line)
    head.append(f"Form 1099-B*{fy} Proceeds from Broker and Barter "
                f"Exchange Transactions")

    def page1(c):
        y = _lines(c, head)
        xs = _header1(c, y - 10)
        y -= 40
        for label, vals in rows.items():
            _row1(c, y, label, vals, xs)
            y -= 13
        c.setFont("Helvetica", 8)
        c.drawString(40, y - 6, "1099-B Section Total")
        _lines(c, [f"Form 1099-DIV*{fy} Dividends and Distributions"],
               y=y - 40)

    draws = [page1]
    if extra_page:
        draws.append(extra_page)
    _pdf(path, *draws)


# ---------------------------------------------------------------------------
# Layout 2 (Robinhood).
# ---------------------------------------------------------------------------

RH_ROWS = [
    "Box A Short-Term Realized Gain 500.00",
    "Box A Short-Term Realized Loss 200.00",
    "Box D Long-Term Realized Gain/Loss 900.00",
    "Box B (basis not reported to IRS) -50.00",
    "Box E (basis not reported to IRS) 25.00",
    "Total Short-Term 250.00",
    "Total Long-Term 925.00",
    "Total Unknown Term 0.00",
]


def robinhood_pdf(path: Path, *, year=2023, header_lines=None, rows=None,
                  ein_line=None):
    rows = RH_ROWS if rows is None else rows
    head = list(header_lines) if header_lines is not None else [
        "Robinhood Securities LLC", f"{year}"]
    head += [
        ein_line if ein_line is not None else
        f"Federal Identification Number: {PAYER_RH}",
        f"Account Number {ACCT}",
        "John Q Sample",
        "FORM 1099-B TOTALS SUMMARY",
        "REALIZED GAIN / LOSS SUMMARY",
    ] + list(rows)
    _pdf(path, lambda c: _lines(c, head))


# ---------------------------------------------------------------------------
# Non-1099 documents found in the same tax-year folder.
# ---------------------------------------------------------------------------

def w2_pdf(path: Path, year=2023):
    _pdf(path, lambda c: _lines(c, [
        f"{year} W-2 Wage and Tax Statement",
        "Employer identification number 12-3456789",
        "Employee's social security number ***-**-6789",
        "1 Wages, tips, other compensation 50000.00",
        "2 Federal income tax withheld 8000.00",
    ]))


def f1098_pdf(path: Path, year=2023):
    _pdf(path, lambda c: _lines(c, [
        f"Form 1098 Mortgage Interest Statement {year}",
        "RECIPIENT'S/LENDER'S TIN 33-3333333",
        "1 Mortgage interest received from payer(s)/borrower(s) 9000.00",
    ]))


@pytest.fixture()
def vocab():
    return load_vocab(None)


def _parse(path, vocab):
    return parse_statement_pdf(str(path), vocab, {"Jane Q Sample": "person-1",
                                                  "John Q Sample": "person-2"})


# ---------------------------------------------------------------------------
# Layout 1 on the real wordings.
# ---------------------------------------------------------------------------

def test_fidelity_layout_known_numbers(tmp_path, vocab):
    pdf = tmp_path / "fid-2023.pdf"
    fidelity_pdf(pdf)
    rec = _parse(pdf, vocab)
    assert rec["layout"] == "layout_1"
    assert rec["year"] == 2023
    assert rec["year_rule"] == "tax_reporting_statement"
    assert rec["payer_ein"] == PAYER_FID
    assert rec["person"] == "person-1"
    assert set(rec["forms_present"]) == {"B", "DIV"}
    b = rec["boxes"]
    assert (b["A"]["proceeds"], b["A"]["cost_basis"], b["A"]["wash"],
            b["A"]["net"], b["A"]["withheld"]) == \
        ("1000.00", "800.00", "50.00", "250.00", "10.00")
    assert (b["B"]["proceeds"], b["B"]["cost_basis"], b["B"]["net"]) == \
        ("600.00", "500.00", "100.00")
    assert (b["D"]["proceeds"], b["D"]["cost_basis"], b["D"]["wash"],
            b["D"]["net"]) == ("3000.00", "2000.00", "100.00", "1100.00")
    assert (b["E"]["proceeds"], b["E"]["cost_basis"], b["E"]["net"]) == \
        ("400.00", "450.00", "-50.00")
    assert rec["st_total"]["net"] == "350.00"
    assert rec["lt_total"]["net"] == "1050.00"
    # Unknown-term row: recorded apart, zero -> no flag, never a box.
    assert "U" not in b
    assert rec["unknown_term"]["net"] == "0.00"
    assert "unknown_term_present" not in rec["flags"]
    assert rec["unmatched_labels"] == []
    assert {r["box"] for r in seed_rows([rec])} == {"A", "B", "D", "E"}


def test_fidelity_unknown_term_nonzero_flags(tmp_path, vocab):
    rows = dict(FID_ROWS)
    rows[ROW_U] = ["700.00", "650.00", "0.00", "0.00", "50.00", "0.00"]
    pdf = tmp_path / "fid-unknown.pdf"
    fidelity_pdf(pdf, rows=rows)
    rec = _parse(pdf, vocab)
    assert "unknown_term_present" in rec["flags"]
    assert rec["unknown_term"]["proceeds"] == "700.00"
    assert "U" not in rec["boxes"]
    assert all(r["box"] in "ABCDEF" for r in seed_rows([rec]))


# ---------------------------------------------------------------------------
# Layout 2 on the real wordings.
# ---------------------------------------------------------------------------

def test_robinhood_layout_known_numbers(tmp_path, vocab):
    pdf = tmp_path / "rh-2023.pdf"
    robinhood_pdf(pdf)
    rec = _parse(pdf, vocab)
    assert rec["layout"] == "layout_2"
    assert rec["year"] == 2023
    assert rec["year_rule"] == "bare_year_line"
    assert rec["payer_ein"] == PAYER_RH
    assert rec["person"] == "person-2"
    b = rec["boxes"]
    assert b["A"]["net"] == "300.00"    # 500 gain - 200 loss
    assert b["B"]["net"] == "-50.00"    # (basis not reported to IRS)
    assert b["D"]["net"] == "900.00"    # combined Gain/Loss row
    assert b["E"]["net"] == "25.00"
    assert b["A"]["proceeds"] == ""     # gain/loss only
    assert rec["st_total"]["net"] == "250.00"
    assert rec["lt_total"]["net"] == "925.00"
    assert not any(f.startswith("total_mismatch") for f in rec["flags"])
    assert "unknown_term_present" not in rec["flags"]
    assert rec["unmatched_labels"] == []


def test_robinhood_total_mismatch_and_unknown_term_flags(tmp_path, vocab):
    rows = list(RH_ROWS)
    rows[5] = "Total Short-Term 999.00"       # boxes say 250
    rows[7] = "Total Unknown Term 12.00"
    pdf = tmp_path / "rh-bad.pdf"
    robinhood_pdf(pdf, rows=rows)
    rec = _parse(pdf, vocab)
    assert "total_mismatch:st" in rec["flags"]
    assert "total_mismatch:lt" not in rec["flags"]
    assert "unknown_term_present" in rec["flags"]
    assert rec["unknown_term"]["net"] == "12.00"
    assert rec["boxes"]["A"]["net"] == "300.00"  # boxes stay authoritative


# ---------------------------------------------------------------------------
# Tax-year rules (case-insensitive, 'F orm' split, fallback).
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("header, rule", [
    (["2024 Tax Reporting Statement"], "tax_reporting_statement"),
    (["F orm 1099-DIV* 2024 Dividends and Distributions"], "form_1099_div"),
    (["Form 1099-INT* 2024 Interest Income"], "form_1099_int"),
    (["Form 1099 2024"], "form_1099"),
    (["Consolidated Statement", "2024"], "bare_year_line"),
])
def test_year_rules_by_name(tmp_path, vocab, header, rule):
    pdf = tmp_path / "stmt.pdf"
    # Keep the 1099-B/DIV form lines year-free so only the header decides.
    fidelity_pdf(pdf, year=2024, header_lines=header, form_year=False)
    rec = _parse(pdf, vocab)
    assert rec["year"] == 2024
    assert rec["year_rule"] == rule
    assert "year_fallback" not in rec["flags"]


def test_year_fallback_most_frequent_pages_1_2(tmp_path, vocab):
    pdf = tmp_path / "stmt.pdf"

    def page2(c):
        _lines(c, ["Trade dates 01/15/2023 02/20/2023 12/31/2023",
                   "Printed 02/10/2024"])

    # No page-1 year form at all; the 1099-B/DIV lines need a year-free
    # wording, so build the page by hand.
    def page1(c):
        y = _lines(c, ["Consolidated Statement",
                       f"Payer's Fed ID Number: {PAYER_FID}",
                       f"Account No. {ACCT}",
                       "Form 1099-B Proceeds from Broker transactions"])
        xs = _header1(c, y - 10)
        y -= 40
        for label, vals in FID_ROWS.items():
            _row1(c, y, label, vals, xs)
            y -= 13
    _pdf(pdf, page1, page2)
    rec = _parse(pdf, vocab)
    assert rec["year"] == 2023
    assert rec["year_rule"] == "most_frequent_year_p1_2"
    assert "year_fallback" in rec["flags"]


# ---------------------------------------------------------------------------
# Payer EIN anchoring.
# ---------------------------------------------------------------------------

def test_payer_ein_after_recipient_tin_on_same_line(tmp_path, vocab):
    pdf = tmp_path / "stmt.pdf"
    fidelity_pdf(pdf, ein_line="Recipient ID No. ***-**-6789 "
                               f"Payer's Fed ID Number: {PAYER_FID}")
    rec = _parse(pdf, vocab)
    assert rec["payer_ein"] == PAYER_FID
    assert "payer_ein_unknown" not in rec["flags"]


def test_payer_ein_never_first_hyphenated_number(tmp_path, vocab):
    """An EIN-shaped recipient TIN printed ABOVE the payer label must not
    be taken; the payer label anchors the value on a later page too."""
    pdf = tmp_path / "stmt.pdf"
    fidelity_pdf(pdf, header_lines=["2023 TAX REPORTING STATEMENT",
                                    "Recipient's TIN 99-9999999"],
                 ein_line="Customer service 800-555-0100",
                 extra_page=lambda c: _lines(
                     c, [f"Federal Identification Number: {PAYER_FID}"]))
    rec = _parse(pdf, vocab)
    assert rec["payer_ein"] == PAYER_FID


def test_payer_ein_absent_is_unknown_not_failed(tmp_path, vocab):
    pdf = tmp_path / "stmt.pdf"
    fidelity_pdf(pdf, ein_line="Recipient ID No. ***-**-6789")
    rec = _parse(pdf, vocab)
    assert rec["payer_ein"] == "unknown"
    assert "payer_ein_unknown" in rec["flags"]
    assert rec["boxes"]["A"]["net"] == "250.00"  # still parsed


# ---------------------------------------------------------------------------
# Scope: a whole tax-year folder.
# ---------------------------------------------------------------------------

def test_non_1099_pdfs_are_not_applicable(tmp_path, vocab):
    w2 = tmp_path / "w2.pdf"
    f1098 = tmp_path / "1098.pdf"
    w2_pdf(w2)
    f1098_pdf(f1098)
    for p in (w2, f1098):
        with pytest.raises(_NotApplicable):
            _parse(p, vocab)


def test_div_only_statement_is_a_record_without_boxes(tmp_path, vocab):
    pdf = tmp_path / "div-only.pdf"
    _pdf(pdf, lambda c: _lines(c, [
        "Form 1099-DIV* 2023 Dividends and Distributions",
        f"Payer's Fed ID Number: {PAYER_FID}",
        f"Account No. {ACCT}",
        "1a Total ordinary dividends 500.00",
    ]))
    rec = _parse(pdf, vocab)
    assert rec["boxes"] == {}
    assert rec["layout"] is None
    assert "no_1099b_section" in rec["flags"]
    assert rec["forms_present"] == ["DIV"]
    assert seed_rows([rec]) == []


def test_1099b_present_but_unparsed_stays_loud(tmp_path, vocab):
    from taxprep.stmt_summary import _SummaryError
    pdf = tmp_path / "b-unparsed.pdf"
    _pdf(pdf, lambda c: _lines(c, [
        "2023 TAX REPORTING STATEMENT",
        f"Payer's Fed ID Number: {PAYER_FID}",
        "Form 1099-B* 2023 Proceeds from Broker and Barter Exchange",
        "Some unrecognized table layout 1.00 2.00",
    ]))
    with pytest.raises(_SummaryError):
        _parse(pdf, vocab)


def test_folder_run_counts_not_applicable(tmp_path, capsys):
    folder = tmp_path / "TY2023"
    folder.mkdir()
    fidelity_pdf(folder / "fidelity.pdf")
    robinhood_pdf(folder / "robinhood.PDF")
    w2_pdf(folder / "w2.pdf")
    f1098_pdf(folder / "1098.pdf")
    out = tmp_path / "packets"
    persons = tmp_path / "persons.json"
    persons.write_text(json.dumps({"Jane Q Sample": "person-1",
                                   "John Q Sample": "person-2"}),
                       encoding="utf-8")
    # Through the CLI: --pdf-dir must pick up .PDF too.
    from taxprep.cli import build_parser
    args = build_parser().parse_args([
        "stmt-summary", "--pdf-dir", str(folder), "--out", str(out),
        "--persons-file", str(persons)])
    assert args.func(args) == 0
    printed = capsys.readouterr().out
    assert printed.count("not_applicable (") == 2
    assert "check file_parse: pass (2 file(s) parsed, 2 not_applicable)" \
        in printed
    assert "year_rule=tax_reporting_statement" in printed
    assert "year_rule=bare_year_line" in printed
    # Blind-safe: no amounts, EINs, account numbers or names on stdout.
    for secret in ("1000.00", "250.00", "900.00", PAYER_FID, PAYER_RH,
                   ACCT, ACCT.replace("-", ""), "Jane Q Sample",
                   "John Q Sample", "50000.00"):
        assert secret not in printed, secret
    summary = json.loads((out / "run-summary.json").read_text())
    assert (summary["n_parsed"], summary["n_not_applicable"],
            summary["n_failed"]) == (2, 2, 0)
    assert {e["filename"] for e in summary["not_applicable"]} == \
        {"w2.pdf", "1098.pdf"}
    stmts = json.loads((out / "2023" / "statements.json").read_text())
    assert stmts["n_files"] == 2
    seed = (out / "2023" / "seed-sheet.csv").read_text().splitlines()
    assert len(seed) == 1 + 4 + 4  # header + Fidelity ABDE + Robinhood ABDE
    # 'U' never reaches the seed sheet.
    assert not any(ln.split(",")[4] == "U" for ln in seed[1:])


# ---------------------------------------------------------------------------
# Dated ORIGINAL / CORRECTED pairs.
# ---------------------------------------------------------------------------

def test_latest_corrected_kept(tmp_path, vocab):
    paths = []
    for name, status in (("orig", "ORIGINAL: 02/10/2024"),
                         ("corr1", "CORRECTED 03/05/2024"),
                         ("corr2", "CORRECTED 04/01/2024")):
        p = tmp_path / f"{name}.pdf"
        fidelity_pdf(p, status_line=status)
        paths.append(p)
    recs = [_parse(p, vocab) for p in paths]
    assert [r["corrected"] for r in recs] == [False, True, True]
    assert recs[0]["statement_date"] == "2024-02-10"
    assert recs[2]["statement_date"] == "2024-04-01"
    kept, pairs = dedupe(recs)
    assert len(kept) == 1
    assert kept[0]["file_id"] == recs[2]["file_id"]
    assert pairs[0]["reason"] == "latest_corrected"
    assert set(pairs[0]["dropped"]) == {recs[0]["file_id"],
                                        recs[1]["file_id"]}
    # The same triple in reverse file order: still the latest date.
    kept2, _ = dedupe(list(reversed(recs)))
    assert kept2[0]["file_id"] == recs[2]["file_id"]


def test_original_corrected_pair_reason(tmp_path, vocab):
    p1 = tmp_path / "a.pdf"
    p2 = tmp_path / "b.pdf"
    fidelity_pdf(p1, status_line="ORIGINAL: 02/10/2024")
    fidelity_pdf(p2, status_line="CORRECTED 03/05/2024")
    kept, pairs = dedupe([_parse(p1, vocab), _parse(p2, vocab)])
    assert kept[0]["corrected"] is True
    assert pairs[0]["reason"] == "corrected"


def test_preprinted_corrected_checkbox_is_not_a_correction(tmp_path, vocab):
    pdf = tmp_path / "stmt.pdf"
    fidelity_pdf(pdf, status_line="CORRECTED (if checked)")
    rec = _parse(pdf, vocab)
    assert rec["corrected"] is False
    assert rec["statement_date"] is None
