"""R24 rev1 (part a): section tracking on the REAL format-v2 structure.

Synthetic fixtures only. The CSVs below reproduce the heading layout
observed on real format-v2 Return Transcripts:

  data rows before the first heading ('Filing status', ...)
  level-1 'Income' / 'Adjustments to Income' / 'Tax and Credits' /
          'Other Taxes' / 'Payments' / 'Refund or Amount Owed' /
          'Third Party Designee'
  level-1 'Schedule C - Profit or Loss From Business (Occurrence #: 1)'
          with LEVEL-2 'Income' and 'Expenses'
  level-1 'SCHEDULE D - CAPITAL GAINS AND LOSSES' with LEVEL-2
          'SHORT TERM CAPITAL GAINS AND LOSSES',
          'LONG TERM CAPITAL GAINS AND LOSSES',
          'TAX COMPUTATION USING MAXIMUM CAPITAL GAINS RATES'
  level-1 'SCHEDULE SE--SELF-EMPLOYMENT TAX (OCCURRENCE #: 1)'

Before rev1 every heading (level 2 included) reset the section and only
headings containing '1040' opened the 1040 section, so real data yielded
zero Schedule D keys and no AGI/deduction/QBI rows.
"""
from __future__ import annotations

import csv
import io
import json
from decimal import Decimal
from pathlib import Path

from taxprep.chain import run

# Known-answer chain (same Schedule D numbers as test_r24_chain, MFJ):
#   2022 ST -15000 -> deduction 3000, ST carryout 12000
#   2023 ST +5000  -> ST carryout 4000
#   2024 LT -1000  -> ST carryout 1000, LT carryout 1000
#   2025 zeros     -> deduction 2000, carry into 2026 = 0
_SCHED_D = {
    2022: dict(st_sale="10000.00", st_cost="25000.00", st_net="-15000.00",
               lt_sale="0.00", lt_cost="0.00", lt_net="0.00"),
    2023: dict(st_sale="15000.00", st_cost="10000.00", st_net="5000.00",
               lt_sale="0.00", lt_cost="0.00", lt_net="0.00"),
    2024: dict(st_sale="0.00", st_cost="0.00", st_net="0.00",
               lt_sale="4000.00", lt_cost="5000.00", lt_net="-1000.00"),
    2025: dict(st_sale="0.00", st_cost="0.00", st_net="0.00",
               lt_sale="0.00", lt_cost="0.00", lt_net="0.00"),
}
# AGI / deduction / QBI per year; the printed 'Taxable income' row is
# deliberately NOT equal to AGI - deduction - QBI so the test can prove
# worksheet line 1 is derived, never read from the floored line.
_FORM1040 = {
    2022: dict(agi="80000.00", ded="25900.00", qbi="1000.00",
               ti_printed="53000.00", line1="53100.00"),
    2023: dict(agi="90000.00", ded="27700.00", qbi="1000.00",
               ti_printed="61200.00", line1="61300.00"),
    2024: dict(agi="95000.00", ded="29200.00", qbi="1000.00",
               ti_printed="64700.00", line1="64800.00"),
    2025: dict(agi="100000.00", ded="30000.00", qbi="1000.00",
               ti_printed="68900.00", line1="69000.00"),
}

SCHED_C_INCOME_LABEL = "Gross receipts or sales"


def _csv_text(rows):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["label", "value"])
    for label, value in rows:
        w.writerow([label, value])
    return buf.getvalue()


