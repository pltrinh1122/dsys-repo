"""R24(b): broker consolidated-1099 summary extractor.

Parses consolidated 1099 PDFs (text only, NO OCR) at SUMMARY level --
per account, per Form 8949 box -- and emits the seed-sheet CSV that
``taxprep chain`` (R24(a)) consumes, plus per-file statement records and
a reconciliation report.

Method: label-anchored geometry parse on pdfplumber word boxes, using
the R23 two-column capture (``taxprep.twocol``) as the template --
``group_into_lines`` for visual lines, header-alignment column
detection, dot-leader-tolerant label/value association. The column/row
vocabulary is seeded from the blind label census
(``msg_aa4c4b4d3e4b``: 23 statements, 2 layouts) and extendable via
``--labels``; labels that match nothing are reported BY LABEL TEXT so
the workstation can extend the census blind.

Blind-safe: stdout carries only labels, counts, flags, years, file ids,
check names and paths. Money and identity values go to files under
``--out`` (0700 dirs, 0600 files). Decimal-safe strings end to end,
never floats.

Layout 1 (Fidelity, 18 statements): 'Summary of ...' page; rows
'Short-/Long-term transactions for which basis is (not) reported to the
IRS'; columns Proceeds | Cost Basis | Market Discount |
Wash Sales Disallowed | Gain/Loss | Income Tax Withheld (headers wrap
over two text lines).
Layout 2 (second payer): 'REALIZED GAIN / LOSS SUMMARY' /
'FORM 1099-B TOTALS SUMMARY'; rows 'Box <A-F> <Short|Long>-Term
Realized Gain/Loss', 'Box B or Box E (basis not reported to IRS)',
'Noncovered Short-Term Gains or Losses on Gross Proceeds',
'Total Short-Term / Long-Term / Unknown Term'.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import NoReturn

from .twocol import group_into_lines, normalize_label

__all__ = ["run", "SUPPORTED_YEARS", "SEED_COLUMNS", "parse_statement_pdf"]

SUPPORTED_YEARS = (2022, 2023, 2024, 2025)

# Exact schema R24(a) consumes (chain._SEED_COLUMNS). Do not reorder.
SEED_COLUMNS = ("year", "payer_ein", "acct_id", "person", "box",
                "proceeds", "cost_basis", "wash_sale_disallowed", "net",
                "term", "source_sha16", "corrected")


class _SummaryError(Exception):
    """Loud, blind-safe failure (message carries labels/rows, never values)."""


def _fail(msg: str) -> NoReturn:
    raise _SummaryError(msg)


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


# ---------------------------------------------------------------------------
# Money parsing (Decimal-safe, never float).
# ---------------------------------------------------------------------------

_MONEY_WORD_RE = re.compile(r"^-?\(?\$?[\d,]+\.\d{2}\)?$")


def parse_money_word(raw: str) -> Decimal | None:
    """Parse one word token to Decimal, or None if not money-shaped.

    Accepts $ , commas, parenthesized negatives, leading '-'.
    """
    t = (raw or "").strip()
    if not _MONEY_WORD_RE.match(t):
        return None
    neg = t.startswith("(") and t.endswith(")") or t.startswith("-")
    t = t.replace("$", "").replace(",", "").replace("(", "").replace(")", "")
    t = t.lstrip("-").lstrip("+")
    try:
        d = Decimal(t)
    except InvalidOperation:
        return None
    return -d if neg else d


def _fmt(d: Decimal | None) -> str:
    return "" if d is None else format(d, ".2f")


# ---------------------------------------------------------------------------
# Vocabulary (seeded from the blind label census, msg_aa4c4b4d3e4b).
# --labels merges over these defaults; unmatched labels are reported by
# text so the census can be extended blind.
# ---------------------------------------------------------------------------

# Layout 1: normalized row label -> 8949 box.
_LAYOUT1_ROW_BOX: dict[str, str] = {
    "SHORT-TERM TRANSACTIONS FOR WHICH BASIS IS REPORTED TO THE IRS": "A",
    "SHORT-TERM TRANSACTIONS FOR WHICH BASIS IS NOT REPORTED TO THE IRS": "B",
    "LONG-TERM TRANSACTIONS FOR WHICH BASIS IS REPORTED TO THE IRS": "D",
    "LONG-TERM TRANSACTIONS FOR WHICH BASIS IS NOT REPORTED TO THE IRS": "E",
}

# Layout 1 summary-table columns, in left-to-right order, with the
# normalized header tokens that anchor each column.
_LAYOUT1_COLUMNS: list[tuple[str, set[str]]] = [
    ("proceeds", {"PROCEEDS"}),
    ("cost_basis", {"COST", "BASIS"}),
    ("market_discount", {"MARKET", "DISCOUNT"}),
    ("wash_disallowed", {"WASH", "SALES", "DISALLOWED"}),
    ("gain_loss", {"GAIN/LOSS", "GAIN", "LOSS"}),
    ("withheld", {"INCOME", "TAX", "WITHHELD", "FEDERAL"}),
]

_HEADER_TOKENS: set[str] = set()
for _name, _toks in _LAYOUT1_COLUMNS:
    _HEADER_TOKENS.update(_toks)

# Layout 2: 'Box <A-F> <Short|Long>-Term Realized Gain|Loss'.
_LAYOUT2_ROW_RE = re.compile(
    r"BOX ([A-F])\b.{0,40}(SHORT-TERM|LONG-TERM).{0,40}REALIZED (GAIN|LOSS)"
)
_LAYOUT2_NONCOVERED_RE = re.compile(
    r"NONCOVERED SHORT-TERM.*GROSS PROCEEDS"
)
_LAYOUT2_AMBIGUOUS_RES = [
    re.compile(r"BOX [A-F] OR BOX [A-F]"),  # e.g. 'Box B or Box E' -- no term
]
_LAYOUT2_TOTAL_RES = [
    re.compile(r"TOTAL (SHORT-TERM|LONG-TERM|UNKNOWN TERM)"),
]

# Section anchors (normalized) -> section kind.
_SECTION_ANCHORS: list[tuple[str, str]] = [
    ("DETAILS OF 1099-DIV TRANSACTIONS", "div"),
    ("TOTAL ORDINARY DIVIDENDS AND DISTRIBUTIONS DETAIL", "div"),
    ("SUMMARY OF INTEREST INCOME", "int"),
    ("INTEREST INCOME DETAILS", "int"),
    ("1099-B PROCEEDS FROM BROKER AND BARTER EXCHANGE TRANSACTIONS", "b1099"),
    ("REALIZED GAIN / LOSS SUMMARY", "b1099"),
    ("FORM 1099-B TOTALS SUMMARY", "b1099"),
]

_DIV_BOXES = ("1A", "1B", "2A", "2B", "2C", "2D", "2E", "2F", "3", "5", "7")
_INT_BOXES = ("1", "3", "8")

_EIN_RE = re.compile(r"\b(\d{2}-\d{7})\b")
_YEAR_CAL_RE = re.compile(r"FOR CALENDAR YEAR (20\d\d)")
_YEAR_TAX_RE = re.compile(r"TAX YEAR (20\d\d)")
_YEAR_ANY_RE = re.compile(r"\b(20\d\d)\b")
_ACCOUNT_RE = re.compile(
    r"ACCOUNT(?:\s+NUMBER|\s+NO\.?)?\s*[:#]?\s*([\dXx][\dXx\- ]{3,})",
    re.IGNORECASE,
)


def _default_vocab() -> dict:
    return {
        "layout_1": {
            "row_boxes": dict(_LAYOUT1_ROW_BOX),
            "columns": [name for name, _ in _LAYOUT1_COLUMNS],
        },
        "layout_2": {},
        "div_boxes": list(_DIV_BOXES),
        "int_boxes": list(_INT_BOXES),
    }


def load_vocab(path: str | None) -> dict:
    """Default census vocabulary merged with an optional --labels file."""
    vocab = _default_vocab()
    if not path:
        return vocab
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        _fail(f"cannot read labels file: {exc}")
    try:
        user = json.loads(raw)
    except ValueError as exc:
        _fail(f"labels file is not JSON: {exc}")
    if not isinstance(user, dict):
        _fail("labels file must be a JSON object")
    l1 = user.get("layout_1", {})
    if isinstance(l1, dict):
        for label, box in (l1.get("row_boxes") or {}).items():
            vocab["layout_1"]["row_boxes"][normalize_label(label)] = box
    return vocab

# ---------------------------------------------------------------------------
# PDF word extraction (pdfplumber is optional; imported lazily so the
# module loads on stdlib).
# ---------------------------------------------------------------------------

def _extract_pages(pdf_path: str) -> list[dict]:
    try:
        import pdfplumber
    except ImportError:
        _fail("pdfplumber is required for stmt-summary "
              "(pip install taxprep[pdf])")
    pages = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                # Tight x tolerance: table columns must not merge into
                # each other (inter-word spaces survive; intra-word
                # char gaps are ~1pt).
                words = page.extract_words(x_tolerance=2) or []
                pages.append({"width": float(page.width),
                              "height": float(page.height),
                              "words": words})
    except OSError as exc:
        _fail(f"cannot read PDF: {exc}")
    if not pages:
        _fail("PDF has no pages")
    return pages


def _line_text(line: list[dict]) -> str:
    return " ".join(str(w.get("text", "")) for w in line)


def _all_lines(pages: list[dict]) -> list[tuple[int, list[dict]]]:
    """(page_no, line) for every visual line, in reading order."""
    out = []
    for pi, page in enumerate(pages):
        for line in group_into_lines(page["words"]):
            out.append((pi, line))
    return out


def _page_text(pages: list[dict], upto: int | None = None) -> str:
    parts = []
    for pi, page in enumerate(pages):
        if upto is not None and pi >= upto:
            break
        for line in group_into_lines(page["words"]):
            parts.append(_line_text(line))
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Layout 1: Fidelity summary table (columns by header alignment).
# ---------------------------------------------------------------------------

def _find_header_band(lines: list[tuple[int, list[dict]]]
                       ) -> tuple[int, int, list[tuple[float, float]]] | None:
    """Locate the summary-table header band.

    Returns (line_idx, end_idx_exclusive, column_bounds) where
    column_bounds are (x_start, x_end) per canonical column, or None.
    """
    for pos in range(len(lines)):
        pi, line = lines[pos]
        n = normalize_label(_line_text(line))
        if "PROCEEDS" not in n or "COST" not in n:
            continue
        band = [(pi, line)]
        for pos2 in range(pos + 1, min(pos + 3, len(lines))):
            _pi2, line2 = lines[pos2]
            t2 = _line_text(line2)
            if _MONEY_WORD_RE.search(t2.replace(" ", "")) or \
                    parse_money_word(t2.split()[0] if t2.split() else ""):
                break
            n2 = normalize_label(t2)
            toks = set(n2.split())
            if toks and toks <= _HEADER_TOKENS and len(toks) <= 8:
                band.append(lines[pos2])
            else:
                break
        bounds = _column_bounds(band, line)
        if bounds is not None:
            return pos, pos + len(band), bounds
    return None


def _column_bounds(band: list[tuple[int, list[dict]]],
                   first_line: list[dict]) -> list[tuple[float, float]] | None:
    """Column x-intervals from header-word alignment.

    Each header word is assigned to the canonical column whose token set
    contains it; the column anchor is the mean x-center of its words and
    boundaries fall at midpoints between consecutive anchors.
    """
    page_width = 612.0
    anchors: list[list[float]] = [[] for _ in _LAYOUT1_COLUMNS]
    for _, line in band:
        for w in line:
            tok = normalize_label(str(w.get("text", "")))
            for ci, (_, toks) in enumerate(_LAYOUT1_COLUMNS):
                if tok in toks:
                    xc = (float(w["x0"]) + float(w["x1"])) / 2.0
                    anchors[ci].append(xc)
                    break
    # The three money columns are required; withheld may be absent.
    if not anchors[0] or not anchors[1] or not anchors[4]:
        return None
    centers = []
    for ci, xs in enumerate(anchors):
        if xs:
            centers.append(sum(xs) / len(xs))
        else:
            centers.append(None)
    # Fill gaps by interpolation between resolved neighbours.
    resolved = [(i, c) for i, c in enumerate(centers) if c is not None]
    filled: list[float | None] = list(centers)
    for k in range(len(resolved) - 1):
        i0, c0 = resolved[k]
        i1, c1 = resolved[k + 1]
        for j in range(i0 + 1, i1):
            filled[j] = c0 + (c1 - c0) * (j - i0) / (i1 - i0)
    # Drop trailing unresolved columns (e.g. no Withheld column).
    last = max(i for i, c in enumerate(filled) if c is not None)
    filled = filled[:last + 1]
    cs = [c for c in filled if c is not None]
    bounds: list[tuple[float, float]] = []
    for i, c in enumerate(cs):
        lo = 0.0 if i == 0 else (cs[i - 1] + c) / 2.0
        hi = page_width if i == len(cs) - 1 else (c + cs[i + 1]) / 2.0
        bounds.append((lo, hi))
    # Column names in the same order (may be fewer than 6).
    return bounds


def _col_index(xc: float, bounds: list[tuple[float, float]]) -> int | None:
    for i, (lo, hi) in enumerate(bounds):
        if lo <= xc < hi:
            return i
    return len(bounds) - 1 if xc >= bounds[-1][1] else 0


def _money_cells(line: list[dict]) -> list[tuple[Decimal, float, float]]:
    """(value, x_center, x0_of_word) for each money-shaped word."""
    out = []
    for w in line:
        d = parse_money_word(str(w.get("text", "")))
        if d is not None:
            xc = (float(w["x0"]) + float(w["x1"])) / 2.0
            out.append((d, xc, float(w["x0"])))
    return out


_LAYOUT1_COL_KEYS = ["proceeds", "cost_basis", "market_discount",
                     "wash_disallowed", "gain_loss", "withheld"]


def _parse_layout1_table(pages: list[dict], vocab: dict,
                         rep_unmatched: list[str],
                         flags: list[str]) -> dict[str, dict]:
    """Box -> {proceeds, cost_basis, wash, net, withheld} (Decimals/None)."""
    lines = _all_lines(pages)
    boxes: dict[str, dict] = {}
    pos = 0
    row_boxes = vocab["layout_1"]["row_boxes"]
    while pos < len(lines):
        found = _find_header_band(lines[pos:])
        if found is None:
            break
        rel_start, rel_end, bounds = found
        start = pos + rel_start
        n_cols = len(bounds)
        col_keys = _LAYOUT1_COL_KEYS[:n_cols]
        # Data rows follow the header band on the same page.
        page_of_start = lines[start][0]
        i = pos + rel_end
        while i < len(lines) and lines[i][0] == page_of_start:
            _, line = lines[i]
            n = normalize_label(_line_text(line))
            if "TOTAL" in n and "TRANSACTIONS FOR WHICH" not in n:
                i += 1
                continue  # section/total rows never seed
            cells = _money_cells(line)
            if not cells:
                i += 1
                continue
            first_x0 = min(x0 for _, _, x0 in cells)
            label_words = [w for w in line if float(w["x1"]) <= first_x0 + 1.0]
            label = normalize_label(_line_text(label_words))
            box = row_boxes.get(label)
            if box is None:
                for known, b in row_boxes.items():
                    if label.startswith(known):
                        box = b
                        break
            if box is None:
                rep_unmatched.append(_line_text(label_words)[:80])
                i += 1
                continue
            if box in boxes:
                # Same box twice (e.g. a continued table): keep the first,
                # flag loudly -- never silently overwrite or double-count.
                flags.append(f"dup_box_row:{box}")
                i += 1
                continue
            vals: dict[str, Decimal | None] = {k: None for k in _LAYOUT1_COL_KEYS}
            for d, xc, _x0 in cells:
                ci = _col_index(xc, bounds)
                if ci is not None and vals[col_keys[ci]] is None:
                    vals[col_keys[ci]] = d
            net = vals["gain_loss"]
            if vals["proceeds"] is not None and vals["cost_basis"] is not None \
                    and net is not None:
                expect = vals["proceeds"] - vals["cost_basis"] + \
                    (vals["wash_disallowed"] or Decimal("0"))
                if abs(net - expect) > Decimal("0.01"):
                    flags.append(f"net_mismatch:box_{box}")
            boxes[box] = {
                "proceeds": vals["proceeds"],
                "cost_basis": vals["cost_basis"],
                "wash": vals["wash_disallowed"],
                "net": net,
                "withheld": vals["withheld"],
                "market_discount": vals["market_discount"],
            }
            i += 1
        pos = i
    return boxes


# ---------------------------------------------------------------------------
# Layout 2: second payer 'REALIZED GAIN / LOSS SUMMARY'.
# ---------------------------------------------------------------------------

def _parse_layout2_rows(pages: list[dict],
                        rep_unmatched: list[str]) -> dict[str, dict]:
    """Box -> {proceeds, cost_basis, wash, net, withheld} from gain/loss rows.

    Layout 2 prints realized gain and loss per box, not proceeds/cost, so
    proceeds/cost/wash stay None and net = gain - loss.
    """
    acc: dict[tuple[str, str], dict[str, Decimal]] = {}
    for _pi, line in _all_lines(pages):
        text = _line_text(line)
        n = normalize_label(text)
        if any(rx.search(n) for rx in _LAYOUT2_TOTAL_RES):
            continue
        if any(rx.search(n) for rx in _LAYOUT2_AMBIGUOUS_RES):
            rep_unmatched.append(text[:80] + " [ambiguous box]")
            continue
        m = _LAYOUT2_ROW_RE.search(n)
        if m:
            box, term_w, gl = m.group(1), m.group(2), m.group(3)
            term = "st" if term_w == "SHORT-TERM" else "lt"
            cells = _money_cells(line)
            if not cells:
                rep_unmatched.append(text[:80] + " [no amount]")
                continue
            amt = cells[-1][0]
            key = (box, term)
            acc.setdefault(key, {"gain": Decimal("0"), "loss": Decimal("0")})
            acc[key]["gain" if gl == "GAIN" else "loss"] += amt
            continue
        if _LAYOUT2_NONCOVERED_RE.search(n):
            cells = _money_cells(line)
            if cells:
                key = ("B", "st")
                acc.setdefault(key, {"gain": Decimal("0"),
                                     "loss": Decimal("0"),
                                     "proceeds_only": cells[-1][0]})
    boxes: dict[str, dict] = {}
    for (box, term), v in acc.items():
        if "proceeds_only" in v:
            boxes[box] = {"proceeds": v["proceeds_only"], "cost_basis": None,
                          "wash": None, "net": None, "withheld": None,
                          "market_discount": None, "proceeds_only": True}
        else:
            boxes[box] = {"proceeds": None, "cost_basis": None, "wash": None,
                          "net": v["gain"] - v["loss"], "withheld": None,
                          "market_discount": None}
    return boxes

# ---------------------------------------------------------------------------
# 1099-DIV / 1099-INT / withholding sections (box-token anchored).
# ---------------------------------------------------------------------------

def _section_spans(lines: list[tuple[int, list[dict]]]
                   ) -> list[tuple[str, int, int]]:
    """(kind, start_line_idx, end_line_idx_exclusive) per anchored section."""
    spans = []
    for idx, (_pi, line) in enumerate(lines):
        n = normalize_label(_line_text(line))
        for anchor, kind in _SECTION_ANCHORS:
            if anchor in n:
                spans.append((kind, idx, len(lines)))
                break
    # End each span at the next span's start.
    out = []
    for s, (kind, start, _end) in enumerate(spans):
        end = spans[s + 1][1] if s + 1 < len(spans) else len(lines)
        out.append((kind, start, end))
    return out


def _box_amounts(lines: list[tuple[int, list[dict]]], kind: str,
                 boxes: tuple[str, ...],
                 rep_unmatched: list[str]) -> dict[str, Decimal]:
    """Box token -> amount within one section's lines.

    For each line, the first money token at/after a box token wins;
    duplicate box lines are summed (detail blocks repeat boxes).
    """
    found: dict[str, Decimal] = {}
    box_res = [(b, re.compile(r"\b" + re.escape(b) + r"\b")) for b in boxes]
    for _pi, line in lines:
        text = _line_text(line)
        n = normalize_label(text)
        for b, rx in box_res:
            m = rx.search(n)
            if not m:
                continue
            # Money tokens at or after the box token's word.
            words = line
            bi = None
            for wi, w in enumerate(words):
                if normalize_label(str(w.get("text", ""))) == b:
                    bi = wi
                    break
            cands = []
            for w in words[bi + 1 if bi is not None else 0:]:
                d = parse_money_word(str(w.get("text", "")))
                if d is not None:
                    cands.append(d)
            if cands:
                found[b] = found.get(b, Decimal("0")) + cands[0]
            else:
                rep_unmatched.append(f"{b}: " + text[:60])
            break
    return found


_WITHHOLD_PAT = re.compile(r"(FEDERAL )?INCOME TAX WITHHELD")


def _section_withholding(lines: list[tuple[int, list[dict]]]) -> Decimal:
    total = Decimal("0")
    for _pi, line in lines:
        n = normalize_label(_line_text(line))
        if _WITHHOLD_PAT.search(n):
            cells = _money_cells(line)
            if cells:
                total += cells[-1][0]
    return total


# ---------------------------------------------------------------------------
# File-level metadata (blind-safe: values never reach stdout).
# ---------------------------------------------------------------------------

def _file_metadata(pages: list[dict], raw: bytes, persons: dict,
                   rep_flags: list[str]) -> dict:
    head = _page_text(pages, upto=3)
    p1 = _page_text(pages, upto=1)
    head_n = normalize_label(head)

    m = _EIN_RE.search(head)
    if not m:
        _fail("payer EIN not found (expected NN-NNNNNNN on first pages)")
    ein = m.group(1)

    year = None
    for rx in (_YEAR_CAL_RE, _YEAR_TAX_RE):
        mm = rx.search(head_n)
        if mm:
            year = int(mm.group(1))
            break
    if year is None:
        _fail("tax year not found (expected 'For calendar year YYYY')")
    if year not in SUPPORTED_YEARS:
        _fail(f"tax year {year} outside supported range")

    am = _ACCOUNT_RE.search(p1)
    if am:
        acct_raw = re.sub(r"[\s\-]", "", am.group(1))
    else:
        acct_raw = ""
    if len(re.sub(r"\D", "", acct_raw)) >= 4:
        acct_id = hashlib.sha256((ein + acct_raw).encode()).hexdigest()[:8]
    else:
        fid = hashlib.sha256(raw).hexdigest()[:16]
        acct_id = hashlib.sha256((ein + fid).encode()).hexdigest()[:8]
        rep_flags.append("no_account_number")

    corrected = bool(re.search(r"\bCORRECTED\b", head, re.IGNORECASE))

    person = "UNMAPPED"
    p1n = normalize_label(p1)
    for key, pval in persons.items():
        if normalize_label(key) and normalize_label(key) in p1n:
            person = pval
            break
    if person == "UNMAPPED":
        rep_flags.append("person_unmapped")

    return {"payer_ein": ein, "acct_id": acct_id, "year": year,
            "person": person, "corrected": corrected}

# ---------------------------------------------------------------------------
# Per-file parse -> record.
# ---------------------------------------------------------------------------

_BOX_TERM = {"A": "st", "B": "st", "C": "st",
             "D": "lt", "E": "lt", "F": "lt"}


def _totals(boxes: dict[str, dict], box_letters: str) -> dict[str, Decimal | None]:
    out: dict[str, Decimal | None] = {"proceeds": None, "cost_basis": None,
                                      "wash": None, "net": None}
    for key in ("proceeds", "cost_basis", "wash", "net"):
        vals = [boxes[b][key] for b in box_letters
                if b in boxes and boxes[b].get(key) is not None]
        out[key] = sum(vals, Decimal("0")) if vals else None
    return out


def parse_statement_pdf(pdf_path: str, vocab: dict, persons: dict,
                        identity: list[str] | None = None) -> dict:
    """Parse one consolidated-1099 PDF into a blind-safe record.

    Raises _SummaryError (loud) when the file cannot be parsed.
    ``identity`` phrases redact echoed label text (defense in depth;
    stdout never carries values regardless).
    """
    raw = Path(pdf_path).read_bytes()
    file_id = hashlib.sha256(raw).hexdigest()[:16]
    pages = _extract_pages(pdf_path)
    flags: list[str] = []
    unmatched: list[str] = []
    meta = _file_metadata(pages, raw, persons, flags)

    boxes = _parse_layout1_table(pages, vocab, unmatched, flags)
    layout = "layout_1" if boxes else None
    if not boxes:
        boxes = _parse_layout2_rows(pages, unmatched)
        layout = "layout_2" if boxes else None
    if not boxes:
        _fail("no 1099-B summary found (layout_1 headers and "
              "layout_2 rows both absent)")
    if any(b.get("proceeds_only") for b in boxes.values()):
        flags.append("proceeds_only_box")

    lines = _all_lines(pages)
    spans = _section_spans(lines)
    div: dict[str, Decimal] = {}
    intb: dict[str, Decimal] = {}
    sec_wh = Decimal("0")
    for kind, s, e in spans:
        seg = lines[s:e]
        if kind == "div":
            for b, d in _box_amounts(seg, kind, tuple(vocab["div_boxes"]),
                                     unmatched).items():
                div[b] = div.get(b, Decimal("0")) + d
            sec_wh += _section_withholding(seg)
        elif kind == "int":
            for b, d in _box_amounts(seg, kind, tuple(vocab["int_boxes"]),
                                     unmatched).items():
                intb[b] = intb.get(b, Decimal("0")) + d
            sec_wh += _section_withholding(seg)

    box_wh = sum((b["withheld"] for b in boxes.values()
                  if b.get("withheld") is not None), Decimal("0"))
    withheld_total = box_wh + sec_wh

    rec: dict = {
        "file_id": file_id,
        "filename": Path(pdf_path).name,
        "payer_ein": meta["payer_ein"],
        "acct_id": meta["acct_id"],
        "year": meta["year"],
        "person": meta["person"],
        "corrected": meta["corrected"],
        "layout": layout,
        "boxes": {b: {k: _fmt(v.get(k)) for k in
                       ("proceeds", "cost_basis", "wash", "net",
                        "withheld", "market_discount")}
                  for b, v in boxes.items()},
        "_sums": boxes,  # Decimal sums kept aside; stripped before JSON
        "st_total": {k: _fmt(v) for k, v in
                     _totals(boxes, "ABC").items()},
        "lt_total": {k: _fmt(v) for k, v in
                     _totals(boxes, "DEF").items()},
        "div": {b: _fmt(d) for b, d in sorted(div.items())},
        "int": {b: _fmt(d) for b, d in sorted(intb.items())},
        "withholding_total": _fmt(withheld_total),
        "unmatched_labels": sorted(set(unmatched)),
        "flags": sorted(set(flags)),
    }
    if identity:
        red = [u for u in rec["unmatched_labels"]
               if not any(ident and ident.lower() in u.lower()
                          for ident in identity)]
        if len(red) != len(rec["unmatched_labels"]):
            rec["flags"].append("identity_redacted_label")
        rec["unmatched_labels"] = sorted(set(red))
    return rec


def _public_record(rec: dict) -> dict:
    """Record minus internal Decimal working state (for JSON output)."""
    return {k: v for k, v in rec.items() if not k.startswith("_")}


# ---------------------------------------------------------------------------
# Duplicates: (EIN, acct_id, year) -> keep corrected, else richest, else first.
# ---------------------------------------------------------------------------

def dedupe(records: list[dict]) -> tuple[list[dict], list[dict]]:
    """Returns (kept, pairs). pairs describe every collapsed duplicate set."""
    groups: dict[tuple, list[dict]] = {}
    for r in records:
        groups.setdefault((r["payer_ein"], r["acct_id"], r["year"]), []).append(r)
    kept: list[dict] = []
    pairs: list[dict] = []
    for key, rs in sorted(groups.items()):
        if len(rs) == 1:
            kept.append(rs[0])
            continue

        def richness(r: dict) -> int:
            return sum(1 for b in r["boxes"].values()
                       if any(b.get(k) for k in ("proceeds", "net")))

        ordered = sorted(rs, key=lambda r: (r["corrected"], richness(r)),
                         reverse=True)
        # sorted() is stable: ties resolve to first-seen order.
        best = ordered[0]
        kept.append(best)
        pairs.append({
            "key": {"payer_ein": key[0], "acct_id": key[1], "year": key[2]},
            "kept": best["file_id"],
            "dropped": [r["file_id"] for r in rs if r["file_id"] != best["file_id"]],
            "reason": ("corrected" if best["corrected"]
                       else "richest" if richness(best) > min(
                           richness(r) for r in rs) else "first_seen"),
        })
    return kept, pairs


# ---------------------------------------------------------------------------
# Seed sheet (exact R24(a) schema) and --template.
# ---------------------------------------------------------------------------

def seed_rows(records: list[dict]) -> list[dict]:
    rows = []
    for r in records:
        for box in "ABCDEF":
            b = r["boxes"].get(box)
            if not b:
                continue
            rows.append({
                "year": str(r["year"]),
                "payer_ein": r["payer_ein"],
                "acct_id": r["acct_id"],
                "person": r["person"],
                "box": box,
                "proceeds": b.get("proceeds") or "",
                "cost_basis": b.get("cost_basis") or "",
                "wash_sale_disallowed": b.get("wash") or "",
                "net": b.get("net") or "",
                "term": _BOX_TERM[box],
                "source_sha16": r["file_id"],
                "corrected": "Y" if r["corrected"] else "",
            })
    rows.sort(key=lambda x: (x["year"], x["payer_ein"], x["acct_id"], x["box"]))
    return rows


def write_seed_csv(rows: list[dict]) -> str:
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=list(SEED_COLUMNS))
    w.writeheader()
    for r in rows:
        w.writerow({c: r.get(c, "") for c in SEED_COLUMNS})
    return out.getvalue()


def seed_template() -> str:
    """Empty seed-sheet.csv with fail-loud placeholders (cf. W-2 template).

    Every placeholder trips chain._parse_seed_sheet loudly, so an
    unfilled template can never ingest silently.
    """
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(list(SEED_COLUMNS))
    w.writerow(["YYYY", "NN-NNNNNNN", "________", "<<< person-N >>>", "A",
                "___.__", "___.__", "___.__", "___.__", "st",
                "________________", ""])
    return out.getvalue()

# ---------------------------------------------------------------------------
# Reconciliation.
# ---------------------------------------------------------------------------

# 8949 box -> (term, schedule-d category) for the as-filed comparison.
_BOX_CAT = {
    "A": ("st", "basis"), "B": ("st", "no_basis"), "C": ("st", "no_1099b"),
    "D": ("lt", "basis"), "E": ("lt", "no_basis"), "F": ("lt", "no_1099b"),
}

_CENT = Decimal("0.01")


def _transcript_scans(csv_dir: str, identity_file: str | None,
                      years: set[int]) -> dict[int, object]:
    """Parse transcript CSVs with chain.py's machinery (reuse, not copy)."""
    from .chain import _discover, _scan_file, _YearScan, _load_identity
    scans: dict[int, object] = {}
    identity = _load_identity(identity_file)
    for frec in _discover(Path(csv_dir)):
        if frec["kind"] not in ("return", "wi"):
            continue
        if frec["year"] not in years:
            continue
        sc = scans.setdefault(frec["year"], _YearScan(frec["year"]))
        _scan_file(sc, frec, identity)
    return scans


