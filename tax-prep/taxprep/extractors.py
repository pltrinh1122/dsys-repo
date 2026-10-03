"""Field extraction from OCR text of US tax forms.

Local-only, dependency-free (stdlib ``re`` only). Synthetic-fixture friendly:
no names, EINs, or amounts in this module are real.

Main entry point
----------------
``extract_fields(form_type, text)`` returns ``(fields, status)`` where
``fields`` maps each box code of the form to
``{"value": float | str | None, "confidence": "high"|"medium"|"low",
"raw_text": str}`` and ``status`` is ``"transcribed"`` when every KEY box of
the form was found with high/medium confidence, else ``"needs_review"``.

Supporting helpers
------------------
``classify_form(text)`` — classify text into a ``form_type`` using
per-section form-title anchors (instruction/notice sections excluded from
scoring, parenthesized "(Form 1040)" mentions treated as references).

``split_form_sections(pages)`` — split per-page texts into ``FormSection``
spans at title anchors, for multi-form files (consolidated 1099s, stacked
scans).

``detect_tax_year(text)`` — find a 4-digit tax year (2000-2030) near tax-year
phrases or in a form header line.
"""

import re
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MONEY_RE = r"[\$]?([\d,]+\.\d{2})"
_MONEY_RE_NODOLLAR = r"([\d,]+\.\d{2})"


def _parse_money(s: str) -> float | None:
    """Strip '$' and commas, parse a float. Returns None on failure."""
    try:
        return float(s.replace("$", "").replace(",", "").strip())
    except (ValueError, AttributeError):
        return None


def _field(value, confidence, raw_text):
    return {"value": value, "confidence": confidence, "raw_text": raw_text}


def _missing_field():
    """Standard low-confidence field for a box that was not found."""
    return _field(None, "low", "")


def _money_search(patterns, text):
    """Return (value, raw_text, is_labeled) for the first money pattern that
    matches. ``patterns`` is a list of (regex, labeled_bool). ``labeled``
    patterns drive "high" confidence; unlabeled ones drive "medium".
    """
    for pattern, labeled in patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            value = _parse_money(m.group(1))
            if value is not None:
                return value, m.group(0), labeled
    return None, "", False


def _str_search(patterns, text):
    """Return (value, raw_text, is_labeled) for the first string pattern that
    matches. ``patterns`` is a list of (regex, labeled_bool, group_index or
    callable transforming the match into the value).
    """
    for pattern, labeled, transform in patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            if callable(transform):
                value = transform(m)
            else:
                value = m.group(transform).strip()
            if value:
                return value, m.group(0), labeled
    return None, "", False


def _box_field(text, label_patterns, box_num, value_transform=None):
    """Extract a money box field.

    ``label_patterns``: list of (regex, group_index) tried first -> "high".
    Fallback: generic ``Box <num>`` pattern -> "medium".
    """
    high_pats = [(p, True) for p, _ in label_patterns]
    # Normalize: wrap each high pattern so group(1) is the amount. label
    # patterns are written with the money group as group(1).
    value, raw, labeled = _money_search(high_pats, text)
    if value is not None:
        return _field(value, "high", raw)
    fallback = re.compile(
        r"Box\s*" + re.escape(str(box_num)) + r"[^\d\n]*?\$?" + _MONEY_RE_NODOLLAR,
        re.IGNORECASE,
    )
    m = fallback.search(text)
    if m:
        value = _parse_money(m.group(1))
        if value is not None:
            return _field(value, "medium", m.group(0))
    return _missing_field()


# ---------------------------------------------------------------------------
# Form-title anchors for classification
# ---------------------------------------------------------------------------
#
# Classification is anchor-based: a form is recognized by its printed title
# ("Form 1099-B", "Wage and Tax Statement", ...), matched per page/section.
# Rules (all deterministic, stdlib ``re`` only):
#
# - Instruction/notice sections ("Instructions for Recipient",
#   "Notice to Employee", ...) are cut out before scoring and are never
#   classified as forms.
# - Parenthesized "(Form 1040)" mentions are references, not titles.
# - Bare form names ("Schedule D", "Interest Income", ...) count as anchors
#   only at the start of a line; "Form NNNN" titles count anywhere. (A Form
#   1040 that says "attach Schedule D" mid-sentence is not a Schedule D.)
# - On a page carrying a transcript title (Wage and Income / Tax Return /
#   Account / Record of Account), inner form mentions are content, not
#   titles: the transcript anchor suppresses the other anchors on that page.
#
# Table entries: (form_type, regex, line_start_only).