def _real_return_rows(year, *, filing_status="Married Filing Joint",
                      with_status=True):
    d = _SCHED_D[year]
    f = _FORM1040[year]
    rows = [("@page 1", "")]
    if with_status:
        rows.append(("Filing status", filing_status))
    rows += [
        ("Form number", "1040"),
        ("# Income", ""),
        ("Wages, salaries, tips, etc", "50000.00"),
        ("Taxable interest income", "100.00"),
        ("Total income", f["agi"]),
        ("# Adjustments to Income", ""),
        ("Adjusted gross income", f["agi"]),
        ("Adjusted gross income per computer", f["agi"]),
        ("# Tax and Credits", ""),
        ("Standard deduction per computer", f["ded"]),
        ("Total itemized or standard deduction", f["ded"]),
        ("Qualified business income deduction", f["qbi"]),
        ("Taxable income", f["ti_printed"]),
        ("Taxable income per computer", f["ti_printed"]),
        ("Tentative tax", "6000.00"),
        ("# Other Taxes", ""),
        ("Total tax liability tp figures per computer", "7000.00"),
        ("# Payments", ""),
        ("Federal income tax withheld", "8000.00"),
        ("# Refund or Amount Owed", ""),
        ("Refund amount", "1000.00"),
        ("# Third Party Designee", ""),
        ("Designee authorization", "No"),
        ("@page 2", ""),
        ("# Schedule C - Profit or Loss From Business (Occurrence #: 1)", ""),
        ("## Income", ""),
        (SCHED_C_INCOME_LABEL, "20000.00"),
        ("Total income", "20000.00"),
        # Decoy: a 1040-pattern label inside the Schedule C level-2
        # 'Income' section. Mis-attribution would double QBI.
        ("Qualified business income", "15000.00"),
        ("## Expenses", ""),
        ("Total expenses", "5000.00"),
        ("Net profit or loss", "15000.00"),
        ("# SCHEDULE D - CAPITAL GAINS AND LOSSES", ""),
        ("## SHORT TERM CAPITAL GAINS AND LOSSES", ""),
        ("Short term basis sale amount", d["st_sale"]),
        ("Short term basis cost amount", d["st_cost"]),
        ("Short term basis adjustments", "0.00"),
        ("Net short-term gain/loss", d["st_net"]),
        ("## LONG TERM CAPITAL GAINS AND LOSSES", ""),
        ("Long term basis sale amount", d["lt_sale"]),
        ("Long term basis cost amount", d["lt_cost"]),
        ("Long term basis adjustments", "0.00"),
        ("Net long-term gain/loss", d["lt_net"]),
        ("## TAX COMPUTATION USING MAXIMUM CAPITAL GAINS RATES", ""),
        ("Schedule D tax per computer", "0.00"),
        ("# SCHEDULE SE--SELF-EMPLOYMENT TAX (OCCURRENCE #: 1)", ""),
        ("Net earnings from self-employment", "13853.00"),
        ("Self-employment tax", "2000.00"),
    ]
    return rows


def _account_rows(year, *, filing_status="Married Filing Joint"):
    """Account Transcript: repeats AGI / taxable income / filing status."""
    f = _FORM1040[year]
    rows = [
        ("@page 1", ""),
        ("Filing status", filing_status),
        ("Adjusted gross income", f["agi"]),
        ("Taxable income", f["ti_printed"]),
        ("Tax per return", "7000.00"),
        ("# TRANSACTIONS", ""),
    ]
    text = _csv_text(rows)
    text += "CODE,EXPLANATION OF TRANSACTION,CYCLE,DATE,AMOUNT\n"
    text += f"150,Tax return filed,20241505,04-15-{year + 1},7000.00\n"
    text += f"846,Refund issued,,05-01-{year + 1},-1000.00\n"
    return text


def _write_dir(tmp_path, *, with_status=True, account_years=(),
               account_status="Married Filing Joint"):
    csvdir = tmp_path / "csvs"
    csvdir.mkdir()
    for y in (2022, 2023, 2024, 2025):
        (csvdir / f"return-{y}.csv").write_text(
            _csv_text(_real_return_rows(y, with_status=with_status)),
            encoding="utf-8")
    for y in account_years:
        (csvdir / f"account-{y}.csv").write_text(
            _account_rows(y, filing_status=account_status), encoding="utf-8")
    return csvdir


def _run(csvdir, outdir, **kw):
    kw.setdefault("filing_status", None)
    return run(csv_dir=str(csvdir), out=str(outdir), seed_sheet=None,
               identity_file=None, **kw)


