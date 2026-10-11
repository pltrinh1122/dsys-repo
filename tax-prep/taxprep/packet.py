"""R24(c): per-year 1040-X entry packet builder.

From the R24(a) chain packets (``packets/<year>/diagnostic.json``,
``packets/chain.json``) and, for the column-A sheet, the Operator's
format-v2 transcript CSVs re-scanned with :mod:`taxprep.chain`'s own
machinery, builds one entry packet per amendment year (2023-2025):

- column-A sheet: 1040-X lines 1-23 via ``column_a.COLUMN_A_LINES``,
  as-adjusted values with the PER COMPUTER variant used (and marked)
  wherever as-entered vs PER COMPUTER differ;
- change lines: Schedule D lines 6/14 (carry-in) and derived 7/15/16/21,
  plus Form 1040 line 7, each with as-filed (A), change (B), correct (C)
  and the expected column-C direction;
- Part II explanation template, CA Schedule X section, Form 8814 note,
  definition-of-done checklist.

2022 is the seed year, not an amendment year: it gets a diagnostic-only
packet, never a 1040-X.

Blind-safe: stdout carries only labels, counts, flags, years, file ids,
check names and paths. All values go to ``packet.json`` / ``packet.md``
(0600/0700). Stdlib only at module load (R24(d)); the frozen
``carryforward`` / ``column_a`` semantics are built on, never changed.

Synthetic fixtures only in tests.
"""

from __future__ import annotations

import json
import os
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

from . import chain as _chain_mod
from .column_a import COLUMN_A_LINES

__all__ = ["run", "AMENDMENT_YEARS", "SEED_YEAR"]

AMENDMENT_YEARS = (2023, 2024, 2025)
SEED_YEAR = 2022

# column_a transcript key -> chain.py form1040 key.
# None = the key is outside (a)'s 1040 scan vocabulary.
_KEYMAP = {
    "agi": "agi",
    "taxable_income": "ti",
    "total_tax": "total_tax",
    "withholding": "withholding",
    "estimated_payments": None,
    "total_payments": None,
    "refund": "refund",
    "amount_owed": "owed",
}


class _PacketError(Exception):
    """Loud failure (never a silent partial packet)."""


def _fail(msg: str) -> "NoReturn":
    raise _PacketError(msg)


class _Reporter:
    """Stdout accumulator. Only allow-listed content (no values)."""

    def __init__(self) -> None:
        self.lines: list[str] = []

    def line(self, text: str) -> None:
        self.lines.append(text)

    def emit(self) -> None:
        for ln in self.lines:
            print(ln)


def _dec(raw) -> Decimal:
    try:
        return Decimal(str(raw))
    except (InvalidOperation, ValueError, TypeError):
        _fail(f"non-decimal value in packet input: {raw!r}")


def _fmt(d: Decimal) -> str:
    return format(d, ".2f")


