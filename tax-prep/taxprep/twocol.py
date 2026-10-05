"""R23 stream A: positional two-column transcript capture.

Workstation-validated algorithm (a standalone operator tool run over 23
real IRS transcripts, 2016-2025): pdfplumber word boxes -> lines
(y-tolerance 2.5 pt) -> drop dot-leader tokens -> split at the largest
horizontal gap when it is >= 14 pt, the right side ends past 55% of the
page width, and the value starts past 35% of the page width.

This module is purely positional: NO label -> canonical-key mappings live
here. The label dictionary is a separate stream's Operator-editable data
file. Other R23 streams import ``normalize_label`` from this module; the
import direction stays one-way -- twocol imports nothing from the other
new R23 modules.
"""

from __future__ import annotations

import re
from pathlib import Path

TWOCOL_VERSION = "1.0"
TWOCOL_EXTRACTOR_ID = f"twocol:{TWOCOL_VERSION}"

# Split geometry (PDF points), workstation-validated on real transcripts.
LINE_Y_TOLERANCE = 2.5   # max |top delta| within one visual line
MIN_SPLIT_GAP = 14.0     # largest horizontal gap splits iff >= this (inclusive)
RIGHT_END_MIN = 0.55     # the line's right end must be PAST 55% of page width
VALUE_START_MIN = 0.35   # the value's first word must start PAST 35% of width

# Dot-leader tokens: dots only (any count) -- dropped before the split.
_DOT_LEADER_RE = re.compile(r"^[.\u00b7\u2026]+$")


def normalize_label(s: str) -> str:
    """Canonical pair-key form of a printed label.

    Strip, collapse internal whitespace runs (spaces, tabs, newlines) to
    single spaces, UPPERCASE. This is the form pair fields are keyed by in
    ingest; the label -> canonical-key mapping lives elsewhere.
    """
    return re.sub(r"\s+", " ", (s or "").strip()).upper()


def is_dot_leader(text: str) -> bool:
    """True for a dot-leader word token (dots only, e.g. ".....")."""
    return bool(text) and _DOT_LEADER_RE.match(text.strip()) is not None


def group_into_lines(words: list[dict], y_tol: float = LINE_Y_TOLERANCE
                     ) -> list[list[dict]]:
    """Group pdfplumber word dicts into visual text lines.

    Words are expected to carry ``top``, ``x0`` and ``text``. A word joins
    the current line while its ``top`` stays within ``y_tol`` of the line's
    first word; otherwise it starts a new line. Returns lines ordered
    top-to-bottom, each line's words left-to-right. Deterministic.
    """
    live = [w for w in (words or [])
            if w.get("text") and str(w.get("text")).strip()]
    ordered = sorted(live, key=lambda w: (float(w["top"]), float(w["x0"])))
    lines: list[list[dict]] = []
    for w in ordered:
        if lines and abs(float(w["top"]) - float(lines[-1][0]["top"])) <= y_tol:
            lines[-1].append(w)
        else:
            lines.append([w])
    for line in lines:
        line.sort(key=lambda w: float(w["x0"]))
    return lines


def split_line(words: list[dict], page_width: float,
               min_gap: float = MIN_SPLIT_GAP,
               right_end_min: float = RIGHT_END_MIN,
               value_start_min: float = VALUE_START_MIN
               ) -> tuple[list[dict], list[dict]] | None:
    """Split one line's word boxes into (label_words, value_words).

    Splits at the largest horizontal gap between consecutive words when:
    (a) the gap is >= ``min_gap`` points (boundary inclusive),
    (b) the line's right end (last word x1) is past
        ``right_end_min`` * page_width,
    (c) the right side's first word (x0) starts past
        ``value_start_min`` * page_width.
    Returns None for label-only rows (single word, no qualifying gap, or
    a right side that fails (b)/(c)). Gap ties split at the leftmost gap --
    deterministic.
    """
    if len(words) < 2:
        return None
    best, best_gap = -1, -1.0
    for i in range(len(words) - 1):
        gap = float(words[i + 1]["x0"]) - float(words[i]["x1"])
        if gap > best_gap:
            best, best_gap = i, gap
    if best < 0 or best_gap < min_gap:
        return None
    if float(words[-1]["x1"]) <= right_end_min * page_width:
        return None
    if float(words[best + 1]["x0"]) <= value_start_min * page_width:
        return None
    return words[:best + 1], words[best + 1:]


def _line_bbox_bl(words: list[dict], page_height: float) -> list[float]:
    """Union bbox of word boxes as [x0, y0, x1, y1], origin bottom-left.

    pdfplumber word boxes are origin top-left; the R15 contract is origin
    bottom-left, so y flips against the page height.
    """
    x0 = min(float(w["x0"]) for w in words)
    x1 = max(float(w["x1"]) for w in words)
    top = min(float(w["top"]) for w in words)
    bottom = max(float(w["bottom"]) for w in words)
    return [round(x0, 2), round(page_height - bottom, 2),
            round(x1, 2), round(page_height - top, 2)]


def capture_page_pairs(words: list[dict], page_width: float,
                       page_height: float, page_number: int
                       ) -> list[tuple[str, str, list[float], int]]:
    """Split one page's word boxes into (label, value, bbox, page) rows.

    Dot-leader tokens are dropped before the split. Rows that do not
    qualify for a split are returned as label-only rows with value "".
    bbox is [x0, y0, x1, y1] in PDF points, origin bottom-left (the R15
    contract). page_number is 1-based. Reading order is preserved.
    """
    rows: list[tuple[str, str, list[float], int]] = []
    for line in group_into_lines(words):
        kept = [w for w in line if not is_dot_leader(str(w.get("text", "")))]
        if not kept:
            continue
        bbox = _line_bbox_bl(kept, page_height)
        label_text = " ".join(str(w["text"]) for w in kept)
        split = split_line(kept, page_width)
        if split is None:
            rows.append((label_text, "", bbox, page_number))
            continue
        label_words, value_words = split
        label = " ".join(str(w["text"]) for w in label_words)
        value = " ".join(str(w["text"]) for w in value_words)
        rows.append((label, value, bbox, page_number))
    return rows


def capture_pairs(pdf_path: str | Path
                  ) -> list[tuple[str, str, list[float], int]]:
    """Positional two-column capture over a digital PDF.

    Returns a flat list of (label, value, bbox, page_number) rows in page
    then reading order, label-only rows carrying value "". label/value are
    the verbatim printed texts (label/value pairing only -- no
    label -> canonical-key mapping here). Raises FileNotFoundError for a
    missing path; lets pdfplumber raise for unreadable PDFs.
    """
    path = Path(pdf_path)
    if not path.is_file():
        raise FileNotFoundError(f"twocol: no such PDF: {path}")
    import pdfplumber  # local import: pdfplumber is an ingest-path dep

    rows: list[tuple[str, str, list[float], int]] = []
    with pdfplumber.open(str(path)) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            words = page.extract_words()
            rows.extend(capture_page_pairs(words, float(page.width),
                                           float(page.height),
                                           page_number))
    return rows