def _diag(outdir, year):
    return json.loads((Path(outdir) / str(year) / "diagnostic.json")
                      .read_text(encoding="utf-8"))


def _chain(outdir):
    return json.loads((Path(outdir) / "chain.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# The real structure: nets found, line 1 derived, chain computed, status read.
# ---------------------------------------------------------------------------

def test_real_structure_chain_computed(tmp_path, capsys):
    csvdir = _write_dir(tmp_path)
    outdir = tmp_path / "packets"
    rc = _run(csvdir, outdir)  # no --filing-status: read from the CSVs
    assert rc == 0, capsys.readouterr()
    D = Decimal
    for y, d in _SCHED_D.items():
        diag = _diag(outdir, y)
        # Net ST/LT lines found under the LEVEL-2 Schedule D headings.
        assert D(diag["as_filed"]["net_st"]) == D(d["st_net"])
        assert D(diag["as_filed"]["net_lt"]) == D(d["lt_net"])
        assert D(diag["as_filed"]["inputs_st"]) == \
            D(d["st_sale"]) - D(d["st_cost"])
        assert D(diag["as_filed"]["inputs_lt"]) == \
            D(d["lt_sale"]) - D(d["lt_cost"])
        # Worksheet line 1 = AGI - deduction - QBI, never the printed TI.
        f = _FORM1040[y]
        l1 = diag["correct"]["worksheet_lines"]["L1_taxable_income"]
        assert D(l1) == D(f["line1"])
        assert D(l1) != D(f["ti_printed"])
        # Attached-form flags from the level-1 schedule headings.
        assert {"sch_c", "sch_se"} <= set(diag["attached_forms"])
    chain = _chain(outdir)
    per = chain["per_year"]
    assert D(per["2022"]["st_carry_out"]) == D("12000")
    assert D(per["2022"]["deduction_allowed"]) == D("3000")
    assert D(per["2023"]["st_carry_out"]) == D("4000")
    assert D(per["2024"]["st_carry_out"]) == D("1000")
    assert D(per["2024"]["lt_carry_out"]) == D("1000")
    assert D(per["2025"]["deduction_allowed"]) == D("2000")
    assert D(chain["carry_into_2026"]["st"]) == D("0")
    # Filing status came from the 'Filing status' data row, mapped from
    # the transcript spelling to the engine alias.
    assert chain["filing_status"] == "mfj"
    assert chain["filing_status_source"] == "csv"
    out = capsys.readouterr().out
    assert "filing_status_source: csv" in out
    assert "check no_engine_fallback: pass" in out
    assert "chain: carry_into_2026 computed" in out


def test_level2_income_under_schedule_c_is_not_a_1040_row(tmp_path):
    csvdir = _write_dir(tmp_path)
    outdir = tmp_path / "packets"
    assert _run(csvdir, outdir) == 0
    for y in (2022, 2023, 2024, 2025):
        diag = _diag(outdir, y)
        # Schedule C rows never reach the 1040 scanner: not even as
        # unmatched 1040 labels ...
        assert SCHED_C_INCOME_LABEL not in diag["as_filed"]["unmatched_1040_labels"]
        assert "Total expenses" not in diag["as_filed"]["unmatched_1040_labels"]
        # ... and the decoy 'Qualified business income' did not double QBI
        # (line 1 is exact).
        l1 = diag["correct"]["worksheet_lines"]["L1_taxable_income"]
        assert Decimal(l1) == Decimal(_FORM1040[y]["line1"])
        # The level-1 1040 sections DID feed the scanner (their
        # non-vocabulary rows are reported by label text).
        assert "Wages, salaries, tips, etc" in \
            diag["as_filed"]["unmatched_1040_labels"]


def test_level2_schedule_d_sections_inherit_sched_d(tmp_path):
    """No Schedule D label leaks into the 1040 unmatched list and the
    tax-computation level-2 rows stay out of the chain math."""
    csvdir = _write_dir(tmp_path)
    outdir = tmp_path / "packets"
    assert _run(csvdir, outdir) == 0
    d22 = _diag(outdir, 2022)
    assert d22["as_filed"]["unmatched_sched_d_labels"] == []
    for lbl in ("Short term basis sale amount", "Net long-term gain/loss",
                "Schedule D tax per computer"):
        assert lbl not in d22["as_filed"]["unmatched_1040_labels"]
    assert d22["unmatched_label_counts"]["sched_d"] == 0


# ---------------------------------------------------------------------------
# Account Transcripts: filing status source, no double counting.
# ---------------------------------------------------------------------------

def test_account_transcript_supplies_filing_status(tmp_path):
    csvdir = _write_dir(tmp_path, with_status=False, account_years=(2023,),
                        account_status="Married Filing Separate")
    outdir = tmp_path / "packets"
    assert _run(csvdir, outdir) == 0
    chain = _chain(outdir)
    assert chain["filing_status"] == "mfs"
    assert chain["filing_status_source"] == "csv"
    # MFS annual limit (1500) applied: 2022 deduction is 1500, not 3000.
    assert Decimal(chain["per_year"]["2022"]["deduction_allowed"]) == \
        Decimal("1500")


def test_account_transcript_does_not_double_1040_rows(tmp_path):
    csvdir = _write_dir(tmp_path, account_years=(2022, 2023, 2024, 2025))
    outdir = tmp_path / "packets"
    assert _run(csvdir, outdir) == 0
    for y in (2022, 2023, 2024, 2025):
        diag = _diag(outdir, y)
        assert "account" in diag["file_ids"]
        l1 = diag["correct"]["worksheet_lines"]["L1_taxable_income"]
        assert Decimal(l1) == Decimal(_FORM1040[y]["line1"])
        # Account-transcript rows are not reported as 1040 labels either.
        assert "Tax per return" not in diag["as_filed"]["unmatched_1040_labels"]


def test_filing_status_missing_everywhere_fails_loud(tmp_path, capsys):
    csvdir = _write_dir(tmp_path, with_status=False)
    outdir = tmp_path / "packets"
    assert _run(csvdir, outdir) == 1
    err = capsys.readouterr().err
    assert "filing status not given" in err
    assert not (outdir / "chain.json").exists()


def test_filing_status_flag_wins_over_csv(tmp_path):
    csvdir = _write_dir(tmp_path)  # CSVs say MFJ
    outdir = tmp_path / "packets"
    assert _run(csvdir, outdir, filing_status="single") == 0
    chain = _chain(outdir)
    assert chain["filing_status"] == "single"
    assert chain["filing_status_source"] == "flag"


def test_unrecognized_transcript_status_fails_loud(tmp_path, capsys):
    csvdir = tmp_path / "csvs"
    csvdir.mkdir()
    for y in (2022, 2023, 2024, 2025):
        (csvdir / f"return-{y}.csv").write_text(
            _csv_text(_real_return_rows(y, filing_status="Frobnicated")),
            encoding="utf-8")
    outdir = tmp_path / "packets"
    assert _run(csvdir, outdir) == 1
    err = capsys.readouterr().err
    assert "not recognized" in err
    assert "Frobnicated" not in err  # value never echoed


# ---------------------------------------------------------------------------
# Blind-safety on the real structure + CLI help.
# ---------------------------------------------------------------------------

def test_real_structure_blind_safe_stdout(tmp_path, capsys):
    csvdir = _write_dir(tmp_path, account_years=(2023,))
    outdir = tmp_path / "packets"
    assert _run(csvdir, outdir) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    for token in ("80000.00", "25900.00", "53100.00", "53000.00",
                  "-15000.00", "13853.00", "Married Filing Joint", "mfj"):
        assert token not in captured.out, token


def test_chain_help_documents_csv_dir_scope():
    from taxprep.cli import build_parser
    parser = build_parser()
    sub = next(a for a in parser._actions
               if a.__class__.__name__ == "_SubParsersAction")
    text = sub.choices["chain"].format_help()
    assert "only 2022-2025 files" in text
    assert "Return 2022-2025 required" in text
