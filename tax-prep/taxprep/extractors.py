"""Field extraction from OCR text of US tax forms.

Local-only, dependency-free (stdlib ``re`` only). Synthetic-fixture friendly:
no names, EINs, or amounts in this module are real.

Main entry point
----------------
``extract_fields(form_type, text)`` returns ``(fields, status)`` where
``fields`` maps each box code of the form to
``{"value": str | None, "confidence": "high"|"medium"|"low",
"raw_text": str}`` and ``status`` is ``"transcribed"`` when every KEY box of
the form was found with high/medium confidence, else ``"needs_review"``.

Money values are canonical Decimal-safe STRINGS (e.g. ``"52345.67"``) --
never float, never Decimal (DocumentStore is JSONL; carryforward coerces
via Decimal and loudly rejects floats). The 1099-B extractor returns a
lot table: ``fields["lots"]["value"]`` is a list of per-lot dicts with
keys ``description``, ``date_acquired``, ``date_sold``, ``proceeds_1d``,
``basis_1e``, ``wash_1g``, ``accrued_market_discount_1f``,
``fed_withheld_4``, ``term``, ``covered``
(money as Decimal-safe strings, the rest strings or None).

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
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

# Derivation version for the Arc B medallion (contract section 7, W2 owns).
# "1" is the pre-medallion era (JSONL store, no artifact derivation).
# "2" added medallion derivation. "3" adds R15 field provenance
# (extraction-time char spans, verbatim transcript evidence, derived
# transcript confidences). Bump on ANY extraction-logic change: a bump
# rebuilds silver (I6) while preserving Operator decisions.
# taxprep.silver.derivation_config() carries this into the config hash.
EXTRACTOR_VERSION = "3"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Money token. The (?<![\d,.]) anchor plus the digit-free label gaps used
# below (``[^\n\d$]*``) are the D3 truncation fix: the gap between a label
# and its amount can never swallow leading digits, so "52,345.67" can
# never truncate to "5.67" and "100.00" can never become "0.00". The
# captured group is the bare amount; "$ " spacing ("$ 1,234.00") and
# parenthesized negatives ("($1,234.56)") are accepted -- negation is
# detected from the match prefix by _paren_negated, not from the group.
_MONEY_RE = r"(?<![\d,.])\(?\$?[ \t]*([\d,]+\.\d{2})\)?"
_MONEY_RE_NODOLLAR = r"(?<![\d,.])\(?([\d,]+\.\d{2})\)?"


def _parse_money(s: str) -> str | None:
    """Canonical Decimal-safe money string, e.g. "52345.67".

    Strips '$', commas and whitespace. Never returns float or Decimal --
    DocumentStore is JSONL and carryforward coerces strings via Decimal
    (loudly rejecting floats). Returns None on failure.
    """
    if not isinstance(s, str):
        return None
    t = s.replace("$", "").replace(",", "").strip()
    if not t:
        return None
    try:
        return format(Decimal(t), "f")
    except InvalidOperation:
        return None


def _paren_negated(m: "re.Match") -> bool:
    """True when the captured amount is wrapped in parentheses.

    Inspects the text between the match start and the amount capture:
    after stripping a trailing "$"/spaces (the "($1,234.56)" shape), a
    "(" means the amount is a parenthesized negative.
    """
    pre = m.string[m.start():m.start(1)]
    return pre.rstrip("$ \t").endswith("(")


def _field(value, confidence, raw_text, span=None):
    """One field entry.

    ``span`` is the transient ``(start, end)`` match offset in the
    extraction text (R15): ingest's provenance attachment converts it to
    the ``provenance`` dict and removes it, so it never persists.
    """
    entry = {"value": value, "confidence": confidence,
             "raw_text": raw_text}
    if span is not None:
        entry["_extract_span"] = span
    return entry


def _missing_field():
    """Standard low-confidence field for a box that was not found."""
    return _field(None, "low", "")


def _money_search(patterns, text):
    """Return (value, raw_text, is_labeled, span) for the first money pattern
    that matches. ``patterns`` is a list of (regex, labeled_bool). ``labeled``
    patterns drive "high" confidence; unlabeled ones drive "medium".
    Values are canonical Decimal-safe strings (see _parse_money);
    parenthesized negatives ("($1,234.56)") come back with a "-" prefix.
    ``span`` is the (start, end) match offset in ``text`` (R15), or None.
    """
    for pattern, labeled in patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            value = _parse_money(m.group(1))
            if value is None:
                continue
            if _paren_negated(m) and not value.startswith("-"):
                value = "-" + value
            return value, m.group(0), labeled, (m.start(), m.end())
    return None, "", False, None


def _str_search(patterns, text):
    """Return (value, raw_text, is_labeled, span) for the first string pattern
    that matches. ``patterns`` is a list of (regex, labeled_bool, group_index
    or callable transforming the match into the value). ``span`` is the
    (start, end) match offset in ``text`` (R15), or None.
    """
    for pattern, labeled, transform in patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            if callable(transform):
                value = transform(m)
            else:
                value = m.group(transform).strip()
            if value:
                return value, m.group(0), labeled, (m.start(), m.end())
    return None, "", False, None


def _box_field(text, label_patterns, box_num, value_transform=None):
    """Extract a money box field.

    ``label_patterns``: list of (regex, group_index) tried first -> "high".
    Fallback: generic ``Box <num>`` pattern -> "medium".
    """
    high_pats = [(p, True) for p, _ in label_patterns]
    # Normalize: wrap each high pattern so group(1) is the amount. label
    # patterns are written with the money group as group(1).
    value, raw, labeled, span = _money_search(high_pats, text)
    if value is not None:
        return _field(value, "high", raw, span)
    fallback = re.compile(
        r"Box\s*" + re.escape(str(box_num)) + r"[^\d\n]*?\$?" + _MONEY_RE_NODOLLAR,
        re.IGNORECASE,
    )
    m = fallback.search(text)
    if m:
        value = _parse_money(m.group(1))
        if value is not None:
            if _paren_negated(m) and not value.startswith("-"):
                value = "-" + value
            return _field(value, "medium", m.group(0), (m.start(), m.end()))
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
    # R17: the IRS header is "TAX ACCOUNT TRANSCRIPT" — accept the optional
    # TAX prefix (mirrors the RETURN_TRANSCRIPT anchor).
    ("ACCOUNT_TRANSCRIPT", r"(?:TAX\s+)?ACCOUNT\s+TRANSCRIPT\b", True),
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


def _find_title_anchors(text: str) -> list[tuple[int, int, str]]:
    """All (start, end, form_type) title-anchor matches, in position order.

    Overlaps resolve to the earliest start, then the longest match, then
    table order (so "Form 1040-X" beats "Form 1040" at the same start).

    Parenthesized "(Form 1040)"-style mentions are references, not
    titles: anchors overlapping a reference region are dropped. (The
    section text itself is NOT stripped -- R15 needs it verbatim so
    character offsets translate exactly into stored per-page text.)
    """
    ref_spans = [m.span() for m in _FORM_REFERENCE_RE.finditer(text)]

    def _in_reference(start: int, end: int) -> bool:
        return any(rs < end and start < re_ for rs, re_ in ref_spans)

    cands: list[tuple[int, int, str]] = []
    order = {ft: i for i, (ft, _p, _l) in enumerate(_FORM_TITLE_ANCHORS)}
    for form_type, rx in _ANCHOR_RES:
        for m in rx.finditer(text):
            if not _in_reference(m.start(), m.end()):
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

    ``page_spans`` (R15) maps ``text`` offsets back to source pages:
    ``[(page_1based, start, end), ...]`` with
    ``text[start:end]`` verbatim from that page's stored text. The
    section text is built from verbatim page substrings (form
    references are filtered at anchor-detection time, never stripped
    from the text), so character offsets translate exactly.
    """

    form_type: str | None
    text: str
    page_start: int
    page_end: int
    excluded: bool = False
    page_spans: list = field(default_factory=list)


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
        # NOTE (R15): the section text keeps the page VERBATIM -- form
        # references are filtered inside _find_title_anchors, never
        # stripped from the text, so page_spans offsets translate
        # exactly into stored per-page text.
        head, tail = page, ""
        m = _EXCLUDED_HEADING_RE.search(page)
        if m:
            head, tail = page[: m.start()], page[m.start():]
        anchors = _find_title_anchors(head)
        cur_type: str | None = None
        cur_start = 0
        for start, _end, form_type in anchors:
            if form_type != cur_type:
                chunk = head[cur_start:start]
                if cur_type is not None or chunk.strip():
                    sections.append(
                        FormSection(cur_type, chunk, pageno, pageno,
                                    page_spans=[(pageno, 0, len(chunk))])
                    )
                cur_type, cur_start = form_type, start
        rest = head[cur_start:]
        if cur_type is not None or rest.strip():
            sections.append(FormSection(cur_type, rest, pageno, pageno,
                                        page_spans=[(pageno, 0, len(rest))]))
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
            base = len(prev.text)
            prev.text += sec.text
            prev.page_spans.extend(
                (p, base + s, base + e) for p, s, e in sec.page_spans
            )
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
        # NOTE (D3): every label gap is [^\n\d$]* -- digits are excluded so
        # a bare "52,345.67" can never truncate to "5.67".
        ("1", [
            r"Wages,?\s+tips,?\s+other\s+compensation[^\n\d$]*" + _MONEY_RE,
            r"\bWages\b[^\n\d$]*" + _MONEY_RE,
        ]),
        ("2", [
            r"Federal\s+income\s+tax\s+withheld[^\n\d$]*" + _MONEY_RE,
            r"\bFederal\s+withheld\b[^\n\d$]*" + _MONEY_RE,
        ]),
        ("3", [
            r"Social\s+security\s+wages[^\n\d$]*" + _MONEY_RE,
        ]),
        ("4", [
            r"Social\s+security\s+tax\s+withheld[^\n\d$]*" + _MONEY_RE,
        ]),
        ("5", [
            r"Medicare\s+wages\s+(?:and\s+tips)?[^\n\d$]*" + _MONEY_RE,
        ]),
        ("6", [
            r"Medicare\s+tax\s+withheld[^\n\d$]*" + _MONEY_RE,
        ]),
    ]
    fields = {}
    for box, pats in money_boxes:
        fields[box] = _box_field(text, [(p, 1) for p in pats], box)

    # Box 12: code + amount, value as string like "D 9500.00".
    # Decimal-exact (never float): the string is the contract.
    v, raw, labeled, span = _str_search(
        [
            (
                r"Box\s*12[^\nA-Z]*?\b([A-Z]{1,2})\s+" + _MONEY_RE_NODOLLAR,
                True,
                lambda m: f"{m.group(1)} {format(Decimal(m.group(2).replace(',', '')), '.2f')}",
            ),
            (
                r"\b12\b[^\nA-Z]*?\b([A-Z]{1,2})\s+" + _MONEY_RE_NODOLLAR,
                False,
                lambda m: f"{m.group(1)} {format(Decimal(m.group(2).replace(',', '')), '.2f')}",
            ),
        ],
        text,
    )
    fields["12"] = (
        _field(v, "high" if labeled else "medium", raw, span)
        if v is not None
        else _missing_field()
    )

    # Box 14: other, free-form string.
    v, raw, labeled, span = _str_search(
        [
            (r"Other\s+14\s*[:\-]?\s*([^\n]{1,60})", True, 1),
            (r"\b14\b\s*[:\-]?\s*([^\n]{1,60})", False, 1),
        ],
        text,
    )
    fields["14"] = (
        _field(v, "high" if labeled else "medium", raw, span)
        if v is not None
        else _missing_field()
    )

    # Employer EIN.
    v, raw, labeled, span = _str_search(
        [
            (r"EIN\b[^\d]*(\d{2}-\d{7})", True, 1),
            (r"Employer'?s?\s+(?:federal\s+)?identification\s+number[^\d]*(\d{2}-\d{7})", True, 1),
            (r"\b(\d{2}-\d{7})\b", False, 1),
        ],
        text,
    )
    fields["employer_ein"] = (
        _field(v, "high" if labeled else "medium", raw, span)
        if v is not None
        else _missing_field()
    )

    # Employer name.
    v, raw, labeled, span = _str_search(
        [
            (r"Employer'?s?\s+name[^\n:]*[:\-]?\s*([^\n]{1,60})", True, 1),
            (r"Box\s*[bc]\s*[:\-]?\s*([^\n]{1,60})", False, 1),
        ],
        text,
    )
    fields["employer_name"] = (
        _field(v, "high" if labeled else "medium", raw, span)
        if v is not None
        else _missing_field()
    )
    return fields