_FORM_TITLE_ANCHORS: list[tuple[str, str, bool]] = [
    ("WAGE_INCOME_TRANSCRIPT", r"WAGE\s+AND\s+INCOME\s+TRANSCRIPT", True),
    ("RECORD_OF_ACCOUNT", r"RECORD\s+OF\s+ACCOUNT", True),
    ("ACCOUNT_TRANSCRIPT", r"ACCOUNT\s+TRANSCRIPT\b", True),
    ("RETURN_TRANSCRIPT", r"TAX\s+RETURN\s+TRANSCRIPT", True),
    ("1040-X", r"FORM\s+1040-?X\b", False),
    ("1040-X", r"AMENDED\s+(?:U\.?S\.?\s+)?INDIVIDUAL\s+INCOME\s+TAX\s+RETURN", True),
    ("1040", r"FORM\s+1040\b", False),
    ("1040", r"U\.?S\.?\s+INDIVIDUAL\s+INCOME\s+TAX\s+RETURN", True),
    ("SCHEDULE_D", r"SCHEDULE\s+D\b", True),
    ("SCHEDULE_D", r"CAPITAL\s+GAINS\s+AND\s+LOSSES", True),
    ("W-2", r"FORM\s+W-?2\b", False),
    ("W-2", r"WAGE\s+AND\s+TAX\s+STATEMENT", True),
    ("1099-B", r"FORM\s+1099-?B\b", False),
    ("1099-B", r"PROCEEDS\s+FROM\s+BROKER\s+AND\s+BARTER\s+EXCHANGE\s+TRANSACTIONS", True),
    ("1099-INT", r"FORM\s+1099-?INT\b", False),
    ("1099-INT", r"INTEREST\s+INCOME", True),
    ("1099-DIV", r"FORM\s+1099-?DIV\b", False),
    ("1099-DIV", r"DIVIDENDS\s+AND\s+DISTRIBUTIONS", True),
    ("1099-NEC", r"FORM\s+1099-?NEC\b", False),
    ("1099-NEC", r"NONEMPLOYEE\s+COMPENSATION", True),
    ("1099-R", r"FORM\s+1099-?R\b", False),
    ("1099-R", r"DISTRIBUTIONS\s+FROM\s+PENSIONS", True),
    ("1099-MISC", r"FORM\s+1099-?MISC\b", False),
    ("1099-MISC", r"MISCELLANEOUS\s+INFORMATION", True),
    ("1098", r"FORM\s+1098\b", False),
    ("1098", r"MORTGAGE\s+INTEREST\s+STATEMENT", True),
]

_TRANSCRIPT_TYPES = frozenset({
    "WAGE_INCOME_TRANSCRIPT",
    "RETURN_TRANSCRIPT",
    "ACCOUNT_TRANSCRIPT",
    "RECORD_OF_ACCOUNT",
})


def _compile_anchor(pattern: str, line_start_only: bool) -> re.Pattern:
    if line_start_only:
        pattern = r"(?m)^[ \t]*" + pattern
    return re.compile(pattern, re.IGNORECASE)


_ANCHOR_RES: list[tuple[str, re.Pattern]] = [
    (form_type, _compile_anchor(pattern, line_start_only))
    for form_type, pattern, line_start_only in _FORM_TITLE_ANCHORS
]

# Instruction/notice headings. A heading must be followed by a colon or end
# of line so that mid-sentence mentions ("see Notice to Employee for
# details") do not cut the page.
_EXCLUDED_HEADING_RE = re.compile(
    r"(?:INSTRUCTIONS\s+FOR\s+(?:RECIPIENT|PAYER)"
    r"|NOTICE\s+TO\s+EMPLOYEE"
    r"|(?:GENERAL|SPECIFIC)\s+INSTRUCTIONS"
    r"|INSTRUCTIONS\s+FOR\s+FORM)"
    r"(?=\s*(?::|$))",
    re.IGNORECASE | re.MULTILINE,
)

