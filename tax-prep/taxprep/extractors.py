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
``classify_form(text)`` — classify OCR text into a ``form_type`` using
``FORM_KEYWORDS`` plus transcript/schedule return-type detection.

``detect_tax_year(text)`` — find a 4-digit tax year (2000-2030) near tax-year
phrases or in a form header line.
"""

import re

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
# Form keyword catalog (uppercase phrases) for classification
# ---------------------------------------------------------------------------

FORM_KEYWORDS: dict[str, list[str]] = {
    "W-2": ["W-2", "WAGE AND TAX STATEMENT", "WAGES, TIPS, OTHER COMPENSATION"],
    "1099-B": ["1099-B", "PROCEEDS FROM BROKER", "BROKER TRANSACTIONS"],
    "1099-INT": ["1099-INT", "INTEREST INCOME", "INTEREST"],
    "1099-DIV": ["1099-DIV", "DIVIDENDS AND DISTRIBUTIONS", "DIVIDENDS"],
    "1099-NEC": ["1099-NEC", "NONEMPLOYEE COMPENSATION"],
    "1099-R": ["1099-R", "DISTRIBUTIONS FROM PENSIONS", "RETIREMENT",
               "DISTRIBUTIONS"],
    "1098": ["1098", "MORTGAGE INTEREST STATEMENT", "MORTGAGE INTEREST"],
    "1099-MISC": ["1099-MISC", "MISCELLANEOUS INFORMATION", "MISCELLANEOUS"],
}


def classify_form(text: str) -> str:
    """Classify OCR text into a form_type.

    Transcript / return types are checked first, then the 1040-X-before-1040
    order rule applies, then FORM_KEYWORDS matching.
    """
    upper = text.upper()
    if "WAGE AND INCOME TRANSCRIPT" in upper:
        return "WAGE_INCOME_TRANSCRIPT"
    if "TAX RETURN TRANSCRIPT" in upper or (
        "RETURN TRANSCRIPT" in upper and "1040" in upper
    ):
        return "RETURN_TRANSCRIPT"
    if "SCHEDULE D" in upper:
        return "SCHEDULE_D"
    # Order matters: 1040-X before 1040.
    if "FORM 1040-X" in upper:
        return "1040-X"
    if "FORM 1040" in upper:
        return "1040"

    best, best_score = "UNKNOWN", 0
    for form_type, keywords in FORM_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in upper)
        if score > best_score:
            best, best_score = form_type, score
    return best


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