# ---------------------------------------------------------------------------
# 1099-B lots (F1): every lot on the statement is extracted, never just the
# first. A statement is split into lot segments -- first at explicit
# "Lot n" markers, otherwise at repeated proceeds labels (total/subtotal
# lines are excluded from segmentation; they feed the summary-totals
# extractor instead). Each segment yields one lot dict; a segment with no
# lot-like content at all yields no lot.
# ---------------------------------------------------------------------------

# Per-lot money patterns: (lot key, [(regex, labeled_bool)]). Money is
# group 1 everywhere; gaps are digit-free (D3).
_LOT_MONEY_PATTERNS: dict[str, list[tuple[str, bool]]] = {
    "proceeds_1d": [
        (r"Proceeds[^\n\d$]*" + _MONEY_RE, True),
        (r"\b1d\b[^\d\n$]*" + _MONEY_RE, False),
    ],
    "basis_1e": [
        (r"Cost\s*(?:or\s+other)?\s*basis[^\n\d$]*" + _MONEY_RE, True),
        (r"\b1e\b[^\d\n$]*" + _MONEY_RE, False),
    ],
    # F3: box 1g, wash sale loss disallowed -- added BACK to the lot's
    # gain/loss by carryforward (gain/loss = 1d - 1e + 1g).
    "wash_1g": [
        (r"Wash\s+sale\s+loss\s+disallowed[^\n\d$]*" + _MONEY_RE, True),
        (r"\b1g\b[^\d\n$]*" + _MONEY_RE, False),
    ],
    # Box 1f: ACCRUED MARKET DISCOUNT -- Schedule B interest income
    # (Phase 4). Never part of gain/loss and never a withholding
    # credit. (B1F: on Form 1099-B, box 1f is NOT federal income tax
    # withheld -- that is box 4.)
    "accrued_market_discount_1f": [
        (r"Accrued\s+market\s+discount[^\n\d$]*" + _MONEY_RE, True),
        (r"\b1f\b[^\d\n$]*" + _MONEY_RE, False),
    ],
    # Box 4: federal income tax withheld -- a withholding credit,
    # never part of gain/loss. No bare \b4\b: it would match any
    # standalone 4 on the statement.
    "fed_withheld_4": [
        (r"Federal\s+income\s+tax\s+withheld[^\n\d$]*" + _MONEY_RE, True),
        (r"Backup\s+withholding[^\n\d$]*" + _MONEY_RE, True),
        (r"\bBox\s*4\b[^\d\n$]*" + _MONEY_RE, True),
    ],
}