# Parenthesized form mentions, e.g. "Schedule D (Form 1040)": references,
# never titles.
_FORM_REFERENCE_RE = re.compile(
    r"\(\s*[^()]*\bFORM\s+1040\b[^()]*\)", re.IGNORECASE
)


def _strip_form_references(text: str) -> str:
    """Remove parenthesized "(Form 1040)"-style mentions."""
    return _FORM_REFERENCE_RE.sub(" ", text)


def _find_title_anchors(text: str) -> list[tuple[int, int, str]]:
    """All (start, end, form_type) title-anchor matches, in position order.

    Overlaps resolve to the earliest start, then the longest match, then
    table order (so "Form 1040-X" beats "Form 1040" at the same start).
    """
    cands: list[tuple[int, int, str]] = []
    order = {ft: i for i, (ft, _p, _l) in enumerate(_FORM_TITLE_ANCHORS)}
    for form_type, rx in _ANCHOR_RES:
        for m in rx.finditer(text):
            cands.append((m.start(), m.end(), form_type))
    # Bare "RETURN TRANSCRIPT" counts as a transcript title only with 1040
    # nearby (legacy rule, kept).
    if "1040" in text.upper() and not re.search(
        r"TAX\s+RETURN\s+TRANSCRIPT", text, re.IGNORECASE
    ):
        for m in re.finditer(r"\bRETURN\s+TRANSCRIPT\b", text, re.IGNORECASE):
            cands.append((m.start(), m.end(), "RETURN_TRANSCRIPT"))
    cands.sort(key=lambda c: (c[0], -(c[1] - c[0]), order[c[2]]))
    kept: list[tuple[int, int, str]] = []
    for start, end, form_type in cands:
        if all(end <= ks or start >= ke for ks, ke, _ in kept):
            kept.append((start, end, form_type))
    # "Record of Account Transcript" contains "Account Transcript": the
    # Record-of-Account anchor wins; drop the shadowed Account anchor.
    if any(c[2] == "RECORD_OF_ACCOUNT" for c in kept):
        kept = [
            c for c in kept
            if c[2] != "ACCOUNT_TRANSCRIPT"
            or not any(
                rs <= c[0] < re_ + 24
                for rs, re_, rt in kept
                if rt == "RECORD_OF_ACCOUNT"
            )
        ]
    # A transcript title dominates its page: inner form mentions ("Form
    # W-2", "Form 1099-INT" inside a Wage & Income transcript) are content,
    # not titles.
    if any(c[2] in _TRANSCRIPT_TYPES for c in kept):
        kept = [c for c in kept if c[2] in _TRANSCRIPT_TYPES]
    return kept


@dataclass
class FormSection:
    """One anchor-delimited span of a document's text.

    ``form_type`` is None for untyped spans (no title anchor) and for
    excluded instruction/notice sections. ``page_start``/``page_end`` are
    1-based, inclusive.
    """

    form_type: str | None
    text: str
    page_start: int
    page_end: int
    excluded: bool = False


