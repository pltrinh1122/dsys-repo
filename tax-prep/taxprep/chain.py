"""R24(a): carryover chain + diagnostic over the Operator's transcript CSVs.

Reads format-v2 Operator CSVs (Return Transcripts 2022-2025, Records of
Account / Account Transcripts, W&I 2022-2024) plus an optional 2022
seed sheet, recomputes the Capital Loss Carryover Worksheet chain on the
FROZEN carryforward engine, and writes blind-safe diagnostics.

BLIND-SAFE CONTRACT (load-bearing): this module never prints a monetary
or identity value on stdout, stderr, or logs. Stdout carries only labels,
counts, flags, tax years, calendar years, file ids (sha256[:16]), check
names with pass/fail, and output paths. Values live only in the JSON
files under --out (written 0600 under a 0700 directory). Unmatched or
ambiguous labels are reported BY LABEL TEXT so the workstation can fix
mappings without seeing values.

Supported Python: 3.12 primary, 3.14 supported. This module imports
stdlib plus first-party modules that are themselves stdlib-only at
module load (operator_csv, carryforward, twocol) -- no pdfplumber (or
any heavy third-party import) anywhere in the chain path.

Money is Decimal-safe strings end to end; never floats.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import NoReturn

from . import carryforward
from .operator_csv import parse_operator_csv
from .twocol import normalize_label

__all__ = ["run", "SUPPORTED_YEARS"]

SUPPORTED_YEARS = (2022, 2023, 2024, 2025)

# ---------------------------------------------------------------------------
# Label vocabulary (from the R24 bus spec, msg_1600621718eb).
# ---------------------------------------------------------------------------

_PER_COMPUTER_SUFFIX = " PER COMPUTER"


def _norm(label: str) -> str:
    return normalize_label(label or "")


def _build_sched_d_map() -> dict[str, tuple[str, str, str]]:
    """normalized label -> (term, category, field).

    term: "st" | "lt" | "" (term-independent). category/field per the
    spec's Schedule D section layout.
    """
    m: dict[str, tuple[str, str, str]] = {}
    cat_templates = [
        ("basis_no_adj", "basis no adjustments", ["sale amount", "cost amount"]),
        ("basis", "basis", ["sale amount", "cost amount", "adjustments"]),
        ("no_basis", "no basis", ["sale amount", "cost amount", "adjustments"]),
        ("no_1099b", "no 1099-B", ["sale amount", "cost amount", "adjustments"]),
    ]
    for term_word, term in (("Short term", "st"), ("Long term", "lt")):
        for cat, cat_words, fields in cat_templates:
            for f in fields:
                label = f"{term_word} {cat_words} {f}"
                m[_norm(label)] = (term, cat, f.split()[0])  # sale|cost|adjustments
        m[_norm(f"{term_word} Schedule K-1 amount")] = (term, "k1", "amount")
    m[_norm("Net short-term gain/loss")] = ("st", "net", "amount")
    m[_norm("Net long-term gain/loss")] = ("lt", "net", "amount")
    # Long-term extras.
    m[_norm("Capital gain distributions (PR)")] = ("lt", "cap_dist", "amount")
    m[_norm("28% rate gain")] = ("lt", "gain28", "amount")
    m[_norm("Unrecaptured section (1250 gain)")] = ("lt", "unrec1250", "amount")
    # Schedule D tax-computer rows: recorded, not part of chain math.
    for lbl in (
        "Schedule D 15% tax computer",
        "Capital gains less invest income per computer",
        "Capital gains per computer",
        "Capital gains tax per computer",
        "28% rate capital gains tax per computer",
        "Schedule D tax per computer",
    ):
        m[_norm(lbl)] = ("", "tc", "amount")
    return m


_SCHED_D_MAP = _build_sched_d_map()

# 1040-section fuzzy patterns, ordered (first match wins).
_1040_PATTERNS: list[tuple[str, str]] = [
    ("ADJUSTED GROSS INCOME", "agi"),
    ("STANDARD DEDUCTION", "std_ded"),
    ("ITEMIZED DEDUCTION", "item_ded"),
    ("QUALIFIED BUSINESS INCOME", "qbi"),
    ("TAXABLE INCOME", "ti"),
    ("TOTAL TAX", "total_tax"),
    ("WITHHOLD", "withholding"),
    ("REFUND", "refund"),
    ("AMOUNT OWED", "owed"),
    ("AMOUNT YOU OWE", "owed"),
    ("BALANCE DUE", "owed"),
]
_1040_EXACT = {
    "TAX": "tax",
    "INCOME TAX": "tax",
    "FEDERAL INCOME TAX": "tax",
    "FILING STATUS": "filing_status",
}

# Attached-form indicators: normalized substring -> flag name.
_FORM_PATTERNS: list[tuple[str, str]] = [
    ("8814", "f8814"),
    ("8615", "f8615"),
    ("8949", "f8949"),
    ("8995", "f8995"),
    ("8960", "f8960"),
    ("4952", "f4952"),
    ("8606", "f8606"),
    ("8959", "f8959"),
    ("SCHEDULE A", "sch_a"),
    ("SCHEDULE C", "sch_c"),
    ("SCHEDULE SE", "sch_se"),
    ("SCHEDULE E", "sch_e"),
]
_FORM_WORD_PATTERNS: list[tuple[str, str]] = [
    ("SCH A", "sch_a"),
    ("SCH C", "sch_c"),
    ("SCH SE", "sch_se"),
    ("SCH E", "sch_e"),
]

# Transcript spellings of the filing status -> carryforward engine alias.
# The engine is FROZEN; the mapping lives here. Prefix match, lowercase.
_STATUS_PREFIXES: list[tuple[str, str]] = [
    ("single", "single"),
    ("married filing joint", "mfj"),
    ("married filing separate", "mfs"),
    ("head of household", "hoh"),
    ("qualifying widow", "qw"),
    ("qualifying surviving spouse", "qw"),
]


def _status_from_transcript(raw: str) -> str | None:
    """Engine status code for a transcript 'Filing status' value, or None."""
    key = " ".join(str(raw or "").strip().lower()
                   .replace("_", " ").replace("-", " ").split())
    if not key:
        return None
    try:
        return carryforward._normalize_status(key)
    except ValueError:
        pass
    for prefix, code in _STATUS_PREFIXES:
        if key.startswith(prefix):
            return code
    return None


# Transaction codes of interest (spec item 5): code -> check stem.
_TC_WATCH = ("420", "460", "922", "971", "976", "977")


def _tc_is_29x(code: str) -> bool:
    return len(code) == 3 and code.startswith("29") and code[2:].isdigit()


# ---------------------------------------------------------------------------
# Blind-safe output plumbing.
# ---------------------------------------------------------------------------

# Money/EIN-shaped redaction for third-party error text (parse_operator_csv
# messages can echo cell values; blind-safe stderr must never carry them).
_VALUE_RE = re.compile(r"\$?\d[\d,]*\.\d{2}|\b\d{2}-\d{7}\b")


def _sanitize(msg: str) -> str:
    return _VALUE_RE.sub("[redacted]", msg)


class _Reporter:
    """Accumulates stdout lines. Only allow-listed content may be added."""

    def __init__(self) -> None:
        self.lines: list[str] = []
        self.checks: list[dict] = []

    def line(self, text: str) -> None:
        self.lines.append(text)

    def check(self, name: str, status: str, detail: str = "") -> None:
        assert status in ("pass", "fail", "skip")
        self.checks.append({"name": name, "status": status, "detail": detail})
        suffix = f" ({detail})" if detail else ""
        self.lines.append(f"check {name}: {status}{suffix}")

    def emit(self) -> None:
        for ln in self.lines:
            print(ln)


def _fail(msg: str) -> "NoReturn":
    raise _ChainError(msg)


class _ChainError(Exception):
    """Loud, blind-safe failure (message carries labels/rows, never values)."""


# ---------------------------------------------------------------------------
# Value parsing (Decimal-safe, never float).
# ---------------------------------------------------------------------------

_MONEY_RE = re.compile(r"^-?\(?\$?\s*[\d,]+(\.\d{1,2})?\)?$")


def parse_money(label_text: str, csv_row: int, raw: str | None) -> Decimal:
    """Parse an Operator-typed money string to Decimal.

    Accepts optional commas, a leading $, and parenthesized negatives.
    Anything else fails loud naming the label and row (never the value).
    """
    s = (raw or "").strip()
    if not s or not _MONEY_RE.match(s):
        _fail(f"row {csv_row}: label '{label_text}' has a non-money value")
    neg = s.startswith("(") and s.endswith(")")
    s = s.replace(",", "").replace("$", "").strip().strip("()").strip()
    try:
        d = Decimal(s)
    except InvalidOperation:
        _fail(f"row {csv_row}: label '{label_text}' has a non-money value")
    return -d if neg else d


def _dec_str(d: Decimal) -> str:
    return format(d, "f")

# ---------------------------------------------------------------------------
# File discovery and classification.
# ---------------------------------------------------------------------------

# kind -> keywords (all must be present in the joined normalized headings).
_KIND_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("return", ("RETURN TRANSCRIPT",)),
    ("roa", ("RECORD OF ACCOUNT",)),
    ("account", ("ACCOUNT TRANSCRIPT",)),
    ("wi", ("WAGE", "INCOME")),
]

_YEAR_RE = re.compile(r"\b(20\d\d)\b")


def _file_id(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()[:16]


def _discover(csv_dir: Path) -> list[dict]:
    """Read + parse every *.csv; classify kind/year. Loud on any problem."""
    if not csv_dir.is_dir():
        _fail(f"csv dir is not a directory: {csv_dir}")
    files = sorted(csv_dir.glob("*.csv"))
    if not files:
        _fail(f"no CSV files in {csv_dir}")
    out = []
    for path in files:
        try:
            raw = path.read_bytes()
        except OSError as exc:
            _fail(f"cannot read file id pending ({path.name}): {exc}")
        fid = _file_id(raw)
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            _fail(f"file {fid} ({path.name}) is not UTF-8")
        try:
            parsed = parse_operator_csv(text)
        except ValueError as exc:
            _fail(f"file {fid} ({path.name}) failed to parse: "
                  f"{_sanitize(str(exc))}")
        kind, year = _classify(parsed, path.name, fid)
        out.append({"file_id": fid, "name": path.name, "path": path,
                    "kind": kind, "year": year, "parsed": parsed})
    return out


def _classify(parsed: dict, filename: str, fid: str) -> tuple[str, int]:
    headings = [_norm(h["text"]) for h in parsed.get("headings", [])]
    joined = " ".join(headings)
    kind = None
    for k, keywords in _KIND_KEYWORDS:
        if all(kw in joined for kw in keywords):
            kind = k
            break
    if kind is None:
        # Filename fallback: return-*, account-*, roa-*, wi-*/wage-*.
        low = filename.lower()
        for k, frags in (("return", ("return",)), ("roa", ("roa",)),
                         ("account", ("account",)), ("wi", ("wi", "wage"))):
            if any(f in low for f in frags):
                kind = k
                break
    if kind is None:
        _fail(f"file {fid} ({filename}): transcript kind not determinable "
              f"from headings or filename")
    years = {int(m.group(1)) for h in headings for m in [_YEAR_RE.search(h)]
             if m}
    if not years:
        m = _YEAR_RE.search(filename)
        if m:
            years = {int(m.group(1))}
    if not years:
        _fail(f"file {fid} ({filename}): tax year not determinable")
    if len(years) > 1:
        _fail(f"file {fid} ({filename}): ambiguous tax year in headings")
    return kind, next(iter(years))


def _load_identity(identity_file: str | None) -> list[str]:
    if not identity_file:
        return []
    p = Path(identity_file)
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        _fail(f"cannot read identity file: {exc}")
    return [ln.strip().casefold() for ln in lines if ln.strip()]


# ---------------------------------------------------------------------------
# Section scanning: rows -> mapped values.
# ---------------------------------------------------------------------------

def _strip_variant(norm_label: str) -> tuple[str, str]:
    if norm_label.endswith(_PER_COMPUTER_SUFFIX):
        return norm_label[: -len(_PER_COMPUTER_SUFFIX)].rstrip(), "per_computer"
    return norm_label, "as_entered"


class _YearScan:
    """All extracted signals for one tax year."""

    def __init__(self, year: int) -> None:
        self.year = year
        self.file_ids: dict[str, list[str]] = {}
        # sched-d: (term, category, field, variant) -> list of
        # (Decimal value, label text, csv row, file id).
        self.sched_d: dict[tuple[str, str, str, str], list] = {}
        self.form1040: dict[tuple[str, str], list] = {}
        self.filing_status_raw: str | None = None
        self.unmatched_sched_d: list[str] = []
        self.unmatched_1040: list[str] = []
        self.transactions: list[dict] = []
        self.forms_present: set[str] = set()
        self.per_computer_pairs: dict[str, dict[str, tuple]] = {}
        # Raw data rows per file kind (for dedicated passes like W&I).
        self.raw_rows: list[dict] = []

    def add_file(self, kind: str, fid: str) -> None:
        self.file_ids.setdefault(kind, []).append(fid)


_SCHED_D_HEAD_RE = re.compile(r"^SCHEDULE D\b")
_FORM_1040_HEAD_RE = re.compile(r"^FORM 1040\b")


def _section_of(heading_text: str) -> str:
    """Section opened by a LEVEL-1 heading (R24 rev1).

    Real format-v2 Return Transcripts carry the 1040 as a run of level-1
    sections ('Income', 'Adjustments to Income', 'Tax and Credits',
    'Other Taxes', 'Payments', 'Refund or Amount Owed', 'Third Party
    Designee'), then one level-1 heading per attached schedule/form
    whose level-2 headings ('Income', 'Expenses' under Schedule C;
    'SHORT TERM ...', 'LONG TERM ...', 'TAX COMPUTATION ...' under
    Schedule D) only subdivide their parent. Hence:

      level-1 'SCHEDULE D ...'      -> sched_d
      level-1 'SCHEDULE ...'        -> other   (scanned for form flags only)
      level-1 'FORM 1040 ...'       -> form1040 (the 1040 itself)
      level-1 'FORM ...'            -> other
      any other level-1 heading     -> form1040
      level-2 heading               -> inherits (never consulted)
    """
    n = _norm(heading_text)
    if _SCHED_D_HEAD_RE.match(n):
        return "sched_d"
    if n.startswith("SCHEDULE"):
        return "other"
    if n.startswith("FORM"):
        return "form1040" if _FORM_1040_HEAD_RE.match(n) else "other"
    return "form1040"


# Transcript kinds whose Schedule D / 1040 money rows feed the math.
# Account Transcripts and Records of Account repeat AGI / taxable income
# (and an ROA repeats the whole return); scanning them would double the
# sums, so they contribute only filing status, transactions and flags.
_MONEY_KINDS = ("return",)


def _scan_file(scan: _YearScan, frec: dict, identity: list[str]) -> None:
    parsed = frec["parsed"]
    fid = frec["file_id"]
    kind = frec["kind"]
    scan.add_file(kind, fid)
    headings = parsed.get("headings", [])
    head_rows = sorted((h["csv_row"], _norm(h["text"])) for h in headings)
    # Section tracking follows LEVEL-1 headings only; level-2 inherit.
    level1_rows = sorted((h["csv_row"], _norm(h["text"]))
                         for h in headings if h.get("level", 1) == 1)
    for _, ht in head_rows:
        _scan_forms(scan, ht)
    money_rows = kind in _MONEY_KINDS
    for row in parsed.get("data_rows", []):
        r = row["csv_row"]
        cur = "unsectioned"
        for hr, ht in level1_rows:
            if hr < r:
                cur = _section_of(ht)
            else:
                break
        # Identity skip: any heading above this row matched the list.
        skip = False
        for hr, ht in head_rows:
            if hr < r and any(ident and ident in ht for ident in identity):
                # a later non-identity heading re-enables
                later = [h2 for h2, _ in head_rows if r > h2 > hr]
                if not later:
                    skip = True
        if skip:
            continue
        _scan_forms(scan, row["normalized"])
        scan.raw_rows.append({"kind": kind, "row": row, "fid": fid})
        if not money_rows:
            # Account / ROA / W&I: the 'Filing status' row only.
            base, _variant = _strip_variant(row["normalized"])
            if _1040_EXACT.get(base) == "filing_status":
                _set_filing_status(scan, row)
            continue
        if cur == "sched_d":
            _scan_sched_d_row(scan, row, fid)
        elif cur in ("form1040", "unsectioned"):
            _scan_1040_row(scan, row, fid)
    for t in parsed.get("transaction_rows", []):
        scan.transactions.append({**t, "file_id": fid})


def _set_filing_status(scan: _YearScan, row: dict) -> None:
    if scan.filing_status_raw is None:
        scan.filing_status_raw = (row["value"] or "").strip()


def _scan_forms(scan: _YearScan, norm_text: str) -> None:
    for pat, flag in _FORM_PATTERNS:
        if pat in norm_text:
            scan.forms_present.add(flag)
    for pat, flag in _FORM_WORD_PATTERNS:
        if re.search(rf"\b{re.escape(pat)}\b", norm_text):
            scan.forms_present.add(flag)


def _scan_sched_d_row(scan: _YearScan, row: dict, fid: str) -> None:
    label_text = row["printed_label"]
    base, variant = _strip_variant(row["normalized"])
    hit = _SCHED_D_MAP.get(base)
    if hit is None and base.endswith(" AMOUNT"):
        hit = _SCHED_D_MAP.get(base[: -len(" AMOUNT")].rstrip())
    if hit is None and variant == "per_computer":
        # Tax-computer rows are keyed WITH their 'per computer' suffix.
        hit = _SCHED_D_MAP.get(row["normalized"])
    if hit is None:
        if label_text not in scan.unmatched_sched_d:
            scan.unmatched_sched_d.append(label_text)
        return
    term, cat, field = hit
    if cat == "tc":
        return  # tax-computer rows: recorded for variant checks only
    key = (term, cat, field, variant)
    val = parse_money(label_text, row["csv_row"], row["value"])
    scan.sched_d.setdefault(key, []).append((val, label_text,
                                             row["csv_row"], fid))
    # Track as-entered vs per-computer pairs for key lines.
    pkey = (term, cat, field)
    scan.per_computer_pairs.setdefault(pkey, {})[variant] = (
        val, label_text, row["csv_row"], fid)


def _scan_1040_row(scan: _YearScan, row: dict, fid: str) -> None:
    label_text = row["printed_label"]
    base, variant = _strip_variant(row["normalized"])
    key = _1040_EXACT.get(base)
    if key is None:
        for pat, k in _1040_PATTERNS:
            if pat in base:
                key = k
                break
    if key is None:
        if label_text not in scan.unmatched_1040:
            scan.unmatched_1040.append(label_text)
        return
    if key == "filing_status":
        _set_filing_status(scan, row)
        return
    val = parse_money(label_text, row["csv_row"], row["value"])
    scan.form1040.setdefault((key, variant), []).append(
        (val, label_text, row["csv_row"], fid))

# ---------------------------------------------------------------------------
# Seed sheet (2022 per-account summary totals).
# ---------------------------------------------------------------------------

_SEED_COLUMNS = ("year", "payer_ein", "acct_id", "person", "box",
                 "proceeds", "cost_basis", "wash_sale_disallowed", "net",
                 "term", "source_sha16", "corrected")

# 8949 box -> (term, sched-d category) for the 2022 seed-vs-filed check.
_BOX_CATEGORY = {
    "A": ("st", "basis"), "B": ("st", "no_basis"), "C": ("st", "no_1099b"),
    "D": ("lt", "basis"), "E": ("lt", "no_basis"), "F": ("lt", "no_1099b"),
}


def _parse_seed_sheet(path: str) -> dict:
    p = Path(path)
    try:
        raw = p.read_text(encoding="utf-8")
    except OSError as exc:
        _fail(f"cannot read seed sheet: {exc}")
    reader = csv.DictReader(raw.splitlines())
    if reader.fieldnames is None:
        _fail("seed sheet is empty")
    missing = [c for c in _SEED_COLUMNS if c not in reader.fieldnames]
    if missing:
        _fail(f"seed sheet missing columns: {', '.join(missing)}")
    rows = []
    for i, r in enumerate(reader, start=2):
        if not any((r.get(c) or "").strip() for c in _SEED_COLUMNS):
            continue  # blank line
        try:
            year = int((r["year"] or "").strip())
        except ValueError:
            _fail(f"seed sheet row {i}: bad year")
        box = (r["box"] or "").strip().upper()
        term_raw = (r["term"] or "").strip().lower()
        if term_raw.startswith("s"):
            term = "st"
        elif term_raw.startswith("l"):
            term = "lt"
        elif box in _BOX_CATEGORY:
            term = _BOX_CATEGORY[box][0]
        else:
            _fail(f"seed sheet row {i}: term not determinable "
                  f"(term/box)")
        net_raw = (r["net"] or "").strip()
        if net_raw:
            try:
                net = Decimal(net_raw.replace(",", ""))
            except InvalidOperation:
                _fail(f"seed sheet row {i}: bad net")
        else:
            try:
                proc = Decimal((r["proceeds"] or "0").replace(",", "") or "0")
                cost = Decimal((r["cost_basis"] or "0").replace(",", "") or "0")
                wash = Decimal((r["wash_sale_disallowed"] or "0").replace(",", "")
                               or "0")
            except InvalidOperation:
                _fail(f"seed sheet row {i}: bad proceeds/cost/wash")
            net = proc - cost + wash
        try:
            proceeds = Decimal((r["proceeds"] or "0").replace(",", "") or "0")
        except InvalidOperation:
            _fail(f"seed sheet row {i}: bad proceeds")
        rows.append({"row": i, "year": year, "box": box, "term": term,
                     "net": net, "proceeds": proceeds,
                     "corrected": (r["corrected"] or "").strip().lower()
                     in ("true", "1", "yes", "x")})
    return {"rows": rows}


# ---------------------------------------------------------------------------
# Per-year as-filed math.
# ---------------------------------------------------------------------------

def _sum_vals(entries: list) -> Decimal:
    return sum((e[0] for e in entries), Decimal("0"))


def _year_inputs(scan: _YearScan) -> dict:
    """Current-year ST/LT inputs from the Schedule D section.

    inputs[term] = sale - cost + adjustments per category + K-1
    (+ capital-gain distributions for LT). All signed as printed.
    """
    out: dict[str, Decimal] = {"st": Decimal("0"), "lt": Decimal("0")}
    cats: dict[tuple[str, str], dict[str, Decimal]] = {}
    for (term, cat, field, variant), entries in scan.sched_d.items():
        if variant != "as_entered" or term not in ("st", "lt"):
            continue
        if cat in ("net", "k1", "cap_dist", "gain28", "unrec1250", "tc"):
            continue
        cats.setdefault((term, cat), {})[field] = _sum_vals(entries)
    for (term, cat), f in cats.items():
        out[term] += f.get("sale", Decimal("0")) - f.get("cost", Decimal("0")) \
            + f.get("adjustments", Decimal("0"))
    for (term, cat, field, variant), entries in scan.sched_d.items():
        if variant != "as_entered":
            continue
        if cat == "k1" and term in ("st", "lt"):
            out[term] += _sum_vals(entries)
        elif cat == "cap_dist" and term == "lt":
            out["lt"] += _sum_vals(entries)
    return out


def _year_nets(scan: _YearScan) -> dict[str, Decimal | None]:
    out: dict[str, Decimal | None] = {"st": None, "lt": None}
    for (term, cat, field, variant), entries in scan.sched_d.items():
        if cat == "net" and variant == "as_entered" and term in ("st", "lt"):
            out[term] = _sum_vals(entries)
    return out


def _form1040_value(scan: _YearScan, key: str,
                    variant: str = "as_entered") -> Decimal | None:
    entries = scan.form1040.get((key, variant))
    if not entries:
        return None
    return _sum_vals(entries)


def _derive_line1(scan: _YearScan) -> dict | None:
    """Worksheet line 1 = AGI - deductions - QBI. None if underivable."""
    agi = _form1040_value(scan, "agi")
    item_ded = _form1040_value(scan, "item_ded")
    std_ded = _form1040_value(scan, "std_ded")
    qbi = _form1040_value(scan, "qbi")
    if agi is None or qbi is None:
        return None
    if item_ded is not None:
        ded, ded_name = item_ded, "itemized"
    elif std_ded is not None:
        ded, ded_name = std_ded, "standard"
    else:
        return None
    return {"agi": agi, "deduction": ded, "deduction_used": ded_name,
            "qbi": qbi, "line1": agi - ded - qbi}

# ---------------------------------------------------------------------------
# Orchestrator.
# ---------------------------------------------------------------------------

def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=1, sort_keys=True)
        fh.write("\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def _ensure_out(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(out_dir, 0o700)


def _wi_proceeds(scan: _YearScan) -> Decimal | None:
    """Sum of 1099-B proceeds rows in W&I CSVs. None if no labeled rows."""
    total = Decimal("0")
    found = False
    for key, entries in scan.sched_d.items():
        pass  # sched_d is return-transcript only; W&I scanned below
    return None  # placeholder replaced below


def run(*, csv_dir: str, seed_sheet: str | None, out: str,
        identity_file: str | None, filing_status: str | None,
        prior_st: str = "0", prior_lt: str = "0") -> int:
    """Run the R24(a) diagnostic. Returns 0 (all checks pass) or 1."""
    rep = _Reporter()
    try:
        return _run_inner(rep, csv_dir=csv_dir, seed_sheet=seed_sheet,
                          out=out, identity_file=identity_file,
                          filing_status=filing_status,
                          prior_st=prior_st, prior_lt=prior_lt)
    except _ChainError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        rep.emit()


def _run_inner(rep: _Reporter, *, csv_dir: str, seed_sheet: str | None,
               out: str, identity_file: str | None,
               filing_status: str | None,
               prior_st: str, prior_lt: str) -> int:
    out_dir = Path(out)
    _ensure_out(out_dir)
    identity = _load_identity(identity_file)
    files = _discover(Path(csv_dir))
    rep.line(f"r24-chain: {len(files)} file(s) parsed, 0 failed")

    # Group by year; exactly one return transcript per year required.
    scans: dict[int, _YearScan] = {}
    for frec in files:
        y = frec["year"]
        scans.setdefault(y, _YearScan(y))
        if frec["kind"] == "return" and "return" in scans[y].file_ids:
            _fail(f"duplicate return transcript CSV for tax year {y}: "
                  f"{scans[y].file_ids['return'][0]} and {frec['file_id']}")
        _scan_file(scans[y], frec, identity)
    for y in SUPPORTED_YEARS:
        if y not in scans or "return" not in scans[y].file_ids:
            _fail(f"no return transcript CSV for tax year {y}")
    extra_years = sorted(y for y in scans if y not in SUPPORTED_YEARS)
    if extra_years:
        _fail(f"unexpected tax year(s) in csv dir: "
              f"{','.join(str(y) for y in extra_years)}")
    years = sorted(y for y in scans if y in SUPPORTED_YEARS)
    rep.line(f"years: {','.join(str(y) for y in years)}")

    # Filing status: flag wins, else the CSV 'Filing status' row, else loud.
    status = filing_status
    status_source = "flag"
    if status is None:
        raws = {scans[y].filing_status_raw for y in years
                if scans[y].filing_status_raw}
        codes = {_status_from_transcript(r) for r in raws}
        if None in codes:
            _fail("transcript 'Filing status' value not recognized "
                  "(pass --filing-status)")
        if len(codes) > 1:
            _fail("transcript 'Filing status' differs across tax years "
                  "(pass --filing-status)")
        if codes:
            status = next(iter(codes))
            status_source = "csv"
    if status is None:
        _fail("filing status not given (--filing-status) and not found "
              "in the transcript CSVs")
    try:
        status = carryforward._normalize_status(status)
    except ValueError as exc:
        _fail(str(exc))
    rep.line(f"filing_status_source: {status_source}")

    seed = _parse_seed_sheet(seed_sheet) if seed_sheet else None

    # --- per-year as-filed math + line-1 derivation ---------------------
    per_year: dict[int, dict] = {}
    line1_by_year: dict[int, Decimal] = {}
    line1_ok = True
    for y in years:
        scan = scans[y]
        nets = _year_nets(scan)
        inputs = _year_inputs(scan)
        if nets["st"] is None or nets["lt"] is None:
            _fail(f"tax year {y}: as-filed net ST/LT lines not found")
        applied_st = nets["st"] - inputs["st"]
        applied_lt = nets["lt"] - inputs["lt"]
        per_year[y] = {"scan": scan, "nets": nets, "inputs": inputs,
                       "applied_st": applied_st, "applied_lt": applied_lt,
                       "applied_total": applied_st + applied_lt}
        li = _derive_line1(scan)
        if li is None:
            line1_ok = False
            rep.check(f"worksheet_line1_derived_{y}", "fail",
                      "AGI/deduction/QBI not all present")
        else:
            line1_by_year[y] = li["line1"]
            rep.check(f"worksheet_line1_derived_{y}", "pass")
        per_year[y]["line1"] = li

    # The engine fallback must never engage: every year needs line 1.
    if not line1_ok or set(line1_by_year) != set(years):
        rep.check("no_engine_fallback", "fail",
                  "worksheet line 1 underivable for a year")
    else:
        rep.check("no_engine_fallback", "pass")

    # --- correct chain --------------------------------------------------
    yearly_inputs: dict[int, dict] = {}
    for y in years:
        if y == 2022 and seed is not None:
            st = sum((r["net"] for r in seed["rows"] if r["year"] == 2022
                      and r["term"] == "st"), Decimal("0"))
            lt = sum((r["net"] for r in seed["rows"] if r["year"] == 2022
                      and r["term"] == "lt"), Decimal("0"))
        else:
            st = per_year[y]["inputs"]["st"]
            lt = per_year[y]["inputs"]["lt"]
        yearly_inputs[y] = {"st_current": st, "lt_current": lt}

    chain_failed = any(c["status"] == "fail" for c in rep.checks)
    chain_result: dict | None = None
    if not chain_failed:
        try:
            pst = Decimal(prior_st.replace(",", ""))
            plt = Decimal(prior_lt.replace(",", ""))
        except InvalidOperation:
            _fail("--prior-st/--prior-lt must be decimal strings")
        chain_result = carryforward.compute_chain(
            yearly_inputs,
            {y: status for y in years},
            prior_carryover={"st": pst, "lt": plt},
            taxable_income_by_year=dict(line1_by_year),
        )
        # Belt-and-braces: the engine must not have warned-and-assumed.
        warned = [w for w in chain_result.get("warnings", [])
                  if "taxable income not supplied" in w]
        if warned:
            rep.check("no_engine_fallback", "fail",
                      "engine fell back despite derived line 1")
            chain_result = None

    # --- checks 1,3,4,5,6,7 + outputs ----------------------------------
    diags: dict[int, dict] = {}
    for y in years:
        diags[y] = _diagnose_year(rep, y, per_year[y], scans[y],
                                 chain_result, seed, status)

    # W&I cross-check needs seed (or (b) output, a later landing).
    if seed is not None:
        for y in years:
            _wi_check(rep, diags[y], scans[y], seed, y)
    else:
        for y in years:
            diags[y]["wi_crosscheck"] = {"status": "skip",
                                         "reason": "no seed sheet or (b) output"}
            rep.check(f"wi_crosscheck_{y}", "skip", "no seed sheet")

    # --- write outputs ---------------------------------------------------
    for y in years:
        diag = diags[y]
        diag["checks"] = [c for c in rep.checks
                          if c["name"].endswith(f"_{y}")
                          or c["name"] in ("no_engine_fallback",)]
        _write_json(out_dir / str(y) / "diagnostic.json",
                    _jsonable(diag))
    if chain_result is not None:
        _write_json(out_dir / "chain.json", _jsonable({
            "years": years,
            "filing_status": status,
            "filing_status_source": status_source,
            "carry_into_2026": chain_result["carryforward_into_2026"],
            "per_year": {
                y: {
                    "st_carry_in": r["st_carry_in"],
                    "lt_carry_in": r["lt_carry_in"],
                    # L4: the deduction that actually reduced taxable
                    # income (line 21 capped by the line-1 limitation).
                    "deduction_allowed": r["worksheet_lines"][
                        "L4_used_deduction"],
                    "st_carry_out": r["st_carry_out"],
                    "lt_carry_out": r["lt_carry_out"],
                    "worksheet_lines": r["worksheet_lines"],
                }
                for y, r in chain_result["years"].items()
            },
        }))
        rep.line("chain: carry_into_2026 computed")

    n_pass = sum(1 for c in rep.checks if c["status"] == "pass")
    n_fail = sum(1 for c in rep.checks if c["status"] == "fail")
    n_skip = sum(1 for c in rep.checks if c["status"] == "skip")
    rep.line(f"summary: {n_pass} passed, {n_fail} failed, {n_skip} skipped")
    for y in years:
        rep.line(f"packets written: {out_dir}/{y}/diagnostic.json")
    if chain_result is not None:
        rep.line(f"packets written: {out_dir}/chain.json")
    return 0 if n_fail == 0 else 1


def _jsonable(obj):
    if isinstance(obj, Decimal):
        return _dec_str(obj)
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, set):
        return sorted(obj)
    return obj


def _diagnose_year(rep: _Reporter, y: int, py: dict, scan: _YearScan,
                   chain_result: dict | None, seed: dict | None,
                   status: str) -> dict:
    diag: dict = {"year": y, "file_ids": scan.file_ids}
    nets, inputs = py["nets"], py["inputs"]

    # Check 1: as-filed applied carryover (expected 0 for 2023-2025).
    diag["as_filed"] = {
        "net_st": nets["st"], "net_lt": nets["lt"],
        "inputs_st": inputs["st"], "inputs_lt": inputs["lt"],
        "applied_carryover_st": py["applied_st"],
        "applied_carryover_lt": py["applied_lt"],
        "applied_carryover_total": py["applied_total"],
        "unmatched_sched_d_labels": sorted(scan.unmatched_sched_d),
        "unmatched_1040_labels": sorted(scan.unmatched_1040),
    }
    if y in (2023, 2024, 2025):
        if py["applied_total"] == 0:
            rep.check(f"as_filed_carryover_zero_{y}", "pass")
        else:
            rep.check(f"as_filed_carryover_zero_{y}", "fail",
                      "as-filed return applied a nonzero carryover")
    diag["unmatched_label_counts"] = {
        "sched_d": len(scan.unmatched_sched_d),
        "form1040": len(scan.unmatched_1040),
    }
    rep.line(f"unmatched_labels_{y}: "
             f"sched_d={len(scan.unmatched_sched_d)} "
             f"form1040={len(scan.unmatched_1040)}")

    # Correct-chain slice for this year.
    if chain_result is not None:
        r = chain_result["years"][y]
        # L4: the deduction that actually reduced taxable income.
        correct_ded = r["worksheet_lines"]["L4_used_deduction"]
        diag["correct"] = {
            "st_carry_in": r["st_carry_in"],
            "lt_carry_in": r["lt_carry_in"],
            "deduction_allowed": correct_ded,
            "st_carry_out": r["st_carry_out"],
            "lt_carry_out": r["lt_carry_out"],
            "worksheet_lines": r["worksheet_lines"],
            "engine_warnings": r["warnings"],
        }
        # Check 3a: TI delta vs as-filed.
        limit = (carryforward.ANNUAL_LIMIT_MFS
                 if carryforward._normalize_status(status) == "mfs"
                 else carryforward.ANNUAL_LIMIT)
        net_total = nets["st"] + nets["lt"]
        as_filed_ded = min(-net_total, limit) if net_total < 0 else Decimal("0")
        ti_delta = correct_ded - as_filed_ded
        direction = ("refund" if ti_delta > 0
                     else "owed" if ti_delta < 0 else "none")
        diag["deltas"] = {
            "as_filed_deduction_recomputed": as_filed_ded,
            "correct_deduction": correct_ded,
            "taxable_income_delta": ti_delta,
            "tax_change": ti_delta != 0,
            "direction": direction,
        }
        # Tax-change is a flag, not a pass/fail check: report it blind-safe.
        rep.line(f"tax_change_{y}: "
                 f"{'yes' if ti_delta != 0 else 'no'} direction={direction}")
    else:
        diag["correct"] = None
        diag["deltas"] = None

    # Check 3b: 2022 seed vs as-filed per category (names only on stdout).
    if y == 2022 and seed is not None:
        mismatches = _seed_vs_filed(scan, seed)
        diag["seed_vs_filed_2022"] = {
            "mismatched_categories": sorted(mismatches),
            "n_mismatched": len(mismatches),
        }
        rep.check("seed_vs_filed_2022",
                  "pass" if not mismatches else "fail",
                  f"{len(mismatches)} categor(ies)" if mismatches else "")
    elif y == 2022:
        diag["seed_vs_filed_2022"] = None
        rep.check("seed_vs_filed_2022", "skip", "no seed sheet")

    # Check 4: as-entered vs PER COMPUTER mismatches (count; info only).
    pc_labels = []
    for pkey, variants in scan.per_computer_pairs.items():
        if "as_entered" in variants and "per_computer" in variants:
            if variants["as_entered"][0] != variants["per_computer"][0]:
                pc_labels.append(variants["as_entered"][1])
    diag["per_computer_mismatches"] = {"count": len(pc_labels),
                                       "labels": sorted(pc_labels)}
    rep.line(f"per_computer_mismatches_{y}: {len(pc_labels)}")

    # Check 5: TC codes, received year (year only on stdout).
    tc_found: dict[str, bool] = {}
    codes_seen: set[str] = set()
    for t in scan.transactions:
        code = (t.get("code") or "").strip()
        if not code:
            continue
        codes_seen.add(code)
        if _tc_is_29x(code):
            tc_found["29x"] = True
        if code in _TC_WATCH:
            tc_found[code] = True
    diag["tc_codes"] = {c: tc_found.get(c, False)
                        for c in ("29x",) + _TC_WATCH}
    for c in ("29x",) + _TC_WATCH:
        rep.line(f"tc_{c}_{y}: "
                 f"{'present' if tc_found.get(c) else 'absent'}")
    received = None
    for t in scan.transactions:
        expl = _norm(t.get("explanation") or "")
        if "RECEIVED" in expl:
            received = _parse_date(t.get("date") or "")
            if received:
                break
    if received:
        diag["return_received"] = {
            "calendar_year": received.year,  # stdout-safe
            "refund_window_date": _dec_str_date(_plus_years(received, 3)),
        }
        rep.line(f"received_year_{y}: {received.year}")
    else:
        diag["return_received"] = None
        rep.line(f"received_year_{y}: not_found")

    # Check 6: attached-form indicators.
    forms = sorted(scan.forms_present)
    diag["attached_forms"] = forms
    rep.line(f"attached_forms_{y}: {','.join(forms) if forms else 'none'}")

    # Check 7 is handled by the caller (needs seed).
    return diag


def _seed_vs_filed(scan: _YearScan, seed: dict) -> list[str]:
    """Category names where the 2022 seed disagrees with as-filed."""
    filed: dict[tuple[str, str], Decimal] = {}
    for (term, cat, field, variant), entries in scan.sched_d.items():
        if variant != "as_entered" or term not in ("st", "lt"):
            continue
        if cat in ("net", "k1", "cap_dist", "gain28", "unrec1250", "tc"):
            continue
        key = (term, cat)
        d = filed.setdefault(key, {"sale": Decimal("0"), "cost": Decimal("0"),
                                   "adjustments": Decimal("0")})
        d[field] = d.get(field, Decimal("0")) + _sum_vals(entries)
    filed_net = {k: v.get("sale", Decimal("0")) - v.get("cost", Decimal("0"))
                 + v.get("adjustments", Decimal("0"))
                 for k, v in filed.items()}
    seed_net: dict[tuple[str, str], Decimal] = {}
    for r in seed["rows"]:
        if r["year"] != 2022:
            continue
        cat = _BOX_CATEGORY.get(r["box"], (r["term"], None))[1]
        if cat is None:
            continue
        key = (r["term"], cat)
        seed_net[key] = seed_net.get(key, Decimal("0")) + r["net"]
    mismatched = []
    for key in sorted(set(filed_net) | set(seed_net)):
        if filed_net.get(key, Decimal("0")) != seed_net.get(key, Decimal("0")):
            mismatched.append(f"{key[0]}_{key[1]}")
    return mismatched


def _wi_check(rep: _Reporter, diag: dict, scan: _YearScan,
              seed: dict, y: int) -> None:
    """W&I partial cross-check: sum(1099-B proceeds in W&I) <= seed proceeds.

    Blind-safe: only matched label texts and the pass/fail/skip outcome
    leave this function; amounts stay in the JSON.
    """
    wi_sum = Decimal("0")
    matched: set[str] = set()
    for item in scan.raw_rows:
        if item["kind"] != "wi":
            continue
        row = item["row"]
        n = row["normalized"]
        if "1099" in n and "PROCEEDS" in n and re.search(r"\bB\b", n):
            matched.add(row["printed_label"])
            wi_sum += parse_money(row["printed_label"], row["csv_row"],
                                  row["value"])
    if not matched:
        diag["wi_crosscheck"] = {"status": "skip",
                                 "reason": "no 1099-B proceeds rows in W&I"}
        rep.check(f"wi_crosscheck_{y}", "skip", "no proceeds rows")
        return
    seed_sum = sum((r["proceeds"] for r in seed["rows"] if r["year"] == y),
                   Decimal("0"))
    ok = wi_sum <= seed_sum
    diag["wi_crosscheck"] = {
        "status": "pass" if ok else "fail",
        "wi_proceeds_sum": wi_sum,
        "seed_proceeds_sum": seed_sum,
        "matched_labels": sorted(matched),
    }
    rep.check(f"wi_crosscheck_{y}", "pass" if ok else "fail",
              f"{len(matched)} label(s)")


def _parse_date(raw: str) -> date | None:
    from datetime import datetime as _dt

    s = (raw or "").strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y"):
        try:
            return _dt.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _plus_years(d: date, n: int) -> date:
    try:
        return d.replace(year=d.year + n)
    except ValueError:  # Feb 29 -> Feb 28
        return d.replace(year=d.year + n, day=28)


def _dec_str_date(d: date) -> str:
    return d.isoformat()