def _direction(a: Decimal, c: Decimal) -> str:
    if c < a:
        return "decrease"
    if c > a:
        return "increase"
    return "none"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=1, sort_keys=True)
        fh.write("\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# Column-A sheet: re-scan the return transcript CSVs with (a)'s machinery.
# ---------------------------------------------------------------------------

def _scan_returns(csv_dir: str, identity_file: str | None) -> dict[int, object]:
    """{year: _YearScan} for return-transcript CSVs. Loud on ambiguity."""
    try:
        files = _chain_mod._discover(Path(csv_dir))
    except Exception as exc:
        _fail(f"column-A scan: {type(exc).__name__}: {exc}")
    identity = _chain_mod._load_identity(identity_file)
    scans: dict[int, object] = {}
    for frec in files:
        if frec["kind"] != "return":
            continue
        y = frec["year"]
        if y in scans:
            _fail(f"column-A scan: duplicate return transcript CSV for "
                  f"tax year {y}")
        scan = _chain_mod._YearScan(y)
        _chain_mod._scan_file(scan, frec, identity)
        scans[y] = scan
    return scans


def _column_a_sheet(scan: object | None) -> list[dict]:
    """1040-X lines 1-23 from a year scan. Variant-marked, never guessed."""
    rows: list[dict] = []
    for code, label, keys in COLUMN_A_LINES:
        entry: dict = {"code": code, "label": label, "value": None,
                       "variant": None, "transcript_key": None}
        if not keys:
            entry["variant"] = "not_in_transcript_scope"
            rows.append(entry)
            continue
        ckey = _KEYMAP.get(keys[0])
        if ckey is None:
            entry["variant"] = "not_in_transcript_scope"
            entry["transcript_key"] = keys[0]
            rows.append(entry)
            continue
        entry["transcript_key"] = keys[0]
        if scan is None:
            entry["variant"] = "unavailable_no_csv_dir"
            rows.append(entry)
            continue
        ae = scan.form1040.get((ckey, "as_entered"), [])
        pc = scan.form1040.get((ckey, "per_computer"), [])
        vae = _chain_mod._sum_vals(ae) if ae else None
        vpc = _chain_mod._sum_vals(pc) if pc else None
        if vae is not None and vpc is not None:
            if vae == vpc:
                entry["value"] = _fmt(vae)
                entry["variant"] = "as_entered (= per_computer)"
            else:
                # Spec: PER COMPUTER wins where the variants differ.
                entry["value"] = _fmt(vpc)
                entry["variant"] = "per_computer (differs from as-entered)"
        elif vae is not None:
            entry["value"] = _fmt(vae)
            entry["variant"] = "as_entered"
        elif vpc is not None:
            entry["value"] = _fmt(vpc)
            entry["variant"] = "per_computer"
        else:
            entry["variant"] = "missing"
        rows.append(entry)
    return rows


# ---------------------------------------------------------------------------
# Change lines from the (a) diagnostic.
# ---------------------------------------------------------------------------

def _change_lines(diag: dict) -> tuple[list[dict], list[str]]:
    """Derive the Sch D / 1040 change lines. Returns (lines, blockers)."""
    blockers: list[str] = []
    correct = diag.get("correct")
    if correct is None:
        return [], ["correct chain unavailable for this year "
                    "(diagnostic 'correct' is null)"]
    af = diag.get("as_filed") or {}
    try:
        net_st = _dec(af["net_st"])
        net_lt = _dec(af["net_lt"])
        inputs_st = _dec(af["inputs_st"])
        inputs_lt = _dec(af["inputs_lt"])
        applied_st = _dec(af["applied_carryover_st"])
        applied_lt = _dec(af["applied_carryover_lt"])
        s_in = _dec(correct["st_carry_in"])      # positive magnitudes
        l_in = _dec(correct["lt_carry_in"])
        l2 = _dec(correct["worksheet_lines"]["L2_deduction"])
        as_filed_ded = _dec(diag["deltas"]["as_filed_deduction_recomputed"])
    except (KeyError, TypeError) as exc:
        return [], [f"diagnostic missing fields for change lines: {exc}"]

    a16 = net_st + net_lt
    c16 = (inputs_st - s_in) + (inputs_lt - l_in)
    a21 = -as_filed_ded if a16 < 0 else a16
    c21 = -l2 if c16 < 0 else c16

    specs = [
        ("schd_6", "Schedule D line 6 — short-term capital loss carryover",
         applied_st, -s_in,
         "as-filed carryover applied (diagnostic); correct = chain ST carry-in"),
        ("schd_14", "Schedule D line 14 — long-term capital loss carryover",
         applied_lt, -l_in,
         "as-filed carryover applied (diagnostic); correct = chain LT carry-in"),
        ("schd_7", "Schedule D line 7 — net short-term gain/loss",
         net_st, inputs_st - s_in,
         "correct = as-filed inputs + correct ST carry-in"),
        ("schd_15", "Schedule D line 15 — net long-term gain/loss",
         net_lt, inputs_lt - l_in,
         "correct = as-filed inputs + correct LT carry-in"),
        ("schd_16", "Schedule D line 16 — combined (7 + 15)",
         a16, c16, "sum of the two lines above"),
        ("schd_21", "Schedule D line 21 — allowable loss deduction",
         a21, c21,
         "as-filed = recomputed as-filed deduction (diagnostic); "
         "correct = chain worksheet L2"),
        ("f1040_7", "Form 1040 line 7 — capital gain or (loss)",
         a21, c21,
         "as-filed 1040 L7 derived = as-filed Sch D L21 (return "
         "construction); correct flows from correct Sch D L21"),
    ]
    lines = []
    for lid, label, a, c, derivation in specs:
        b = c - a
        lines.append({"id": lid, "label": label, "a": _fmt(a), "b": _fmt(b),
                      "c": _fmt(c), "direction": _direction(a, c),
                      "derivation": derivation})
    return lines, blockers

# ---------------------------------------------------------------------------
# Packet assembly.
# ---------------------------------------------------------------------------

def _part2_text(year: int, s_in: Decimal, l_in: Decimal,
                direction: str, ti_delta: Decimal) -> str:
    dir_word = {"refund": "a refund", "owed": "additional tax",
                "none": "no change in tax"}.get(direction, "an uncertain tax effect")
    return (
        f"Amended return to claim a capital loss carryover from 2022 that "
        f"was omitted from the original {year} return.\n"
        f"\n"
        f"The 2022 Schedule D reported a net capital loss. Under the "
        f"Capital Loss Carryover Worksheet, {_fmt(s_in)} of short-term loss "
        f"and {_fmt(l_in)} of long-term loss carried forward to {year}; the "
        f"original {year} return applied no carryover. This amendment "
        f"applies the correct carryover ({_fmt(s_in)} short-term on "
        f"Schedule D line 6, {_fmt(l_in)} long-term on line 14), changing "
        f"net capital gain/loss as shown in the change lines below. "
        f"Taxable income changes by {_fmt(ti_delta)}, resulting in "
        f"{dir_word} (tax recomputed in tax software).\n"
        f"\n"
        f"[Operator: add any additional facts or explanation here.]"
    )


_CA_NOTE = (
    "No California transcript is available in the packet inputs, so the "
    "CA Schedule X mapping is Operator-filled. For each federal change "
    "line above, enter the corresponding California adjustment; California "
    "does not conform to the federal capital-loss carryover in all "
    "respects — verify each line against the FTB instructions. "
    "[Operator: complete.]"
)


def _dod_checklist() -> list[str]:
    return [
        "Column-A values verified against the return transcript (variant markings reviewed)",
        "Carry-in amounts (Schedule D lines 6/14) agree with the chain packet",
        "Change lines entered on Form 1040-X, columns B and C",
        "Tax recomputed in tax software (1040-X lines 6/11); packet does not derive tax",
        "Part II explanation completed and reviewed",
        "CA Schedule X completed (if required)",
        "Refund/owed direction matches the packet's expected direction",
        "Packet values cross-checked in the tax software before filing",
    ]


def _f8814_note(diag: dict) -> str | None:
    forms = diag.get("attached_forms") or []
    if "f8814" in forms:
        return ("Form 8814 was present on this year's return (child's "
                "interest/dividends election). No action in this packet; "
                "the tax software recompute covers it.")
    return None


def _build_amendment_packet(year: int, diag: dict, scans: dict,
                            packets_dir: Path) -> tuple[dict, list[str]]:
    blockers: list[str] = []
    scan = scans.get(year)
    if scan is None:
        blockers.append("column-A sheet unavailable: --csv-dir not given "
                        "or no return transcript for this year")
    column_a = _column_a_sheet(scan)
    n_valued = sum(1 for r in column_a if r["value"] is not None)

    change_lines, cl_blockers = _change_lines(diag)
    blockers.extend(cl_blockers)

    deltas = diag.get("deltas") or {}
    ti_delta = deltas.get("taxable_income_delta")
    direction = deltas.get("direction", "none")
    tax_change = bool(deltas.get("tax_change", False))

    # Affected 1040-X lines. L1 moves 1:1 with the 1040 L7 change, all
    # else equal; L5 moves by the diagnostic's taxable-income delta; tax
    # lines are software-recomputed, never derived here.
    affected: list[dict] = []
    if change_lines:
        b1040_7 = _dec(next(ln["b"] for ln in change_lines
                             if ln["id"] == "f1040_7"))
        affected.append({"code": "L1", "label": "Adjusted gross income",
                         "delta": _fmt(b1040_7),
                         "note": "moves 1:1 with the Form 1040 line 7 "
                                 "change, all else equal"})
    if ti_delta is not None:
        affected.append({"code": "L5", "label": "Taxable income",
                         "delta": _fmt(_dec(ti_delta)),
                         "note": "diagnostic taxable-income delta"})
    affected.append({"code": "L6/L11", "label": "Tax / Total tax",
                     "delta": None,
                     "note": "recompute in tax software; packet does not "
                             "derive tax"})
    affected.append({"code": "L12+", "label": "Withholding and payments",
                     "delta": _fmt(Decimal("0")),
                     "note": "unchanged by the carryover correction"})

    correct = diag.get("correct") or {}
    s_in = _dec(correct.get("st_carry_in", "0"))
    l_in = _dec(correct.get("lt_carry_in", "0"))
    part2 = _part2_text(year, s_in, l_in, direction,
                        _dec(ti_delta) if ti_delta is not None else Decimal("0"))

    packet = {
        "year": year,
        "packet_type": "1040x_entry",
        "generated_from": {
            "diagnostic": f"packets/{year}/diagnostic.json",
            "chain": "packets/chain.json",
            "column_a_csv_dir": bool(scans),
        },
        "column_a": column_a,
        "n_column_a_valued": n_valued,
        "change_lines": change_lines,
        "affected_1040x_lines": affected,
        "overall": {
            "taxable_income_delta": ti_delta,
            "direction": direction,
            "tax_change": tax_change,
        },
        "part2_explanation": part2,
        "ca_schedule_x": {"status": "operator_filled", "note": _CA_NOTE},
        "f8814_note": _f8814_note(diag),
        "dod_checklist": _dod_checklist(),
        "blockers": blockers,
    }
    return packet, blockers


def _build_seed_packet(year: int, diag: dict) -> tuple[dict, list[str]]:
    blockers: list[str] = []
    correct = diag.get("correct")
    if correct is None:
        blockers.append("correct chain unavailable for the seed year")
    packet = {
        "year": year,
        "packet_type": "seed_diagnostic",
        "note": ("2022 is the seed year for the carryover chain; no "
                 "1040-X is prepared for it. This packet carries the "
                 "diagnostic values the amendment years build on."),
        "correct": correct,
        "seed_vs_filed": diag.get("seed_vs_filed_2022"),
        "as_filed": diag.get("as_filed"),
        "blockers": blockers,
    }
    return packet, blockers


def _render_md(packet: dict) -> str:
    y = packet["year"]
    out = [f"# 1040-X entry packet — tax year {y}", ""]
    if packet["packet_type"] == "seed_diagnostic":
        out.append("> Seed year: no 1040-X is prepared for 2022. "
                   "Diagnostic values below feed the amendment years.")
        out.append("")
        out.append("## Correct chain (seed)")
        correct = packet.get("correct") or {}
        for k in ("st_carry_in", "lt_carry_in", "deduction_allowed",
                  "st_carry_out", "lt_carry_out"):
            out.append(f"- {k}: {correct.get(k)}")
        out.append("")
        out.append("## Seed vs as-filed (2022)")
        svf = packet.get("seed_vs_filed") or {}
        out.append(f"- mismatched categories: {svf.get('n_mismatched')}")
        for c in svf.get("mismatched_categories") or []:
            out.append(f"  - {c}")
        out.append("")
    else:
        out.append("## Column A — 1040-X lines 1–23 (as-adjusted transcript)")
        out.append("")
        out.append("| Line | Description | Value | Variant |")
        out.append("|---|---|---|---|")
        for r in packet["column_a"]:
            out.append(f"| {r['code']} | {r['label']} | "
                       f"{r['value'] or '—'} | {r['variant']} |")
        out.append("")
        out.append("## Change lines")
        out.append("")
        out.append("| Line | As filed (A) | Change (B) | Correct (C) | "
                   "Direction |")
        out.append("|---|---|---|---|---|")
        for ln in packet["change_lines"]:
            out.append(f"| {ln['label']} | {ln['a']} | {ln['b']} | "
                       f"{ln['c']} | {ln['direction']} |")
        out.append("")
        for ln in packet["change_lines"]:
            out.append(f"- {ln['id']} derivation: {ln['derivation']}")
        out.append("")
        o = packet["overall"]
        out.append(f"Expected direction: **{o['direction']}** "
                   f"(taxable-income delta {o['taxable_income_delta']}; "
                   f"tax change: {'yes' if o['tax_change'] else 'no'})")
        out.append("")
        out.append("## Affected 1040-X lines")
        out.append("")
        for a in packet["affected_1040x_lines"]:
            out.append(f"- {a['code']} {a['label']}: "
                       f"delta {a['delta'] or 'n/a'} — {a['note']}")
        out.append("")
        out.append("## Part II explanation")
        out.append("")
        out.append(packet["part2_explanation"])
        out.append("")
        out.append("## CA Schedule X")
        out.append("")
        out.append(f"Status: {packet['ca_schedule_x']['status']}")
        out.append("")
        out.append(packet["ca_schedule_x"]["note"])
        out.append("")
        if packet["f8814_note"]:
            out.append("## Form 8814 note")
            out.append("")
            out.append(packet["f8814_note"])
            out.append("")
        out.append("## Definition of done")
        out.append("")
        for i, item in enumerate(packet["dod_checklist"], 1):
            out.append(f"{i}. [ ] {item}")
        out.append("")
    if packet["blockers"]:
        out.append("## BLOCKERS")
        out.append("")
        for b in packet["blockers"]:
            out.append(f"- BLOCKED: {b}")
        out.append("")
    return "\n".join(out)


def _load_diagnostic(packets_dir: Path, year: int) -> dict:
    p = packets_dir / str(year) / "diagnostic.json"
    if not p.is_file():
        _fail(f"packets/{year}/diagnostic.json not found "
              f"(run `taxprep chain` first)")
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except ValueError as exc:
        _fail(f"packets/{year}/diagnostic.json is not valid JSON: {exc}")


def run(*, packets_dir: str, csv_dir: str | None = None,
        out: str | None = None, identity_file: str | None = None) -> int:
    """Build per-year 1040-X entry packets. Returns 0 or 1."""
    rep = _Reporter()
    try:
        return _run_inner(rep, packets_dir=packets_dir, csv_dir=csv_dir,
                          out=out, identity_file=identity_file)
    except _PacketError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        rep.emit()


def _run_inner(rep: _Reporter, *, packets_dir: str, csv_dir: str | None,
               out: str | None, identity_file: str | None) -> int:
    pdir = Path(packets_dir)
    if not pdir.is_dir():
        _fail(f"packets dir is not a directory: {packets_dir}")
    out_dir = Path(out) if out else pdir

    scans: dict[int, object] = {}
    if csv_dir:
        scans = _scan_returns(csv_dir, identity_file)
        rep.line(f"column-A: scanned return transcripts for years "
                 f"{','.join(str(y) for y in sorted(scans))}")
    else:
        rep.line("column-A: no --csv-dir; sheet marked unavailable")

    n_blocked = 0
    for year in (SEED_YEAR,) + AMENDMENT_YEARS:
        diag = _load_diagnostic(pdir, year)
        if year == SEED_YEAR:
            packet, blockers = _build_seed_packet(year, diag)
        else:
            packet, blockers = _build_amendment_packet(year, diag, scans,
                                                       pdir)
        _write_json(out_dir / str(year) / "packet.json", packet)
        _write_text(out_dir / str(year) / "packet.md",
                    _render_md(packet))
        n_valued = packet.get("n_column_a_valued", "-")
        n_change = len(packet.get("change_lines", []))
        direction = (packet.get("overall") or {}).get("direction", "-")
        rep.line(f"packet {year}: type={packet['packet_type']}, "
                 f"column-A valued={n_valued}, change lines={n_change}, "
                 f"direction={direction}, "
                 f"blockers={len(blockers)}")
        rep.line(f"packets written: {out_dir}/{year}/packet.json, "
                 f"{out_dir}/{year}/packet.md")
        n_blocked += len(blockers)

    rep.line(f"summary: 4 packets, {n_blocked} blocker(s)")
    return 0 if n_blocked == 0 else 1