def split_form_sections(pages: list[str]) -> list[FormSection]:
    """Split per-page texts into form sections at title anchors.

    - A section starts at each title anchor; consecutive anchors of the same
      form_type are one section (title + subtitle of a single form).
    - Text from an instruction/notice heading to the end of its page is an
      excluded section: never scored, never classified as a form.
    - A page (or leading span) with no anchor is an untyped section; it is
      attached to the preceding section as a continuation (e.g. page 2 of a
      form whose title is on page 1).
    """
    sections: list[FormSection] = []
    for pageno, page in enumerate(pages, start=1):
        text = _strip_form_references(page)
        head, tail = text, ""
        m = _EXCLUDED_HEADING_RE.search(text)
        if m:
            head, tail = text[: m.start()], text[m.start():]
        anchors = _find_title_anchors(head)
        cur_type: str | None = None
        cur_start = 0
        for start, _end, form_type in anchors:
            if form_type != cur_type:
                chunk = head[cur_start:start]
                if cur_type is not None or chunk.strip():
                    sections.append(
                        FormSection(cur_type, chunk, pageno, pageno)
                    )
                cur_type, cur_start = form_type, start
        rest = head[cur_start:]
        if cur_type is not None or rest.strip():
            sections.append(FormSection(cur_type, rest, pageno, pageno))
        if tail.strip():
            sections.append(
                FormSection(None, tail, pageno, pageno, excluded=True)
            )
    merged: list[FormSection] = []
    for sec in sections:
        if (
            not sec.excluded
            and sec.form_type is None
            and merged
            and not merged[-1].excluded
        ):
            prev = merged[-1]
            prev.text += sec.text
            prev.page_end = sec.page_end
        else:
            merged.append(sec)
    return merged


# Legacy keyword catalog: fallback only, for anchor-less text. Instruction
# and notice sections are never scored.
FORM_KEYWORDS: dict[str, list[str]] = {
    "W-2": ["W-2", "WAGE AND TAX STATEMENT", "WAGES, TIPS, OTHER COMPENSATION"],
    "1099-B": ["1099-B", "PROCEEDS FROM BROKER", "BARTER EXCHANGE"],
    "1099-INT": ["1099-INT", "INTEREST INCOME", "INTEREST"],
    "1099-DIV": ["1099-DIV", "DIVIDENDS AND DISTRIBUTIONS", "DIVIDENDS"],
    "1099-NEC": ["1099-NEC", "NONEMPLOYEE COMPENSATION"],
    "1099-R": ["1099-R", "DISTRIBUTIONS FROM PENSIONS", "RETIREMENT",
               "DISTRIBUTIONS"],
    "1098": ["1098", "MORTGAGE INTEREST STATEMENT", "MORTGAGE INTEREST"],
    "1099-MISC": ["1099-MISC", "MISCELLANEOUS INFORMATION", "MISCELLANEOUS"],
}


def _keyword_fallback(text: str) -> str:
    """Old substring scoring, kept as a fallback for anchor-less text."""
    upper = text.upper()
    best, best_score = "UNKNOWN", 0
    for form_type, keywords in FORM_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in upper)
        if score > best_score:
            best, best_score = form_type, score
    return best


def classify_form(text: str) -> str:
    """Classify text into a form_type using per-section title anchors.

    Instruction/notice sections are excluded from scoring (never classified
    as forms) and parenthesized "(Form 1040)" mentions are references, not
    titles. Returns "UNKNOWN" when no section carries a title anchor, and
    also when sections carry two or more distinct form types: a multi-form
    input is never collapsed to a single form_type (use
    split_form_sections for the per-section detail).
    """
    sections = split_form_sections([text])
    ordered: list[str] = []
    for sec in sections:
        if not sec.excluded and sec.form_type and sec.form_type not in ordered:
            ordered.append(sec.form_type)
    if len(ordered) == 1:
        return ordered[0]
    if not ordered:
        joined = " ".join(s.text for s in sections if not s.excluded)
        return _keyword_fallback(joined)
    return "UNKNOWN"


_LEADING_ANCHOR_RES: dict[str, re.Pattern] = {}


def _leading_anchor_re(form_type: str) -> re.Pattern:
    rx = _LEADING_ANCHOR_RES.get(form_type)
    if rx is None:
        pats = [pat for ft, pat, _line in _FORM_TITLE_ANCHORS if ft == form_type]
        rx = re.compile(r"\s*(?:" + "|".join(pats) + ")", re.IGNORECASE)
        _LEADING_ANCHOR_RES[form_type] = rx
    return rx


def section_has_content(text: str, form_type: str) -> bool:
    """True if a form section holds text beyond its leading title anchor.

    Decides split-vs-block for multi-form files: bare title mentions with
    no content are blocked as MULTI_FORM rather than fanned out into empty
    child documents.
    """
    m = _leading_anchor_re(form_type).match(text)
    rest = text[m.end():] if m else text
    return bool(rest.strip())