_LOT_KEYS = ("description", "date_acquired", "date_sold", "proceeds_1d",
             "basis_1e", "wash_1g", "accrued_market_discount_1f",
             "fed_withheld_4", "term", "covered")


def _clean_description(m: "re.Match") -> str | None:
    """Trim a captured description at box-label bleed on the same line."""
    v = m.group(1).strip()
    v = re.split(r"\s{2,}|\s+\b1[abcdefg]\b", v, maxsplit=1)[0].strip()
    return v or None


_LOT_STR_PATTERNS: dict[str, list[tuple]] = {
    "description": [
        (r"Description\s*(?:of\s+(?:property|security))?\s*[:\-]?\s*([^\n]{1,80})",
         True, _clean_description),
        (r"\b1a\b\s*[:\-]?\s*([^\n]{1,80})", False, _clean_description),
    ],
    "date_acquired": [
        (r"Date\s+acquired\s*[:\-]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})", True, 1),
        (r"\bacquired\b[^\d]*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})", False, 1),
        (r"\b1b\b[^\d]*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})", False, 1),
    ],
    "date_sold": [
        (r"Date\s+sold\s*(?:or\s+disposed)?\s*[:\-]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})", True, 1),
        (r"\bsold\b[^\d]*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})", False, 1),
        (r"\b1c\b[^\d]*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})", False, 1),
    ],
}


