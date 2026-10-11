"""R24(c): taxprep packet — per-year 1040-X entry packets. Synthetic only.

Builds real (a) packets with taxprep.chain.run, then feeds them to
taxprep.packet.run and asserts known answers: change-line derivation,
column-A variant marking, 8814 note, CA operator-filled section, DoD
checklist, blind-safe stdout, and stdlib-only importability.
"""
from __future__ import annotations

import csv
import io
import json
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest

from taxprep.chain import run as run_chain
from taxprep.packet import run as run_packet

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


def _sched_d(st_sale, st_cost, st_net, lt_net):
    return [
        ("Short term basis sale amount", st_sale),
        ("Short term basis cost amount", st_cost),
        ("Net short-term gain/loss", st_net),
        ("Net long-term gain/loss", lt_net),
    ]


def _form1040(agi, ded, withholding="6000.00", per_computer_agi=None):
    rows = [
        ("Adjusted gross income", agi),
        ("Standard deduction", ded),
        ("Qualified business income deduction", "0.00"),
        ("Taxable income", "0.00"),
        ("Total tax", "5000.00"),
        ("Federal income tax withholding", withholding),
    ]
    if per_computer_agi is not None:
        rows.append(("Adjusted gross income PER COMPUTER", per_computer_agi))
    return rows


def _write(dirpath, name, rows):
    p = Path(dirpath) / name
    p.write_text(_csv_text(rows), encoding="utf-8")
    return p


def _four_years(csvdir, per_computer_agi=None, f8814_year=None):
    """Consistent fixture: as-filed applied carryover is 0 every year."""
    csvdir = Path(csvdir)
    csvdir.mkdir(parents=True, exist_ok=True)
    specs = {
        # sale, cost, net_st, net_lt, agi, ded
        2022: (("10000.00", "25000.00", "-15000.00", "0.00"),
               ("80000.00", "12950.00")),
        2023: (("15000.00", "10000.00", "5000.00", "0.00"),
               ("90000.00", "13850.00")),
        2024: (("4000.00", "5000.00", "-1000.00", "0.00"),
               ("95000.00", "14600.00")),
        2025: (("0.00", "0.00", "0.00", "0.00"),
               ("100000.00", "15000.00")),
    }
    for y, (sd, f) in specs.items():
        extra = []
        if y == f8814_year:
            extra.append(("# Form 8814 Parents Election", ""))
        pc = per_computer_agi if y == 2023 else None
        _write(csvdir, f"return-{y}.csv",
               _return_rows(y, _sched_d(*sd),
                            _form1040(f[0], f[1], per_computer_agi=pc),
                            extra=extra))
    return csvdir


def _run_all(csvdir, outdir, **kw):
    rc = run_chain(csv_dir=str(csvdir), out=str(outdir), seed_sheet=None,
                   identity_file=None, filing_status="single")
    assert rc == 0, "chain fixture must pass"
    return run_packet(packets_dir=str(outdir), csv_dir=str(csvdir),
                      out=None, identity_file=None, **kw)


def _packet(outdir, year):
    return json.loads((Path(outdir) / str(year) / "packet.json")
                     .read_text(encoding="utf-8"))


def _line(packet, lid):
    return next(ln for ln in packet["change_lines"] if ln["id"] == lid)


# ---------------------------------------------------------------------------
# Known answers: 2023 change lines.
# Chain: 2022 st_carry_out=12000 -> 2023 st_carry_in=12000.
# 2023 as-filed: inputs_st=5000, net_st=5000, applied=0.
# ---------------------------------------------------------------------------

def test_2023_change_lines_known_answers(tmp_path):
    csvdir = _four_years(tmp_path / "csvs")
    outdir = tmp_path / "packets"
    assert _run_all(csvdir, outdir) == 0
    p = _packet(outdir, 2023)
    assert p["packet_type"] == "1040x_entry"
    assert p["blockers"] == []

    D = Decimal
    l6 = _line(p, "schd_6")
    assert (D(l6["a"]), D(l6["b"]), D(l6["c"])) == (D("0"), D("-12000"), D("-12000"))
    assert l6["direction"] == "decrease"
    l14 = _line(p, "schd_14")
    assert (D(l14["a"]), D(l14["b"]), D(l14["c"])) == (D("0"), D("0"), D("0"))
    assert l14["direction"] == "none"
    l7 = _line(p, "schd_7")
    assert (D(l7["a"]), D(l7["b"]), D(l7["c"])) == (D("5000"), D("-12000"), D("-7000"))
    l16 = _line(p, "schd_16")
    assert (D(l16["a"]), D(l16["b"]), D(l16["c"])) == (D("5000"), D("-12000"), D("-7000"))
    l21 = _line(p, "schd_21")
    # As-filed L16 is a gain -> L21 = L16; correct L16 is a loss -> capped.
    assert (D(l21["a"]), D(l21["b"]), D(l21["c"])) == (D("5000"), D("-8000"), D("-3000"))
    assert l21["direction"] == "decrease"
    f7 = _line(p, "f1040_7")
    assert (f7["a"], f7["b"], f7["c"]) == (l21["a"], l21["b"], l21["c"])
    assert "return construction" in f7["derivation"]

    assert p["overall"]["direction"] == "refund"
    assert p["overall"]["tax_change"] is True
    aff = {a["code"]: a for a in p["affected_1040x_lines"]}
    assert D(aff["L1"]["delta"]) == D("-8000")
    assert aff["L6/L11"]["delta"] is None  # tax recomputed in software


