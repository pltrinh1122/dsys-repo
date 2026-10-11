"""R24(a)+(d): taxprep chain diagnostics. Synthetic fixtures only.

Known-answer coverage: a four-year carryover chain, a low-income year
(worksheet line 1 < 0), a wash-sale seed sheet, an 8814-present return,
W&I partial sets, plus blind-safety, stdlib-only, and failure-mode tests.
"""
from __future__ import annotations

import csv
import io
import json
import os
import stat
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest

from taxprep.chain import run

REPO = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Fixture builders (synthetic).
# ---------------------------------------------------------------------------

def _csv_text(rows):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["label", "value"])
    for label, value in rows:
        w.writerow([label, value])
    return buf.getvalue()


def _return_rows(year, sched_d_rows, form1040_rows, extra=()):
    rows = [(f"# Return Transcript {year}", "")]
    rows.extend(extra)
    rows.append(("# Schedule D - Capital Gains and Losses", ""))
    rows.extend(sched_d_rows)
    rows.append(("# Form 1040", ""))
    rows.extend(form1040_rows)
    return rows


def _sched_d(st_sale, st_cost, st_net, lt_net, lt_rows=()):
    rows = [
        ("Short term basis sale amount", st_sale),
        ("Short term basis cost amount", st_cost),
        ("Net short-term gain/loss", st_net),
        ("Net long-term gain/loss", lt_net),
    ]
    rows.extend(lt_rows)
    return rows


def _form1040(agi, ded, qbi="0.00"):
    return [
        ("Adjusted gross income", agi),
        ("Standard deduction", ded),
        ("Qualified business income deduction", qbi),
        ("Taxable income", "0.00"),
    ]


def _write(dirpath, name, rows):
    p = Path(dirpath) / name
    p.write_text(_csv_text(rows), encoding="utf-8")
    return p


def _base_four_years(csvdir):
    """The known-answer chain: 2022 -15000 ST -> 12000 carryout, etc."""
    csvdir = Path(csvdir)
    csvdir.mkdir(parents=True, exist_ok=True)
    specs = {
        2022: dict(rows=_sched_d("10000.00", "25000.00", "-15000.00", "0.00"),
                   agi="80000.00", ded="12950.00"),
        2023: dict(rows=_sched_d("15000.00", "10000.00", "5000.00", "0.00"),
                   agi="90000.00", ded="13850.00"),
        2024: dict(rows=_sched_d("0.00", "0.00", "0.00", "-1000.00",
                                 lt_rows=[("Long term basis sale amount",
                                            "4000.00"),
                                           ("Long term basis cost amount",
                                            "5000.00")]),
                   agi="95000.00", ded="14600.00"),
        2025: dict(rows=_sched_d("0.00", "0.00", "0.00", "0.00"),
                   agi="100000.00", ded="15000.00"),
    }
    for y, s in specs.items():
        _write(csvdir, f"return-{y}.csv",
               _return_rows(y, s["rows"], _form1040(s["agi"], s["ded"])))
    return csvdir


def _run_chain(csvdir, outdir, **kw):
    kw.setdefault("filing_status", "single")
    return run(csv_dir=str(csvdir), out=str(outdir),
               seed_sheet=None, identity_file=None, **kw)