def _lot_term(segment: str) -> str | None:
    """Holding term for one lot segment: "short" | "long" | None."""
    m = re.search(r"\b(short|long)\s*-?\s*term\b", segment, re.IGNORECASE)
    if m:
        return m.group(1).lower()
    if re.search(r"\blong\b", segment, re.IGNORECASE):
        return "long"
    if re.search(r"\bshort\b", segment, re.IGNORECASE):
        return "short"
    return None


def _lot_covered(segment: str) -> str | None:
    """Basis-reporting flag for one lot segment, if stated."""
    if re.search(r"\bnoncovered\b", segment, re.IGNORECASE):
        return "noncovered"
    if re.search(r"\bcovered\b", segment, re.IGNORECASE):
        return "covered"
    if re.search(r"basis\s+reported\s+to\s+IRS", segment, re.IGNORECASE):
        return "covered"
    return None


# F1b: section headings ("Short-term covered", "Long-term noncovered",
# "Short-term transactions for which basis is reported to IRS", ...).
# A heading is a line naming the holding term WITH covered/noncovered
# (or basis-reported-to-IRS) context -- a bare "Holding period: long
# term" lot line is not a heading.
_SECTION_HEADING_RE = re.compile(
    r"^[^\n]*\b(short|long)\s*-?\s*term\b[^\n]*"
    r"\b(noncovered|covered|basis\s+reported\s+to\s+IRS)\b[^\n]*$",
    re.IGNORECASE | re.MULTILINE,
)

