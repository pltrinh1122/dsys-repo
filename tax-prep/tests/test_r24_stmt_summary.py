"""R24(b) tests: synthetic consolidated-1099 PDFs with known answers."""

import csv
import hashlib
import io
import json
import re
from decimal import Decimal
from pathlib import Path

import pytest
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from taxprep.stmt_summary import (
    SEED_COLUMNS,
    dedupe,
    load_vocab,
    parse_statement_pdf,
    seed_rows,
    seed_template,
    write_seed_csv,
)

PAGE_W, PAGE_H = letter

# Money columns: right edges (values right-aligned).
COL_R = [380, 425, 470, 515, 560, 600]
COL_L = [340, 385, 430, 475, 520, 560]


def _pdf(path: Path, draw):
    c = canvas.Canvas(str(path), pagesize=letter)
    draw(c)
    c.showPage()
    c.save()


def _meta(c, *, year, ein, acct, recipient, corrected=False):
    c.setFont("Helvetica", 10)
    c.drawString(50, 750, "Consolidated Form 1099")
    c.drawString(50, 736, f"For calendar year {year}")
    c.drawString(50, 722, f"Payer EIN {ein}")
    c.drawString(50, 708, f"Account Number {acct}")
    c.drawString(50, 694, f"Recipient: {recipient}")
    if corrected:
        c.drawString(50, 680, "CORRECTED Copy B for Recipient")


def _header1(c, y=630):
    """Draw the two-line wrapped header; returns {first-word: x}."""
    c.setFont("Helvetica", 9)
    cols = ["Proceeds", "Cost Basis", "Market", "Wash", "Gain/Loss",
            "Income Tax"]
    xs = {}
    x = 340
    for col in cols:
        xs[col.split()[0]] = x
        c.drawString(x, y, col)
        x += c.stringWidth(col, "Helvetica", 9) + 14
    c.drawString(xs["Market"], y - 12, "Discount")
    c.drawString(xs["Wash"], y - 12, "Sales Disallowed")
    c.drawString(xs["Income"], y - 12, "Withheld")
    return xs


def _row1(c, y, label, vals, xs):
    c.setFont("Helvetica", 9)
    c.drawString(45, y, label)
    c.setFont("Helvetica", 10)
    order = ["Proceeds", "Cost", "Market", "Wash", "Gain/Loss", "Income"]
    for v, col in zip(vals, order):
        if v is not None:
            c.drawString(xs[col], y, v)


def layout1_pdf(path: Path, *, year=2022, ein="12-3456789", acct="987654321",
                recipient="John Smith", corrected=False, div_rows=(),
                int_rows=(), extra_rows=()):
    """Two basis-reported rows (A: ST, D: LT) with consistent nets."""
    def draw(c):
        _meta(c, year=year, ein=ein, acct=acct, recipient=recipient,
              corrected=corrected)
        xs = _header1(c)
        _row1(c, 600, "Short-term transactions for which basis is "
                       "reported to the IRS",
              ["1000.00", "800.00", "0.00", "50.00", "250.00", "10.00"], xs)
        _row1(c, 585, "Long-term transactions for which basis is "
                       "reported to the IRS",
              ["3000.00", "2000.00", "0.00", "100.00", "1100.00", "0.00"], xs)
        for i, (label, vals) in enumerate(extra_rows):
            _row1(c, 570 - 15 * i, label, vals, xs)
        c.setFont("Helvetica", 10)
        c.drawString(50, 545, "1099-B Section Total")
        y = 515
        if div_rows:
            c.drawString(50, y, "Details of 1099-DIV Transactions")
            y -= 15
            for box, label, amt in div_rows:
                c.drawString(50, y, f"{box} {label} {amt}")
                y -= 15
        if int_rows:
            c.drawString(50, y, "Summary of Interest Income")
            y -= 15
            for box, label, amt in int_rows:
                c.drawString(50, y, f"Box {box} {label} {amt}")
                y -= 15
    _pdf(path, draw)