def test_2024_change_lines_known_answers(tmp_path):
    csvdir = _four_years(tmp_path / "csvs")
    outdir = tmp_path / "packets"
    assert _run_all(csvdir, outdir) == 0
    p = _packet(outdir, 2024)
    D = Decimal
    # 2024: st_carry_in=4000 (2023 st_carry_out), inputs_st=-1000.
    l6 = _line(p, "schd_6")
    assert (D(l6["a"]), D(l6["c"])) == (D("0"), D("-4000"))
    l7 = _line(p, "schd_7")
    assert (D(l7["a"]), D(l7["c"])) == (D("-1000"), D("-5000"))
    l21 = _line(p, "schd_21")
    assert (D(l21["a"]), D(l21["c"])) == (D("-1000"), D("-3000"))


def test_2022_seed_packet_not_1040x(tmp_path):
    csvdir = _four_years(tmp_path / "csvs")
    outdir = tmp_path / "packets"
    assert _run_all(csvdir, outdir) == 0
    p = _packet(outdir, 2022)
    assert p["packet_type"] == "seed_diagnostic"
    assert "change_lines" not in p
    assert Decimal(p["correct"]["st_carry_in"]) == Decimal("0")
    assert Decimal(p["correct"]["st_carry_out"]) == Decimal("12000")
    md = (Path(outdir) / "2022" / "packet.md").read_text(encoding="utf-8")
    assert "no 1040-X is prepared for 2022" in md


# ---------------------------------------------------------------------------
# Column-A sheet: variant marking.
# ---------------------------------------------------------------------------

def test_column_a_values_and_variants(tmp_path):
    csvdir = _four_years(tmp_path / "csvs")
    outdir = tmp_path / "packets"
    assert _run_all(csvdir, outdir) == 0
    p = _packet(outdir, 2023)
    by_code = {r["code"]: r for r in p["column_a"]}
    assert by_code["L1"]["value"] == "90000.00"
    assert by_code["L1"]["variant"] == "as_entered"
    assert by_code["L12"]["value"] == "6000.00"
    # L2 has no transcript key in COLUMN_A_LINES.
    assert by_code["L2"]["variant"] == "not_in_transcript_scope"
    assert by_code["L2"]["value"] is None
    # Keys outside (a)'s 1040 vocabulary are not_in_transcript_scope.
    assert by_code["L13"]["variant"] == "not_in_transcript_scope"
    assert p["n_column_a_valued"] == sum(
        1 for r in p["column_a"] if r["value"] is not None)


def test_per_computer_variant_wins_and_marked(tmp_path):
    csvdir = _four_years(tmp_path / "csvs", per_computer_agi="90500.00")
    outdir = tmp_path / "packets"
    assert _run_all(csvdir, outdir) == 0
    p = _packet(outdir, 2023)
    l1 = next(r for r in p["column_a"] if r["code"] == "L1")
    assert l1["value"] == "90500.00"
    assert l1["variant"] == "per_computer (differs from as-entered)"


def test_no_csv_dir_column_a_unavailable_loud(tmp_path):
    csvdir = _four_years(tmp_path / "csvs")
    outdir = tmp_path / "packets"
    rc = run_chain(csv_dir=str(csvdir), out=str(outdir), seed_sheet=None,
                   identity_file=None, filing_status="single")
    assert rc == 0
    rc2 = run_packet(packets_dir=str(outdir), csv_dir=None, out=None,
                     identity_file=None)
    assert rc2 == 1  # blockers: column-A unavailable
    p = _packet(outdir, 2023)
    assert p["column_a"][0]["variant"] == "unavailable_no_csv_dir"
    assert any("column-A sheet unavailable" in b for b in p["blockers"])


# ---------------------------------------------------------------------------
# 8814 note, CA section, Part II, DoD checklist.
# ---------------------------------------------------------------------------

def test_f8814_note_present_and_absent(tmp_path):
    csvdir = _four_years(tmp_path / "csvs", f8814_year=2024)
    outdir = tmp_path / "packets"
    assert _run_all(csvdir, outdir) == 0
    assert _packet(outdir, 2024)["f8814_note"] is not None
    assert "No action" in _packet(outdir, 2024)["f8814_note"]
    assert _packet(outdir, 2023)["f8814_note"] is None