def detect_tax_year(text: str) -> int | None:
    """Find a 4-digit tax year (2000-2030) near tax-year phrases or in a form
    header line. Returns the int or None."""
    year_re = r"\b(20[0-2]\d)\b"

    # 1. Near explicit tax-year phrases.
    for phrase in ("TAX YEAR", "FOR CALENDAR YEAR", "CALENDAR YEAR"):
        m = re.search(
            phrase + r"[^\n]{0,40}" + year_re, text, re.IGNORECASE
        )
        if m:
            year = int(m.group(1))
            if 2000 <= year <= 2030:
                return year

    # 2. In a form header line, e.g. "Form W-2 2025" or "2025 Form 1099-NEC".
    for m in re.finditer(year_re, text):
        year = int(m.group(1))
        if not (2000 <= year <= 2030):
            continue
        line_start = text.rfind("\n", 0, m.start()) + 1
        line_end = text.find("\n", m.end())
        line = text[line_start:] if line_end == -1 else text[line_start:line_end]
        if re.search(r"\bFORM\b", line, re.IGNORECASE):
            return year

    # 3. Fallback: any year adjacent to "TAX" within the same line.
    for m in re.finditer(year_re, text):
        year = int(m.group(1))
        if not (2000 <= year <= 2030):
            continue
        line_start = text.rfind("\n", 0, m.start()) + 1
        line_end = text.find("\n", m.end())
        line = text[line_start:] if line_end == -1 else text[line_start:line_end]
        if re.search(r"\bTAX\b", line, re.IGNORECASE):
            return year
    return None


# ---------------------------------------------------------------------------
# Per-form extractors
# ---------------------------------------------------------------------------

def _extract_w2(text: str) -> dict:
    money_boxes = [
        # (box_code, [labeled regexes with money as group 1])
        ("1", [
            r"Wages,?\s+tips,?\s+other\s+compensation[^\n$]*" + _MONEY_RE,
            r"\bWages\b[^\n$]*" + _MONEY_RE,
        ]),
        ("2", [
            r"Federal\s+income\s+tax\s+withheld[^\n$]*" + _MONEY_RE,
            r"\bFederal\s+withheld\b[^\n$]*" + _MONEY_RE,
        ]),
        ("3", [
            r"Social\s+security\s+wages[^\n$]*" + _MONEY_RE,
        ]),
        ("4", [
            r"Social\s+security\s+tax\s+withheld[^\n$]*" + _MONEY_RE,
        ]),
        ("5", [
            r"Medicare\s+wages\s+(?:and\s+tips)?[^\n$]*" + _MONEY_RE,
        ]),
        ("6", [
            r"Medicare\s+tax\s+withheld[^\n$]*" + _MONEY_RE,
        ]),
    ]
    fields = {}
    for box, pats in money_boxes:
        fields[box] = _box_field(text, [(p, 1) for p in pats], box)

    # Box 12: code + amount, value as string like "D 9500.00".
    v, raw, labeled = _str_search(
        [
            (
                r"Box\s*12[^\nA-Z]*?\b([A-Z]{1,2})\s+" + _MONEY_RE_NODOLLAR,
                True,
                lambda m: f"{m.group(1)} {float(m.group(2).replace(',', '')):.2f}",
            ),
            (
                r"\b12\b[^\nA-Z]*?\b([A-Z]{1,2})\s+" + _MONEY_RE_NODOLLAR,
                False,
                lambda m: f"{m.group(1)} {float(m.group(2).replace(',', '')):.2f}",
            ),
        ],
        text,
    )
    fields["12"] = (
        _field(v, "high" if labeled else "medium", raw)
        if v is not None
        else _missing_field()
    )

    # Box 14: other, free-form string.
    v, raw, labeled = _str_search(
        [
            (r"Other\s+14\s*[:\-]?\s*([^\n]{1,60})", True, 1),
            (r"\b14\b\s*[:\-]?\s*([^\n]{1,60})", False, 1),
        ],
        text,
    )
    fields["14"] = (
        _field(v, "high" if labeled else "medium", raw)
        if v is not None
        else _missing_field()
    )

    # Employer EIN.
    v, raw, labeled = _str_search(
        [
            (r"EIN\b[^\d]*(\d{2}-\d{7})", True, 1),
            (r"Employer'?s?\s+(?:federal\s+)?identification\s+number[^\d]*(\d{2}-\d{7})", True, 1),
            (r"\b(\d{2}-\d{7})\b", False, 1),
        ],
        text,
    )
    fields["employer_ein"] = (
        _field(v, "high" if labeled else "medium", raw)
        if v is not None
        else _missing_field()
    )

    # Employer name.
    v, raw, labeled = _str_search(
        [
            (r"Employer'?s?\s+name[^\n:]*[:\-]?\s*([^\n]{1,60})", True, 1),
            (r"Box\s*[bc]\s*[:\-]?\s*([^\n]{1,60})", False, 1),
        ],
        text,
    )
    fields["employer_name"] = (
        _field(v, "high" if labeled else "medium", raw)
        if v is not None
        else _missing_field()
    )
    return fields