def layout2_pdf(path: Path, *, year=2022, ein="98-7654321", acct="11223344",
                recipient="Jane Doe", corrected=False):
    def draw(c):
        _meta(c, year=year, ein=ein, acct=acct, recipient=recipient,
              corrected=corrected)
        c.setFont("Helvetica", 10)
        c.drawString(50, 650, "REALIZED GAIN / LOSS SUMMARY")
        c.drawString(50, 630, "Box A Short-Term Realized Gain 500.00")
        c.drawString(50, 615, "Box A Short-Term Realized Loss 200.00")
        c.drawString(50, 600, "Box D Long-Term Realized Gain 1000.00")
        c.drawString(50, 585, "Box D Long-Term Realized Loss 100.00")
        c.drawString(50, 570, "Total Short-Term")
        c.drawString(50, 555, "Total Long-Term")
    _pdf(path, draw)


@pytest.fixture()
def vocab():
    return load_vocab(None)


@pytest.fixture()
def persons(tmp_path):
    p = tmp_path / "persons.json"
    p.write_text(json.dumps({"John Smith": "person-1",
                             "Jane Doe": "person-2"}), encoding="utf-8")
    return str(p)


def _persons_dict(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Layout 1: box extraction.
# ---------------------------------------------------------------------------

def test_layout1_boxes(tmp_path, vocab, persons):
    pdf = tmp_path / "fidelity-2022.pdf"
    layout1_pdf(pdf)
    rec = parse_statement_pdf(str(pdf), vocab, _persons_dict(persons))
    assert rec["layout"] == "layout_1"
    assert rec["year"] == 2022
    assert rec["payer_ein"] == "12-3456789"
    assert rec["person"] == "person-1"
    assert rec["corrected"] is False
    a, d = rec["boxes"]["A"], rec["boxes"]["D"]
    assert (a["proceeds"], a["cost_basis"], a["wash"], a["net"],
            a["withheld"]) == ("1000.00", "800.00", "50.00", "250.00", "10.00")
    assert (d["proceeds"], d["cost_basis"], d["wash"], d["net"]) == \
        ("3000.00", "2000.00", "100.00", "1100.00")
    assert rec["st_total"]["net"] == "250.00"
    assert rec["lt_total"]["net"] == "1100.00"


def test_layout1_opaque_acct_id(tmp_path, vocab, persons, capsys):
    pdf = tmp_path / "fidelity-2022.pdf"
    layout1_pdf(pdf)
    rec = parse_statement_pdf(str(pdf), vocab, _persons_dict(persons))
    expect = hashlib.sha256(b"12-3456789" + b"987654321").hexdigest()[:8]
    assert rec["acct_id"] == expect
    assert rec["acct_id"] != "987654321"
    # Blind-safe: the account number never appears in the record's
    # printable surface except inside the opaque id computation.
    blob = json.dumps({k: v for k, v in rec.items() if k != "_sums"})
    assert "987654321" not in blob


def test_layout1_net_mismatch_flag(tmp_path, vocab, persons):
    pdf = tmp_path / "bad-net.pdf"
    layout1_pdf(
        pdf, extra_rows=[
            ("Short-term transactions for which basis is not reported to "
             "the IRS",
             ["2000.00", "1500.00", "0.00", "0.00", "999.00", "0.00"]),
        ])
    rec = parse_statement_pdf(str(pdf), vocab, _persons_dict(persons))
    assert "net_mismatch:box_B" in rec["flags"]
    # The printed net is kept (authoritative), not recomputed.
    assert rec["boxes"]["B"]["net"] == "999.00"


def test_layout1_unmatched_row_label(tmp_path, vocab, persons):
    pdf = tmp_path / "weird-row.pdf"
    layout1_pdf(
        pdf, extra_rows=[
            ("Mystery category with made-up words",
             ["100.00", "90.00", "0.00", "0.00", "10.00", "0.00"]),
        ])
    rec = parse_statement_pdf(str(pdf), vocab, _persons_dict(persons))
    assert any("Mystery category" in u for u in rec["unmatched_labels"])
    assert "B" not in rec["boxes"]  # never guessed into a box


# ---------------------------------------------------------------------------
# Layout 2: gain/loss rows.
# ---------------------------------------------------------------------------

def test_layout2_boxes(tmp_path, vocab, persons):
    pdf = tmp_path / "second-payer-2022.pdf"
    layout2_pdf(pdf)
    rec = parse_statement_pdf(str(pdf), vocab, _persons_dict(persons))
    assert rec["layout"] == "layout_2"
    assert rec["payer_ein"] == "98-7654321"
    assert rec["boxes"]["A"]["net"] == "300.00"    # 500 - 200
    assert rec["boxes"]["D"]["net"] == "900.00"    # 1000 - 100
    assert rec["boxes"]["A"]["proceeds"] == ""     # gain/loss only
    assert "B" not in rec["boxes"]


# ---------------------------------------------------------------------------
# Duplicates / corrected pairs.
# ---------------------------------------------------------------------------

def test_duplicate_corrected_pair(tmp_path, vocab, persons):
    p1 = tmp_path / "stmt-orig.pdf"
    p2 = tmp_path / "stmt-corr.pdf"
    layout1_pdf(p1, corrected=False)
    layout1_pdf(p2, corrected=True)
    recs = [parse_statement_pdf(str(p), vocab, _persons_dict(persons))
            for p in (p1, p2)]
    kept, pairs = dedupe(recs)
    assert len(kept) == 1
    assert kept[0]["corrected"] is True
    assert len(pairs) == 1
    assert pairs[0]["reason"] == "corrected"
    assert pairs[0]["kept"] == kept[0]["file_id"]
    assert len(pairs[0]["dropped"]) == 1


def test_duplicate_plain_pair_keeps_first(tmp_path, vocab, persons):
    p1 = tmp_path / "stmt-a.pdf"
    p2 = tmp_path / "stmt-b.pdf"
    layout1_pdf(p1)
    layout1_pdf(p2)
    recs = [parse_statement_pdf(str(p), vocab, _persons_dict(persons))
            for p in (p1, p2)]
    # Different bytes (timestamps) but same key.
    kept, pairs = dedupe(recs)
    assert len(kept) == 1
    assert pairs[0]["reason"] == "first_seen"


# ---------------------------------------------------------------------------
# DIV / INT / withholding sections.
# ---------------------------------------------------------------------------

def test_div_int_sections(tmp_path, vocab, persons):
    pdf = tmp_path / "with-div.pdf"
    layout1_pdf(pdf,
                div_rows=[("1a", "Total ordinary dividends", "500.00"),
                          ("1b", "Qualified dividends", "400.00"),
                          ("2a", "Total capital gain distributions", "300.00")],
                int_rows=[("1", "Interest income", "100.00"),
                          ("3", "Interest on US savings bonds", "25.00")])
    rec = parse_statement_pdf(str(pdf), vocab, _persons_dict(persons))
    assert rec["div"] == {"1A": "500.00", "1B": "400.00", "2A": "300.00"}
    assert rec["int"] == {"1": "100.00", "3": "25.00"}
    assert rec["withholding_total"] == "10.00"  # box-A column only

# ---------------------------------------------------------------------------
# Reconciliation, template, blind-safety, end-to-end.
# ---------------------------------------------------------------------------

from taxprep.stmt_summary import run as stmt_run
from taxprep.stmt_summary import seed_template as _seed_template


def _return_csv(path: Path, *, year=2022, st_sale="1000.00", st_cost="800.00",
                st_adj="50.00", lt_sale="3000.00", lt_cost="2000.00",
                lt_adj="100.00"):
    path.write_text(
        "label,value\n"
        f"# Return Transcript {year},\n"
        "# Schedule D - Capital Gains and Losses,\n"
        f"Short term basis sale amount,{st_sale}\n"
        f"Short term basis cost amount,{st_cost}\n"
        f"Short term basis adjustments,{st_adj}\n"
        f"Long term basis sale amount,{lt_sale}\n"
        f"Long term basis cost amount,{lt_cost}\n"
        f"Long term basis adjustments,{lt_adj}\n",
        encoding="utf-8")


def _wi_csv(path: Path, *, year=2022, proceeds="900.00"):
    path.write_text(
        "label,value\n"
        f"# Wage and Income Transcript {year},\n"
        f"1099-B Proceeds,{proceeds}\n",
        encoding="utf-8")


def _run_e2e(tmp_path, pdfs, *, csvs=(), persons=None):
    csv_dir = tmp_path / "csvs"
    csv_dir.mkdir(exist_ok=True)
    for name, text in csvs:
        (csv_dir / name).write_text(text, encoding="utf-8")
    out = tmp_path / "packets"
    code = stmt_run(pdfs=[str(p) for p in pdfs],
                    persons_file=persons,
                    csv_dir=str(csv_dir) if csvs else None,
                    out=str(out))
    return code, out


def test_sched_d_recon_pass(tmp_path, vocab, persons, capsys):
    pdf = tmp_path / "fidelity-2022.pdf"
    layout1_pdf(pdf)
    _return_csv(tmp_path / "return-2022.csv")
    code, out = _run_e2e(tmp_path, [pdf],
                         csvs=[("return-2022.csv",
                                (tmp_path / "return-2022.csv").read_text())],
                         persons=persons)
    assert code == 0
    recon = json.loads((out / "2022" / "reconciliation.json").read_text())
    assert recon["sched_d"]["status"] == "pass"
    assert recon["sched_d"]["n_diffs"] == 0
    # Seed sheet parses under (a)'s reader with the exact known answers.
    from taxprep.chain import _parse_seed_sheet
    seed = _parse_seed_sheet(str(out / "2022" / "seed-sheet.csv"))
    by_box = {r["box"]: r for r in seed["rows"]}
    assert by_box["A"]["proceeds"] == Decimal("1000.00")
    assert by_box["A"]["net"] == Decimal("250.00")
    assert by_box["D"]["proceeds"] == Decimal("3000.00")


def test_sched_d_recon_fail_lists_diffs(tmp_path, vocab, persons, capsys):
    pdf = tmp_path / "fidelity-2022.pdf"
    layout1_pdf(pdf)
    _return_csv(tmp_path / "return-2022.csv", st_sale="9999.99")
    code, out = _run_e2e(tmp_path, [pdf],
                         csvs=[("return-2022.csv",
                                (tmp_path / "return-2022.csv").read_text())],
                         persons=persons)
    assert code == 1
    recon = json.loads((out / "2022" / "reconciliation.json").read_text())
    assert recon["sched_d"]["status"] == "fail"
    diff = recon["sched_d"]["diffs"][0]
    assert diff["box"] == "A" and diff["field"] == "proceeds"
    assert diff["as_filed"] == "9999.99" and diff["statements"] == "1000.00"
    # Blind-safe: values stay in the file, never on stdout.
    printed = capsys.readouterr().out
    assert "9999.99" not in printed
    assert "check sched_d_recon_2022: fail" in printed


def test_wi_crosscheck(tmp_path, vocab, persons):
    pdf = tmp_path / "fidelity-2022.pdf"
    layout1_pdf(pdf)
    _return_csv(tmp_path / "return-2022.csv")
    # pass: 900 <= 1000
    _wi_csv(tmp_path / "wi-2022.csv", proceeds="900.00")
    code, out = _run_e2e(
        tmp_path, [pdf],
        csvs=[("return-2022.csv", (tmp_path / "return-2022.csv").read_text()),
              ("wi-2022.csv", (tmp_path / "wi-2022.csv").read_text())],
        persons=persons)
    assert code == 0
    recon = json.loads((out / "2022" / "reconciliation.json").read_text())
    assert recon["wi"]["status"] == "pass"
    # fail: 5000 > 1000
    _wi_csv(tmp_path / "wi-2022.csv", proceeds="5000.00")
    code, _ = _run_e2e(
        tmp_path, [pdf],
        csvs=[("return-2022.csv", (tmp_path / "return-2022.csv").read_text()),
              ("wi-2022.csv", (tmp_path / "wi-2022.csv").read_text())],
        persons=persons)
    assert code == 1


def test_no_csv_dir_skips_reconciliation(tmp_path, vocab, persons, capsys):
    pdf = tmp_path / "fidelity-2022.pdf"
    layout1_pdf(pdf)
    out = tmp_path / "packets"
    code = stmt_run(pdfs=[str(pdf)], persons_file=persons, out=str(out))
    assert code == 0
    recon = json.loads((out / "2022" / "reconciliation.json").read_text())
    assert recon["sched_d"]["status"] == "skip"
    assert recon["wi"]["status"] == "skip"


def test_template_fails_loud_until_filled(tmp_path):
    from taxprep.chain import _SEED_COLUMNS, _parse_seed_sheet
    text = _seed_template()
    assert text.splitlines()[0] == ",".join(_SEED_COLUMNS)
    p = tmp_path / "seed.csv"
    p.write_text(text, encoding="utf-8")
    with pytest.raises(Exception):
        _parse_seed_sheet(str(p))
    # Filled, it parses with the exact schema (a) consumes.
    filled = (",".join(_SEED_COLUMNS) + "\n"
              "2022,12-3456789,a1b2c3d4,person-1,A,"
              "1000.00,800.00,50.00,250.00,st,abc123def4567890,\n")
    p.write_text(filled, encoding="utf-8")
    seed = _parse_seed_sheet(str(p))
    assert seed["rows"][0]["box"] == "A"
    assert seed["rows"][0]["net"] == Decimal("250.00")


def test_blind_safe_stdout(tmp_path, vocab, persons, capsys):
    pdf = tmp_path / "fidelity-2022.pdf"
    layout1_pdf(pdf,
                div_rows=[("1a", "Total ordinary dividends", "500.00")])
    _return_csv(tmp_path / "return-2022.csv")
    code, out = _run_e2e(tmp_path, [pdf],
                         csvs=[("return-2022.csv",
                                (tmp_path / "return-2022.csv").read_text())],
                         persons=persons)
    assert code == 0
    printed = capsys.readouterr().out
    for secret in ("1000.00", "800.00", "3000.00", "500.00", "12-3456789",
                   "987654321", "John Smith"):
        assert secret not in printed, secret
    assert "check sched_d_recon_2022: pass" in printed


def test_cli_template(capsys):
    from taxprep.cli import build_parser
    args = build_parser().parse_args(["stmt-summary", "--template"])
    assert args.func(args) == 0
    out = capsys.readouterr().out
    from taxprep.chain import _SEED_COLUMNS
    assert out.splitlines()[0] == ",".join(_SEED_COLUMNS)


def test_unparseable_pdf_fails_loud_but_collected(tmp_path, vocab, persons,
                                                  capsys):
    good = tmp_path / "good.pdf"
    bad = tmp_path / "bad.pdf"
    layout1_pdf(good)
    bad.write_text("not a pdf at all", encoding="utf-8")
    out = tmp_path / "packets"
    code = stmt_run(pdfs=[str(good), str(bad)], persons_file=persons,
                    out=str(out))
    assert code == 1
    printed = capsys.readouterr().out
    assert "FAILED" in printed
    # The good file still produced output.
    assert (out / "2022" / "seed-sheet.csv").exists()


def test_dup_box_row_flags_loud(tmp_path, vocab, persons):
    pdf = tmp_path / "dup-row.pdf"
    layout1_pdf(
        pdf, extra_rows=[
            ("Short-term transactions for which basis is reported to "
             "the IRS",
             ["100.00", "90.00", "0.00", "0.00", "10.00", "0.00"]),
        ])
    rec = parse_statement_pdf(str(pdf), vocab, _persons_dict(persons))
    assert "dup_box_row:A" in rec["flags"]
    # First occurrence kept, not overwritten or doubled.
    assert rec["boxes"]["A"]["proceeds"] == "1000.00"