def _as_filed_by_category(scan) -> dict[tuple[str, str], dict[str, Decimal]]:
    """(term, category) -> {sale, cost, adj} as-entered (PER COMPUTER out)."""
    agg: dict[tuple[str, str, str], Decimal] = {}
    for (term, cat, field, variant), entries in scan.sched_d.items():
        if variant != "as_entered" or not term or cat == "tc":
            continue
        key = (term, cat, field)
        agg[key] = agg.get(key, Decimal("0")) + sum(
            v for v, _lbl, _row, _fid in entries)
    out: dict[tuple[str, str], dict[str, Decimal]] = {}
    for term in ("st", "lt"):
        for cat in ("basis", "no_basis", "no_1099b"):
            sale = agg.get((term, cat, "sale"), Decimal("0"))
            cost = agg.get((term, cat, "cost"), Decimal("0"))
            adj = agg.get((term, cat, "adjustments"), Decimal("0"))
            if cat == "basis":
                # The transcript splits 'basis, no adjustments' out; both
                # roll into the 8949 box on the filed return.
                sale += agg.get((term, "basis_no_adj", "sale"), Decimal("0"))
                cost += agg.get((term, "basis_no_adj", "cost"), Decimal("0"))
            out[(term, cat)] = {"sale": sale, "cost": cost, "adj": adj}
    return out