# Lines that look like lot content are never headings, even when they
# name a term: a heading is a section label, not a lot row.
_HEADING_EXCLUSIONS_RE = re.compile(
    r"proceeds|\bBox\s*1[defg]?\b|\bLots?\s*#?\s*\d+\b", re.IGNORECASE)


def _find_section_headings(text: str) -> list[tuple[int, str, str]]:
    """[(offset, term, covered)] of 1099-B section headings, in order.

    Delegates to _is_section_heading_line so the finder and the
    segment stripper agree on what a heading is.
    """
    headings = []
    for m in re.finditer(r"(?m)^[^\n]*$", text):
        line = m.group(0)
        if not _is_section_heading_line(line):
            continue
        term = _SECTION_HEADING_RE.search(line).group(1).lower()
        if re.search(r"\bnoncovered\b", line, re.IGNORECASE):
            covered = "noncovered"
        else:
            covered = "covered"  # "covered" or "basis reported to IRS"
        headings.append((m.start(), term, covered))
    return headings


def _strip_heading_lines(segment: str) -> str:
    """Remove section-heading lines from a lot segment.

    A heading that lands inside a segment's span (e.g. between two
    "Lot n" markers) belongs to the section, not to the lot: leaving
    it in would let one section's heading set the previous lot's term.
    """
    kept = [line for line in segment.splitlines(keepends=True)
            if not _is_section_heading_line(line)]
    return "".join(kept)


def _is_section_heading_line(line: str) -> bool:
    """True when a single line is a 1099-B section heading."""
    # The MULTILINE regex is anchored per line, so a search over the
    # single line is exact.
    m = _SECTION_HEADING_RE.search(line)
    if not m:
        return False
    if _HEADING_EXCLUSIONS_RE.search(line):
        return False
    return not re.search(_MONEY_RE, line)


# Form box 2 ("Short-term/Long-term gain or loss"): fallback term
# source when the statement carries no section headings at all.
_BOX2_TERM_RE = re.compile(
    r"^[^\n]*\bbox\s*2\b[^\n]*\b(short|long)\s*-?\s*term\b",
    re.IGNORECASE | re.MULTILINE,
)


def _extract_one_lot(segment: str) -> tuple[dict, bool]:
    """Extract one lot dict from a segment.

    Returns (lot, proceeds_labeled): ``proceeds_labeled`` is True when
    the lot's proceeds came from a labeled pattern (drives the lots
    field's high/medium confidence).
    """
    lot: dict = {}
    proceeds_labeled = False
    for key, pats in _LOT_MONEY_PATTERNS.items():
        v, _raw, labeled, _span = _money_search(pats, segment)
        lot[key] = v
        if key == "proceeds_1d" and v is not None:
            proceeds_labeled = labeled
    for key, pats in _LOT_STR_PATTERNS.items():
        v, _raw, _labeled, _span = _str_search(pats, segment)
        lot[key] = v.strip() if isinstance(v, str) else None
        if not lot[key]:
            lot[key] = None
    lot["term"] = _lot_term(segment)
    lot["covered"] = _lot_covered(segment)
    return {k: lot.get(k) for k in _LOT_KEYS}, proceeds_labeled