def test_ca_schedule_x_operator_filled(tmp_path):
    csvdir = _four_years(tmp_path / "csvs")
    outdir = tmp_path / "packets"
    assert _run_all(csvdir, outdir) == 0
    ca = _packet(outdir, 2023)["ca_schedule_x"]
    assert ca["status"] == "operator_filled"
    assert "Operator" in ca["note"]


def test_part2_and_dod_checklist(tmp_path):
    csvdir = _four_years(tmp_path / "csvs")
    outdir = tmp_path / "packets"
    assert _run_all(csvdir, outdir) == 0
    p = _packet(outdir, 2023)
    assert "2023" in p["part2_explanation"]
    assert "12000.00" in p["part2_explanation"]
    assert "[Operator:" in p["part2_explanation"]
    assert len(p["dod_checklist"]) == 8
    md = (Path(outdir) / "2023" / "packet.md").read_text(encoding="utf-8")
    assert "1040-X entry packet" in md
    assert "Definition of done" in md
    assert "[ ]" in md


# ---------------------------------------------------------------------------
# Failure modes are loud, never silent.
# ---------------------------------------------------------------------------

def test_missing_diagnostic_fails_loud(tmp_path, capsys):
    outdir = tmp_path / "packets"
    outdir.mkdir()
    rc = run_packet(packets_dir=str(outdir), csv_dir=None, out=None,
                    identity_file=None)
    assert rc == 1
    assert "diagnostic.json not found" in capsys.readouterr().err


def test_correct_none_gives_blockers(tmp_path):
    csvdir = _four_years(tmp_path / "csvs")
    outdir = tmp_path / "packets"
    rc = run_chain(csv_dir=str(csvdir), out=str(outdir), seed_sheet=None,
                   identity_file=None, filing_status="single")
    assert rc == 0
    diag_path = Path(outdir) / "2023" / "diagnostic.json"
    diag = json.loads(diag_path.read_text(encoding="utf-8"))
    diag["correct"] = None
    diag["deltas"] = None
    diag_path.write_text(json.dumps(diag), encoding="utf-8")
    rc2 = run_packet(packets_dir=str(outdir), csv_dir=str(csvdir), out=None,
                     identity_file=None)
    assert rc2 == 1
    p = _packet(outdir, 2023)
    assert p["change_lines"] == []
    assert any("correct chain unavailable" in b for b in p["blockers"])


# ---------------------------------------------------------------------------
# Blind safety: stdout carries no values.
# ---------------------------------------------------------------------------

def test_stdout_carries_no_values(tmp_path, capsys):
    csvdir = _four_years(tmp_path / "csvs")
    outdir = tmp_path / "packets"
    rc = run_chain(csv_dir=str(csvdir), out=str(outdir), seed_sheet=None,
                   identity_file=None, filing_status="single")
    assert rc == 0
    capsys.readouterr()  # drain chain output
    rc2 = run_packet(packets_dir=str(outdir), csv_dir=str(csvdir), out=None,
                     identity_file=None)
    assert rc2 == 0
    out = capsys.readouterr().out
    for secret in ("90000.00", "12000.00", "80000.00", "-7000.00"):
        assert secret not in out, f"value leaked to stdout: {secret}"
    assert "packet 2023" in out


# ---------------------------------------------------------------------------
# (d): the packet path runs without heavy third-party imports.
# ---------------------------------------------------------------------------

def test_packet_stdlib_only_subprocess(tmp_path):
    csvdir = _four_years(tmp_path / "csvs")
    outdir = tmp_path / "packets"
    rc = run_chain(csv_dir=str(csvdir), out=str(outdir), seed_sheet=None,
                   identity_file=None, filing_status="single")
    assert rc == 0
    code = (
        "import sys\n"
        "class _Blocker:\n"
        "    _BLOCKED = {'pdfplumber', 'pdf2image', 'pypdf'}\n"
        "    def find_spec(self, name, path=None, target=None):\n"
        "        if name.split('.')[0] in self._BLOCKED:\n"
        "            raise ImportError('blocked for stdlib audit: ' + name)\n"
        "        return None\n"
        "sys.meta_path.insert(0, _Blocker())\n"
        "sys.argv = ['taxprep', 'packet', '--packets-dir', %r,\n"
        "            '--csv-dir', %r]\n"
        "from taxprep.cli import main\n"
        "raise SystemExit(main())\n"
    ) % (str(outdir), str(csvdir))
    proc = subprocess.run([sys.executable, "-c", code],
                          cwd=str(REPO), capture_output=True, text=True,
                          timeout=120)
    assert proc.returncode == 0, proc.stderr
    assert (Path(outdir) / "2023" / "packet.json").exists()