def _wi_proceeds_sum(scan) -> Decimal | None:
    """Sum of 1099-B proceeds rows in W&I CSVs (same rule as chain)."""
    from .chain import parse_money
    total = Decimal("0")
    found = False
    for item in scan.raw_rows:
        if item["kind"] != "wi":
            continue
        row = item["row"]
        n = row["normalized"]
        if "1099" in n and "PROCEEDS" in n and re.search(r"\bB\b", n):
            found = True
            total += parse_money(row["printed_label"], row["csv_row"],
                                 row["value"])
    return total if found else None


def reconcile_year(year: int, records: list[dict], pairs: list[dict],
                   scans: dict[int, object] | None,
                   rep: _Reporter) -> dict:
    """Reconciliation for one year. Values stay in the returned dict."""
    rep_out: dict = {"year": year, "duplicates": pairs}

    # -- per-box sums from the statements --
    sums: dict[str, dict[str, Decimal]] = {}
    for r in records:
        for box, vals in r["_sums"].items():
            s = sums.setdefault(box, {"proceeds": Decimal("0"),
                                      "cost": Decimal("0"),
                                      "wash": Decimal("0"),
                                      "net": Decimal("0"),
                                      "n": 0})
            for k in ("proceeds", "cost_basis", "wash", "net"):
                v = vals.get(k)
                if v is not None:
                    s["proceeds" if k == "proceeds" else
                      "cost" if k == "cost_basis" else
                      "wash" if k == "wash" else "net"] += v
            s["n"] += 1

    # -- Schedule D as-filed comparison --
    if scans is not None and year in scans:
        as_filed = _as_filed_by_category(scans[year])
        diffs = []
        for box in sorted(sums):
            term, cat = _BOX_CAT[box]
            af = as_filed[(term, cat)]
            mine = sums[box]
            for mine_k, af_k in (("proceeds", "sale"), ("cost", "cost"),
                                 ("wash", "adj")):
                if abs(mine[mine_k] - af[af_k]) > _CENT:
                    diffs.append({"box": box, "field": mine_k,
                                  "statements": format(mine[mine_k], ".2f"),
                                  "as_filed": format(af[af_k], ".2f")})
        rep_out["sched_d"] = {"status": "pass" if not diffs else "fail",
                              "n_diffs": len(diffs), "diffs": diffs}
        rep.check(f"sched_d_recon_{year}",
                  "pass" if not diffs else "fail",
                  f"{len(diffs)} diff(s)" if diffs else "cent-exact")
    else:
        rep_out["sched_d"] = {"status": "skip",
                              "reason": "no return transcript scan"}
        rep.check(f"sched_d_recon_{year}", "skip", "no return transcript")

    # -- W&I partial comparison --
    if scans is not None and year in scans:
        wi = _wi_proceeds_sum(scans[year])
        stmt = sum((s["proceeds"] for s in sums.values()), Decimal("0"))
        if wi is None:
            rep_out["wi"] = {"status": "skip",
                             "reason": "no 1099-B proceeds rows in W&I"}
            rep.check(f"wi_crosscheck_{year}", "skip", "no proceeds rows")
        else:
            ok = wi <= stmt
            rep_out["wi"] = {"status": "pass" if ok else "fail",
                             "wi_proceeds_sum": format(wi, ".2f"),
                             "stmt_proceeds_sum": format(stmt, ".2f")}
            rep.check(f"wi_crosscheck_{year}", "pass" if ok else "fail",
                      "partial sum within statements" if ok
                      else "W&I exceeds statements")
    else:
        rep_out["wi"] = {"status": "skip", "reason": "no W&I scan"}
        rep.check(f"wi_crosscheck_{year}", "skip", "no W&I data")

    return rep_out