_LOT_MARKER_RE = re.compile(r"\bLots?\s*#?\s*\d+\b", re.IGNORECASE)
_PROCEEDS_SPLIT_RE = re.compile(
    r"Proceeds[^\n\d$]*" + _MONEY_RE + r"|\b1d\b[^\d\n$]*" + _MONEY_RE,
    re.IGNORECASE,
)
_TOTAL_LINE_RE = re.compile(r"\btotals?\b|\bsubtotals?\b", re.IGNORECASE)


# A repeated lot block usually opens with its description or dates
# ("Description: ...", "Date acquired: ...") ahead of the proceeds line.
# When splitting at repeated proceeds labels, the block starts at the
# nearest such opener -- unless a basis amount intervenes between the
# opener and the proceeds (then the opener belongs to the previous
# block's tail, e.g. a description printed after its proceeds).
_BLOCK_OPENER_RE = re.compile(
    r"Description\s*(?:of\s+(?:property|security))?\s*[:\-]?"
    r"|Date\s+acquired"
    r"|Date\s+sold\s*(?:or\s+disposed)?"
    r"|\b1[abc]\b",
    re.IGNORECASE,
)
_BASIS_DISQUALIFIER_RE = re.compile(
    r"Cost\s*(?:or\s+other)?\s*basis[^\n\d$]*" + _MONEY_RE
    + r"|\b1e\b[^\d\n$]*" + _MONEY_RE,
    re.IGNORECASE,
)


def _total_line_spans(text: str) -> list[tuple[int, int]]:
    """Spans of lines mentioning totals/subtotals (statement-level, not lots)."""
    spans = []
    for m in re.finditer(r"(?m)^[^\n]*$", text):
        if _TOTAL_LINE_RE.search(m.group(0)):
            spans.append((m.start(), m.end()))
    return spans


def _split_lot_segments(text: str) -> list[tuple[str, int]]:
    """Split statement text into per-lot (segment, start_offset) pairs.

    1. Explicit "Lot n" markers win: each marker starts a segment (the
       preamble before the first marker holds statement-level info and
       is not a lot).
    2. Otherwise, repeated proceeds labels start new segments -- but
       never on total/subtotal lines (those feed the summary-totals
       extractor, not the lot table).
    3. Zero or one proceeds label: the whole text is one lot.

    The start offset lets _extract_1099_b inherit term/covered from
    the nearest preceding section heading (F1b).
    """
    markers = list(_LOT_MARKER_RE.finditer(text))
    if markers:
        segs = []
        for i, m in enumerate(markers):
            end = markers[i + 1].start() if i + 1 < len(markers) else len(text)
            seg = text[m.end():end]
            if seg.strip():
                segs.append((seg, m.end()))
        if segs:
            return segs
    total_spans = _total_line_spans(text)

    def _on_total_line(pos: int) -> bool:
        return any(s <= pos < e for s, e in total_spans)

    proc_matches = [m for m in _PROCEEDS_SPLIT_RE.finditer(text)
                    if not _on_total_line(m.start())]
    if len(proc_matches) <= 1:
        return [(text, 0)]
    # Repeated labeled blocks: each block starts at the nearest
    # description/date opener ahead of its proceeds label (see
    # _BLOCK_OPENER_RE); without an opener the block starts at the
    # proceeds label itself.
    openers = list(_BLOCK_OPENER_RE.finditer(text))
    bounds: list[int] = []
    prev_proc_end = 0
    for pm in proc_matches:
        cands = [om for om in openers if prev_proc_end < om.start() < pm.start()]
        block_start = pm.start()
        for om in cands:
            # An opener with a basis amount between it and this lot's
            # proceeds belongs to the previous block's tail, not to
            # this block: keep looking.
            if _BASIS_DISQUALIFIER_RE.search(text, om.end(), pm.start()):
                continue
            block_start = om.start()
            break
        bounds.append(block_start)
        prev_proc_end = pm.end()
    segs = []
    for i, b in enumerate(bounds):
        end = bounds[i + 1] if i + 1 < len(bounds) else len(text)
        segs.append((text[b:end], b))
    return segs