def _extract_1099_b(text: str) -> dict:
    fields = {}

    v, raw, labeled = _money_search(
        [
            (r"Proceeds[^\n$]*" + _MONEY_RE, True),
            (r"\b1d\b[^\d\n$]*" + _MONEY_RE, False),
        ],
        text,
    )
    fields["1d_proceeds"] = (
        _field(v, "high" if labeled else "medium", raw)
        if v is not None
        else _missing_field()
    )

    v, raw, labeled = _money_search(
        [
            (r"Cost\s*(?:or\s+other)?\s*basis[^\n$]*" + _MONEY_RE, True),
            (r"\b1e\b[^\d\n$]*" + _MONEY_RE, False),
        ],
        text,
    )
    fields["1e_basis"] = (
        _field(v, "high" if labeled else "medium", raw)
        if v is not None
        else _missing_field()
    )

    v, raw, labeled = _str_search(
        [
            (r"Date\s+acquired\s*[:\-]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})", True, 1),
            (r"\bacquired\b[^\d]*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})", False, 1),
        ],
        text,
    )
    fields["date_acquired"] = (
        _field(v, "high" if labeled else "medium", raw)
        if v is not None
        else _missing_field()
    )

    v, raw, labeled = _str_search(
        [
            (r"Date\s+sold\s*(?:or\s+disposed)?\s*[:\-]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})", True, 1),
            (r"\bsold\b[^\d]*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})", False, 1),
        ],
        text,
    )
    fields["date_sold"] = (
        _field(v, "high" if labeled else "medium", raw)
        if v is not None
        else _missing_field()
    )

    term = None
    term_raw = ""
    term_conf = "low"
    m = re.search(r"\b(short|long)\s*-?\s*term\b", text, re.IGNORECASE)
    if m:
        term = m.group(1).lower()
        term_raw = m.group(0)
        term_conf = "high"
    elif re.search(r"\bshort\b", text, re.IGNORECASE) and not re.search(
        r"\blong\b", text, re.IGNORECASE
    ):
        term, term_raw, term_conf = "short", "short", "medium"
    elif re.search(r"\blong\b", text, re.IGNORECASE):
        term, term_raw, term_conf = "long", "long", "medium"
    fields["term"] = _field(term, term_conf, term_raw)

    v, raw, labeled = _str_search(
        [
            (r"Payer'?s?\s+name[^\n:]*[:\-]?\s*([^\n]{1,60})", True, 1),
            (r"Broker[^\n:]*[:\-]?\s*([^\n]{1,60})", True, 1),
        ],
        text,
    )
    fields["broker"] = (
        _field(v, "high" if labeled else "medium", raw)
        if v is not None
        else _missing_field()
    )
    return fields


def _generic_money_extractor(defs):
    """Build an extractor for simple numbered money boxes.

    ``defs``: list of (box_code, label_regexes_list, is_key). Label regexes
    must capture the amount as group 1.
    """
    def extractor(text):
        fields = {}
        for box, pats, _key in defs:
            fields[box] = _box_field(text, [(p, 1) for p in pats], box)
        return fields
    return extractor