# ---------------------------------------------------------------------------
# Outputs + entry point.
# ---------------------------------------------------------------------------

def _ensure_out(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    os.chmod(path, 0o700)


def _write_file(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
    os.chmod(path, 0o600)


def run(*, pdfs: list[str], labels: str | None = None,
        persons_file: str | None = None, identity_file: str | None = None,
        csv_dir: str | None = None, out: str | None = None,
        template: bool = False) -> int:
    """R24(b) entry point. Returns process exit code."""
    import sys
    rep = _Reporter()
    if template:
        sys.stdout.write(seed_template())
        return 0
    if not pdfs:
        _fail("no PDFs given (use --pdf-dir and/or --pdfs)")
    if not out:
        _fail("--out is required")

    vocab = load_vocab(labels)
    persons: dict = {}
    if persons_file:
        try:
            persons = json.loads(Path(persons_file).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            _fail(f"cannot read persons file: {exc}")
        if not isinstance(persons, dict):
            _fail("persons file must be a JSON object")

    records: list[dict] = []
    failures: list[dict] = []
    for pdf in sorted(set(pdfs)):
        try:
            rec = parse_statement_pdf(pdf, vocab, persons)
        except _SummaryError as exc:
            try:
                fid = hashlib.sha256(Path(pdf).read_bytes()).hexdigest()[:16]
            except OSError:
                fid = Path(pdf).name
            failures.append({"file_id": fid, "reason": str(exc)})
            rep.line(f"file {fid}: FAILED ({exc})")
            continue
        except Exception as exc:  # never silent: label the crash, keep going
            fid = hashlib.sha256(Path(pdf).read_bytes()).hexdigest()[:16]
            failures.append({"file_id": fid,
                             "reason": f"internal error: {type(exc).__name__}"})
            rep.line(f"file {fid}: FAILED (internal error)")
            continue
        records.append(rec)
        n_boxes = len(rec["boxes"])
        flag_txt = f", flags: {','.join(rec['flags'])}" if rec["flags"] else ""
        rep.line(f"file {rec['file_id']}: {n_boxes} box(es), "
                 f"{rec['layout']}, year {rec['year']}, "
                 f"{'corrected' if rec['corrected'] else 'original'}"
                 f"{flag_txt}")
        if rec["unmatched_labels"]:
            rep.line(f"  unmatched labels: {len(rec['unmatched_labels'])} "
                     f"(see reconciliation file)")

    kept, pairs = dedupe(records)
    rep.check("dup_resolution", "pass",
              f"{len(records)} file(s), {len(pairs)} duplicate set(s)")

    by_year: dict[int, list[dict]] = {}
    for r in kept:
        by_year.setdefault(r["year"], []).append(r)

    scans = None
    if csv_dir:
        try:
            scans = _transcript_scans(csv_dir, identity_file, set(by_year))
        except Exception as exc:
            _fail(f"transcript scan failed: {type(exc).__name__}: {exc}")

    out_path = Path(out)
    ok = not failures
    for year in sorted(by_year):
        ydir = out_path / str(year)
        _ensure_out(ydir)
        yrecs = by_year[year]
        _write_file(ydir / "statements.json",
                    json.dumps({"year": year, "n_files": len(yrecs),
                                "files": [_public_record(r) for r in yrecs]},
                               indent=2) + "\n")
        _write_file(ydir / "seed-sheet.csv",
                    write_seed_csv(seed_rows(yrecs)))
        recon = reconcile_year(year, yrecs,
                               [p for p in pairs if p["key"]["year"] == year],
                               scans, rep)
        _write_file(ydir / "reconciliation.json",
                    json.dumps(recon, indent=2) + "\n")
        if recon["sched_d"]["status"] == "fail" or \
                recon["wi"]["status"] == "fail":
            ok = False

    if failures:
        rep.check("file_parse", "fail", f"{len(failures)} file(s) failed")
        ok = False
    else:
        rep.check("file_parse", "pass", f"{len(records)} file(s) parsed")
    rep.emit()
    return 0 if ok else 1