# Statement-level summary totals, e.g. "Short-term totals: Proceeds
# $3,000.00 Basis $4,100.00". Feeds verify_summary_reconciliation
# (metadata-only: lot sums vs these totals, 1-cent tolerance).
_SUMMARY_KINDS: dict[str, list[str]] = {
    "proceeds_1d": [r"Proceeds", r"Gross\s+proceeds"],
    "basis_1e": [r"(?:Cost\s+(?:or\s+other\s+)?)?[Bb]asis"],
}


def _extract_summary_totals(text: str) -> dict:
    """Per-category summary totals: {"short": {"proceeds_1d", "basis_1e"},
    "long": {...}} -- only categories/kinds actually shown. Missing when
    the statement shows no totals (the reconciliation check then skips
    the document, never fails it)."""
    totals: dict = {}
    raw_spans: list[str] = []
    match_spans: list[tuple[int, int]] = []
    for cat, cat_label in (("short", r"Short[\s-]*term"),
                           ("long", r"Long[\s-]*term")):
        cat_totals: dict = {}
        for key, labels in _SUMMARY_KINDS.items():
            label_alt = "(?:" + "|".join(labels) + ")"
            v, raw, _labeled, span = _money_search(
                [
                    (r"(?:Totals?|Subtotals?)\s+" + cat_label + r"\s+"
                     + label_alt + r"[^\n\d$]*" + _MONEY_RE, True),
                    (cat_label + r"\s+totals?\b[^\n]*?" + label_alt
                     + r"[^\n\d$]*" + _MONEY_RE, True),
                ],
                text,
            )
            if v is not None:
                cat_totals[key] = v
                raw_spans.append(raw)
                if span is not None:
                    match_spans.append(span)
        if cat_totals:
            totals[cat] = cat_totals
    if not totals:
        return _missing_field()
    span = ((min(s for s, _ in match_spans),
             max(e for _, e in match_spans)) if match_spans else None)
    return _field(totals, "high", "\n".join(raw_spans), span)


def _extract_1099_b(text: str) -> dict:
    fields = {}

    lots: list[dict] = []
    all_labeled = True
    any_proceeds = False
    lot_raw: list[str] = []
    lot_spans: list[tuple[int, int]] = []  # R15: per-lot evidence spans
    # F1b: section headings ("Short-term covered", ...) name the term
    # and covered flag for every lot in the section. A lot's own
    # segment wins when it names them; otherwise the nearest preceding
    # heading applies -- never a guess, and genuinely unknown stays
    # None (the carryforward guard raises it to the Operator). With no
    # headings at all, form box 2 ("Short-term/Long-term gain or
    # loss") is the fallback term source.
    headings = _find_section_headings(text)
    box2_term = None
    if not headings:
        m = _BOX2_TERM_RE.search(text)
        if m:
            box2_term = m.group(1).lower()
    for seg, start in _split_lot_segments(text):
        # A heading line inside a segment's span belongs to the
        # section, not to the lot: strip it before per-lot detection
        # so one section's heading cannot set the previous lot's term.
        # The R15 span covers the whole original segment (heading lines
        # included): it is the lot's evidence region, and the strip only
        # affects term/covered detection, never the stored offsets.
        seg_span = (start, start + len(seg))
        seg = _strip_heading_lines(seg)
        lot, proceeds_labeled = _extract_one_lot(seg)
        if lot["term"] is None or lot["covered"] is None:
            hterm = hcovered = None
            for hoff, ht, hc in headings:
                if hoff < start:
                    hterm, hcovered = ht, hc
                else:
                    break
            if lot["term"] is None:
                lot["term"] = hterm or box2_term
            if lot["covered"] is None:
                lot["covered"] = hcovered
        if not any(v is not None for v in lot.values()):
            continue  # no lot-like content in this segment
        lots.append(lot)
        lot_raw.append(seg.strip())
        lot_spans.append(seg_span)
        if lot["proceeds_1d"] is not None:
            any_proceeds = True
            all_labeled = all_labeled and proceeds_labeled
    if lots and any_proceeds:
        fields["lots"] = _field(
            lots, "high" if all_labeled else "medium", "\n".join(lot_raw),
            (lot_spans[0][0], lot_spans[-1][1]))
        fields["lots"]["_lot_spans"] = lot_spans
    elif lots:
        # Lots parsed but no proceeds anywhere: present but malformed.
        fields["lots"] = _field(lots, "low", "\n".join(lot_raw),
                                (lot_spans[0][0], lot_spans[-1][1]))
        fields["lots"]["_lot_spans"] = lot_spans
    else:
        fields["lots"] = _missing_field()

    fields["summary_totals"] = _extract_summary_totals(text)

    v, raw, labeled, span = _str_search(
        [
            (r"Payer'?s?\s+name[^\n:]*[:\-]?\s*([^\n]{1,60})", True, 1),
            (r"Broker[^\n:]*[:\-]?\s*([^\n]{1,60})", True, 1),
        ],
        text,
    )
    fields["broker"] = (
        _field(v, "high" if labeled else "medium", raw, span)
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
    ("1", [r"Interest\s+income[^\n\d$]*" + _MONEY_RE,
           r"\bInterest\b[^\n\d$]*" + _MONEY_RE], True),
    ("3", [r"Interest\s+on\s+U\.?S\.?\s+Savings\s+Bonds[^\n\d$]*" + _MONEY_RE,
           r"\bBonds?[^\n\d$]*" + _MONEY_RE], False),
])