_extract_1099_int = _generic_money_extractor([
    ("1", [r"Interest\s+income[^\n$]*" + _MONEY_RE,
           r"\bInterest\b[^\n$]*" + _MONEY_RE], True),
    ("3", [r"Interest\s+on\s+U\.?S\.?\s+Savings\s+Bonds[^\n$]*" + _MONEY_RE,
           r"\bBonds?[^\n$]*" + _MONEY_RE], False),
])

_extract_1099_div = _generic_money_extractor([
    ("1a", [r"Total\s+ordinary\s+dividends[^\n$]*" + _MONEY_RE,
            r"Ordinary\s+dividends[^\n$]*" + _MONEY_RE], True),
    ("1b", [r"Qualified\s+dividends[^\n$]*" + _MONEY_RE], False),
    ("2a", [r"Total\s+capital\s+gain\s+distr[^\n$]*" + _MONEY_RE,
            r"Capital\s+gain[^\n$]*" + _MONEY_RE], False),
])

_extract_1099_nec = _generic_money_extractor([
    ("1", [r"Nonemployee\s+compensation[^\n$]*" + _MONEY_RE,
           r"\bCompensation\b[^\n$]*" + _MONEY_RE], True),
])

_extract_1098 = _generic_money_extractor([
    ("1", [r"Mortgage\s+interest\s+received[^\n$]*" + _MONEY_RE,
           r"Mortgage\s+interest[^\n$]*" + _MONEY_RE], True),
])

_extract_1099_misc = _generic_money_extractor([
    ("1", [r"\bRents\b[^\n$]*" + _MONEY_RE], True),
    ("3", [r"Other\s+income[^\n$]*" + _MONEY_RE], False),
])


def _extract_1099_r(text: str) -> dict:
    fields = {}
    fields["1"] = _box_field(
        text, [(r"Gross\s+distribution[^\n$]*" + _MONEY_RE, 1)], "1"
    )
    fields["2a"] = _box_field(
        text, [(r"Taxable\s+amount[^\n$]*" + _MONEY_RE, 1)], "2a"
    )
    v, raw, labeled = _str_search(
        [
            (r"Distribution\s+code\s*(?:\(s\))?\s*[:\-]?\s*([A-Z0-9]{1,3})", True, 1),
            (r"\bcode\s*7\b\s*[:\-]?\s*([A-Z0-9]{1,3})", False, 1),
            (r"\bBox\s*7\b\s*[:\-]?\s*([A-Z0-9]{1,3})", False, 1),
        ],
        text,
    )
    fields["7"] = (
        _field(v, "high" if labeled else "medium", raw)
        if v is not None
        else _missing_field()
    )
    return fields


# ---------------------------------------------------------------------------
# Registry: form_type -> (extractor_fn, key_boxes)
# ---------------------------------------------------------------------------

_FORM_REGISTRY = {
    "W-2": (_extract_w2, ["1", "2", "employer_ein"]),
    "1099-B": (_extract_1099_b, ["1d_proceeds", "broker"]),
    "1099-INT": (_extract_1099_int, ["1"]),
    "1099-DIV": (_extract_1099_div, ["1a"]),
    "1099-NEC": (_extract_1099_nec, ["1"]),
    "1099-R": (_extract_1099_r, ["1"]),
    "1098": (_extract_1098, ["1"]),
    "1099-MISC": (_extract_1099_misc, ["1"]),
}


def extract_fields(form_type: str, text: str) -> tuple[dict, str]:
    """Extract box-level fields from OCR text of a tax form.

    Returns (fields, status). ``status`` is "transcribed" when every KEY box
    of the form was found with high/medium confidence, otherwise
    "needs_review". Unknown ``form_type`` -> ({}, "needs_review").
    """
    entry = _FORM_REGISTRY.get(form_type)
    if entry is None:
        return {}, "needs_review"
    extractor, key_boxes = entry
    fields = extractor(text)
    ok = all(
        fields.get(box, {}).get("confidence") in ("high", "medium")
        for box in key_boxes
    )
    return fields, "transcribed" if ok else "needs_review"