def _diag(outdir, year):
    return json.loads((Path(outdir) / str(year) / "diagnostic.json")
                      .read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Known answers.
# ---------------------------------------------------------------------------

def test_chain_known_answers(tmp_path):
    csvdir = _base_four_years(tmp_path / "csvs")
    outdir = tmp_path / "packets"
    rc = _run_chain(csvdir, outdir)
    assert rc == 0
    chain = json.loads((outdir / "chain.json").read_text(encoding="utf-8"))
    per = chain["per_year"]
    D = Decimal
    # Hand-computed worksheet values (see module docstring math).
    assert D(per["2022"]["st_carry_out"]) == D("12000")
    assert D(per["2022"]["lt_carry_out"]) == D("0")
    assert D(per["2022"]["deduction_allowed"]) == D("3000")
    assert D(per["2023"]["st_carry_in"]) == D("12000")
    assert D(per["2023"]["st_carry_out"]) == D("4000")
    assert D(per["2024"]["st_carry_in"]) == D("4000")
    assert D(per["2024"]["st_carry_out"]) == D("1000")
    assert D(per["2024"]["lt_carry_out"]) == D("1000")
    assert D(per["2025"]["st_carry_in"]) == D("1000")
    assert D(per["2025"]["lt_carry_in"]) == D("1000")
    assert D(per["2025"]["st_carry_out"]) == D("0")
    assert D(per["2025"]["lt_carry_out"]) == D("0")
    assert D(per["2025"]["deduction_allowed"]) == D("2000")
    assert D(chain["carry_into_2026"]["st"]) == D("0")
    assert D(chain["carry_into_2026"]["lt"]) == D("0")
    # As-filed applied carryover is zero for 2023-2025 (the omission story).
    for y in (2023, 2024, 2025):
        d = _diag(outdir, y)
        assert D(d["as_filed"]["applied_carryover_total"]) == D("0")
    # 2023 delta: correct deduction 3000 vs as-filed 0 -> refund direction.
    d23 = _diag(outdir, 2023)
    assert D(d23["deltas"]["taxable_income_delta"]) == D("3000")
    assert d23["deltas"]["direction"] == "refund"
    assert d23["deltas"]["tax_change"] is True


def test_low_income_year_line1_negative(tmp_path):
    """Worksheet line 1 < 0: L4 caps the deduction at zero."""
    csvdir = tmp_path / "csvs"
    csvdir.mkdir()
    rows = _sched_d("5000.00", "15000.00", "-10000.00", "0.00")
    fio = _form1040("5000.00", "12950.00")  # line1 = -7950
    _write(csvdir, "return-2022.csv", _return_rows(2022, rows, fio))
    for y in (2023, 2024, 2025):
        _write(csvdir, f"return-{y}.csv",
               _return_rows(y, _sched_d("0.00", "0.00", "0.00", "0.00"),
                            _form1040("80000.00", "12950.00")))
    outdir = tmp_path / "packets"
    assert _run_chain(csvdir, outdir) == 0
    chain = json.loads((outdir / "chain.json").read_text(encoding="utf-8"))
    p22 = chain["per_year"]["2022"]
    assert p22["deduction_allowed"] == "0"  # L4, not line-21's 3000
    assert p22["st_carry_out"] == "10000.00"
    d22 = _diag(outdir, 2022)
    assert d22["correct"]["worksheet_lines"]["L1_taxable_income"] == "-7950.00"


def test_wash_sale_seed_sheet(tmp_path):
    """Wash-sale disallowed loss flows through the seed into 2022 ST."""
    csvdir = tmp_path / "csvs"
    csvdir.mkdir()
    # Filed 2022 carries the wash adjustment as a printed adjustment.
    rows = [
        ("Short term basis sale amount", "10000.00"),
        ("Short term basis cost amount", "25000.00"),
        ("Short term basis adjustments", "2000.00"),
        ("Net short-term gain/loss", "-13000.00"),
        ("Net long-term gain/loss", "0.00"),
    ]
    _write(csvdir, "return-2022.csv",
           _return_rows(2022, rows, _form1040("80000.00", "12950.00")))
    for y in (2023, 2024, 2025):
        _write(csvdir, f"return-{y}.csv",
               _return_rows(y, _sched_d("0.00", "0.00", "0.00", "0.00"),
                            _form1040("80000.00", "12950.00")))
    seed = tmp_path / "seed.csv"
    with open(seed, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["year", "payer_ein", "acct_id", "person", "box",
                    "proceeds", "cost_basis", "wash_sale_disallowed", "net",
                    "term", "source_sha16", "corrected"])
        w.writerow(["2022", "11-1111111", "a1", "person-1", "A",
                    "10000.00", "25000.00", "2000.00", "-13000.00",
                    "short", "deadbeef12345678", "false"])
    outdir = tmp_path / "packets"
    rc = run(csv_dir=str(csvdir), out=str(outdir), seed_sheet=str(seed),
             identity_file=None, filing_status="single")
    assert rc == 0
    chain = json.loads((outdir / "chain.json").read_text(encoding="utf-8"))
    # 2022 ST current = -13000 (wash-adjusted); carryout = 10000.
    assert Decimal(chain["per_year"]["2022"]["st_carry_out"]) == Decimal("10000")
    d22 = _diag(outdir, 2022)
    assert d22["seed_vs_filed_2022"]["mismatched_categories"] == []


def test_8814_present_indicator(tmp_path):
    csvdir = _base_four_years(tmp_path / "csvs")
    # Append an 8814 label to the 2023 return.
    p = csvdir / "return-2023.csv"
    text = p.read_text(encoding="utf-8")
    text += "Form 8814 Parents Election To Report Childs Interest,0.00\n"
    p.write_text(text, encoding="utf-8")
    outdir = tmp_path / "packets"
    assert _run_chain(csvdir, outdir) == 0
    d23 = _diag(outdir, 2023)
    assert "f8814" in d23["attached_forms"]


# ---------------------------------------------------------------------------
# W&I partial cross-check.
# ---------------------------------------------------------------------------

def _wi_csv(year, proceeds_rows):
    rows = [(f"# Wage and Income Transcript {year}", "")]
    rows.append(("# Payer block", ""))
    rows.extend(proceeds_rows)
    return rows


def test_wi_crosscheck_pass_and_fail(tmp_path):
    csvdir = _base_four_years(tmp_path / "csvs")
    _write(csvdir, "wi-2022.csv",
           _wi_csv(2022, [("1099-B Proceeds", "9000.00")]))
    seed = tmp_path / "seed.csv"
    with open(seed, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["year", "payer_ein", "acct_id", "person", "box",
                    "proceeds", "cost_basis", "wash_sale_disallowed", "net",
                    "term", "source_sha16", "corrected"])
        w.writerow(["2022", "11-1111111", "a1", "person-1", "A",
                    "10000.00", "25000.00", "0.00", "-15000.00",
                    "short", "deadbeef12345678", "false"])
    outdir = tmp_path / "packets"
    rc = run(csv_dir=str(csvdir), out=str(outdir), seed_sheet=str(seed),
             identity_file=None, filing_status="single")
    assert rc == 0  # 9000 <= 10000
    d22 = _diag(outdir, 2022)
    assert d22["wi_crosscheck"]["status"] == "pass"

    # Now make W&I exceed the seed: must fail.
    _write(csvdir, "wi-2022.csv",
           _wi_csv(2022, [("1099-B Proceeds", "11000.00")]))
    outdir2 = tmp_path / "packets2"
    rc = run(csv_dir=str(csvdir), out=str(outdir2), seed_sheet=str(seed),
             identity_file=None, filing_status="single")
    assert rc == 1
    d22b = json.loads((outdir2 / "2022" / "diagnostic.json")
                      .read_text(encoding="utf-8"))
    assert d22b["wi_crosscheck"]["status"] == "fail"


def test_wi_crosscheck_skipped_without_seed(tmp_path):
    csvdir = _base_four_years(tmp_path / "csvs")
    _write(csvdir, "wi-2023.csv",
           _wi_csv(2023, [("1099-B Proceeds", "100.00")]))
    outdir = tmp_path / "packets"
    assert _run_chain(csvdir, outdir) == 0
    d23 = _diag(outdir, 2023)
    assert d23["wi_crosscheck"]["status"] == "skip"

# ---------------------------------------------------------------------------
# Blind-safety: stdout/stderr carry no monetary or identity values.
# ---------------------------------------------------------------------------

def test_blind_safe_stdout(tmp_path, capsys):
    csvdir = _base_four_years(tmp_path / "csvs")
    outdir = tmp_path / "packets"
    rc = _run_chain(csvdir, outdir)
    assert rc == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    out = captured.out
    # Distinctive fixture values must never appear on stdout.
    for token in ("10000.00", "25000.00", "-15000.00", "80000.00",
                  "12950.00", "90000.00", "13850.00", "67050.00"):
        assert token not in out, token
    # But the allowed surface does appear.
    assert "check no_engine_fallback: pass" in out
    assert "years: 2022,2023,2024,2025" in out
    assert "summary:" in out


def test_blind_safe_error_paths(tmp_path, capsys):
    csvdir = tmp_path / "csvs"
    csvdir.mkdir()
    # Malformed prefixed row carrying a value: the parse error must not
    # echo the value.
    p = csvdir / "return-2022.csv"
    p.write_text("label,value\n# Return Transcript 2022,99999.99\n",
                 encoding="utf-8")
    outdir = tmp_path / "packets"
    rc = _run_chain(csvdir, outdir)
    assert rc == 1
    captured = capsys.readouterr()
    assert "99999.99" not in captured.err
    assert "[redacted]" in captured.err


# ---------------------------------------------------------------------------
# (d): the chain path runs without heavy third-party imports.
# ---------------------------------------------------------------------------

def test_chain_stdlib_only_subprocess(tmp_path):
    csvdir = _base_four_years(tmp_path / "csvs")
    outdir = tmp_path / "packets"
    code = (
        "import sys\n"
        "class _Blocker:\n"
        "    _BLOCKED = {'pdfplumber', 'pdf2image', 'pypdf'}\n"
        "    def find_spec(self, name, path=None, target=None):\n"
        "        if name.split('.')[0] in self._BLOCKED:\n"
        "            raise ImportError('blocked for stdlib audit: ' + name)\n"
        "        return None\n"
        "sys.meta_path.insert(0, _Blocker())\n"
        "sys.argv = ['taxprep', 'chain', '--csv-dir', %r, '--out', %r,\n"
        "            '--filing-status', 'single']\n"
        "from taxprep.cli import main\n"
        "raise SystemExit(main())\n"
    ) % (str(csvdir), str(outdir))
    proc = subprocess.run([sys.executable, "-c", code],
                          cwd=str(REPO), capture_output=True, text=True,
                          timeout=120)
    assert proc.returncode == 0, proc.stderr
    assert (outdir / "chain.json").exists()


# ---------------------------------------------------------------------------
# Failure modes are loud, never silent.
# ---------------------------------------------------------------------------

def test_engine_fallback_is_failed_check(tmp_path):
    """A year missing QBI: line 1 underivable -> FAILED check, exit 1."""
    csvdir = tmp_path / "csvs"
    csvdir.mkdir()
    rows = _sched_d("0.00", "0.00", "0.00", "0.00")
    fio = [("Adjusted gross income", "80000.00"),
           ("Standard deduction", "12950.00"),
           ("# Form 1040 continued", ""),
           ("Taxable income", "67050.00")]  # no QBI row
    _write(csvdir, "return-2022.csv",
           _return_rows(2022, rows, fio))
    for y in (2023, 2024, 2025):
        _write(csvdir, f"return-{y}.csv",
               _return_rows(y, _sched_d("0.00", "0.00", "0.00", "0.00"),
                            _form1040("80000.00", "12950.00")))
    outdir = tmp_path / "packets"
    rc = _run_chain(csvdir, outdir)
    assert rc == 1
    assert not (outdir / "chain.json").exists()  # never half-computed
    d22 = _diag(outdir, 2022)
    assert any(c["name"] == "no_engine_fallback" and c["status"] == "fail"
               for c in d22["checks"])


def test_as_filed_carryover_nonzero_fails(tmp_path):
    """2023 as-filed applied carryover != 0 contradicts the omission story."""
    csvdir = _base_four_years(tmp_path / "csvs")
    p = csvdir / "return-2023.csv"
    text = p.read_text(encoding="utf-8")
    text = text.replace("Net short-term gain/loss,5000.00",
                        "Net short-term gain/loss,7000.00")
    p.write_text(text, encoding="utf-8")
    outdir = tmp_path / "packets"
    rc = _run_chain(csvdir, outdir)
    assert rc == 1
    d23 = _diag(outdir, 2023)
    assert any(c["name"] == "as_filed_carryover_zero_2023"
               and c["status"] == "fail" for c in d23["checks"])


def test_duplicate_return_csv_fails_loud(tmp_path):
    csvdir = _base_four_years(tmp_path / "csvs")
    import shutil
    shutil.copy(csvdir / "return-2023.csv", csvdir / "return-2023-dup.csv")
    outdir = tmp_path / "packets"
    rc = _run_chain(csvdir, outdir)
    assert rc == 1


def test_missing_return_csv_fails_loud(tmp_path):
    csvdir = _base_four_years(tmp_path / "csvs")
    (csvdir / "return-2024.csv").unlink()
    outdir = tmp_path / "packets"
    rc = _run_chain(csvdir, outdir)
    assert rc == 1


def test_unmatched_labels_reported_by_text(tmp_path, capsys):
    csvdir = _base_four_years(tmp_path / "csvs")
    p = csvdir / "return-2023.csv"
    text = p.read_text(encoding="utf-8")
    text = text.replace("# Form 1040",
                        "Short term frobnicate amount,12.34\n# Form 1040")
    p.write_text(text, encoding="utf-8")
    outdir = tmp_path / "packets"
    assert _run_chain(csvdir, outdir) == 0
    captured = capsys.readouterr()
    assert "unmatched_labels_2023: sched_d=1 form1040=0" in captured.out
    assert "12.34" not in captured.out  # value stays out of stdout
    d23 = _diag(outdir, 2023)
    assert ("Short term frobnicate amount"
            in d23["as_filed"]["unmatched_sched_d_labels"])


def test_identity_rows_skipped(tmp_path):
    csvdir = _base_four_years(tmp_path / "csvs")
    p = csvdir / "return-2023.csv"
    text = p.read_text(encoding="utf-8")
    text += ("# Taxpayer Name And Address,,\n"
             "Short term basis sale amount,99999.99\n")
    p.write_text(text, encoding="utf-8")
    ident = tmp_path / "identity.txt"
    ident.write_text("Taxpayer Name And Address\n", encoding="utf-8")
    outdir = tmp_path / "packets"
    rc = run(csv_dir=str(csvdir), out=str(outdir), seed_sheet=None,
             identity_file=str(ident), filing_status="single")
    assert rc == 0
    d23 = _diag(outdir, 2023)
    # The identity-section row must not have entered the math.
    assert d23["as_filed"]["inputs_st"] == "5000.00"


def test_per_computer_mismatch_counted(tmp_path):
    csvdir = _base_four_years(tmp_path / "csvs")
    p = csvdir / "return-2023.csv"
    text = p.read_text(encoding="utf-8")
    text = text.replace("# Form 1040",
                        "Net short-term gain/loss PER COMPUTER,5001.00\n"
                        "# Form 1040")
    p.write_text(text, encoding="utf-8")
    outdir = tmp_path / "packets"
    assert _run_chain(csvdir, outdir) == 0
    d23 = _diag(outdir, 2023)
    assert d23["per_computer_mismatches"]["count"] == 1
    assert d23["per_computer_mismatches"]["labels"] == [
        "Net short-term gain/loss"]


def test_out_dir_and_file_permissions(tmp_path):
    csvdir = _base_four_years(tmp_path / "csvs")
    outdir = tmp_path / "packets"
    assert _run_chain(csvdir, outdir) == 0
    assert stat.S_IMODE(os.stat(outdir).st_mode) == 0o700
    f = outdir / "2023" / "diagnostic.json"
    assert stat.S_IMODE(os.stat(f).st_mode) == 0o600


def test_seed_sheet_bad_columns_fail_loud(tmp_path):
    csvdir = _base_four_years(tmp_path / "csvs")
    seed = tmp_path / "seed.csv"
    seed.write_text("year,box\n2022,A\n", encoding="utf-8")
    outdir = tmp_path / "packets"
    rc = run(csv_dir=str(csvdir), out=str(outdir), seed_sheet=str(seed),
             identity_file=None, filing_status="single")
    assert rc == 1


def test_seed_vs_filed_mismatch_fails_loud(tmp_path):
    """2022 seed disagreeing with as-filed lots fails the run by name."""
    csvdir = _base_four_years(tmp_path / "csvs")
    seed = tmp_path / "seed.csv"
    with open(seed, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["year", "payer_ein", "acct_id", "person", "box",
                    "proceeds", "cost_basis", "wash_sale_disallowed", "net",
                    "term", "source_sha16", "corrected"])
        # Filed 2022 ST basis net is -15000; seed says -13000.
        w.writerow(["2022", "11-1111111", "a1", "person-1", "A",
                    "10000.00", "25000.00", "2000.00", "-13000.00",
                    "short", "deadbeef12345678", "false"])
    outdir = tmp_path / "packets"
    rc = run(csv_dir=str(csvdir), out=str(outdir), seed_sheet=str(seed),
             identity_file=None, filing_status="single")
    assert rc == 1
    d22 = _diag(outdir, 2022)
    assert d22["seed_vs_filed_2022"]["mismatched_categories"] == ["st_basis"]
    assert any(c["name"] == "seed_vs_filed_2022" and c["status"] == "fail"
               for c in d22["checks"])