_extract_1099_div = _generic_money_extractor([
    ("1a", [r"Total\s+ordinary\s+dividends[^\n\d$]*" + _MONEY_RE,
            r"Ordinary\s+dividends[^\n\d$]*" + _MONEY_RE], True),
    ("1b", [r"Qualified\s+dividends[^\n\d$]*" + _MONEY_RE], False),
    ("2a", [r"Total\s+capital\s+gain\s+distr[^\n\d$]*" + _MONEY_RE,
            r"Capital\s+gain[^\n\d$]*" + _MONEY_RE], False),
])

_extract_1099_nec = _generic_money_extractor([
    ("1", [r"Nonemployee\s+compensation[^\n\d$]*" + _MONEY_RE,
           r"\bCompensation\b[^\n\d$]*" + _MONEY_RE], True),
])

_extract_1098 = _generic_money_extractor([
    ("1", [r"Mortgage\s+interest\s+received[^\n\d$]*" + _MONEY_RE,
           r"Mortgage\s+interest[^\n\d$]*" + _MONEY_RE], True),
])

_extract_1099_misc = _generic_money_extractor([
    ("1", [r"\bRents\b[^\n\d$]*" + _MONEY_RE], True),
    ("3", [r"Other\s+income[^\n\d$]*" + _MONEY_RE], False),
])


def _extract_1099_r(text: str) -> dict:
    fields = {}
    fields["1"] = _box_field(
        text, [(r"Gross\s+distribution[^\n\d$]*" + _MONEY_RE, 1)], "1"
    )
    fields["2a"] = _box_field(
        text, [(r"Taxable\s+amount[^\n\d$]*" + _MONEY_RE, 1)], "2a"
    )
    v, raw, labeled, span = _str_search(
        [
            (r"Distribution\s+code\s*(?:\(s\))?\s*[:\-]?\s*([A-Z0-9]{1,3})", True, 1),
            (r"\bcode\s*7\b\s*[:\-]?\s*([A-Z0-9]{1,3})", False, 1),
            (r"\bBox\s*7\b\s*[:\-]?\s*([A-Z0-9]{1,3})", False, 1),
        ],
        text,
    )
    fields["7"] = (
        _field(v, "high" if labeled else "medium", raw, span)
        if v is not None
        else _missing_field()
    )
    return fields


# ---------------------------------------------------------------------------
# Registry: form_type -> (extractor_fn, key_boxes)
# ---------------------------------------------------------------------------

_FORM_REGISTRY = {
    "W-2": (_extract_w2, ["1", "2", "employer_ein"]),
    "1099-B": (_extract_1099_b, ["lots", "broker"]),
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
