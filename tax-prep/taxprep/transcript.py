"""IRS transcript parsers — local-only, stdlib only.

Four entry points:
  - parse_return_transcript: IRS Tax Return Transcript -> lines /
    transactions. Money is Decimal-safe strings (D2), never floats --
    the same convention as the account parser.
  - parse_wage_income_transcript: IRS Wage & Income Transcript -> payer blocks.
  - parse_account_transcript: IRS Tax Account Transcript -> lines /
    transactions (with cycle). Money is Decimal-safe strings, never floats.
  - parse_record_of_account: IRS Record of Account -> {"return_section",
    "account_section", "unparsed_lines", "unparsed_spans"}. Block model
    (X3b): an anchor-event scan over the whole text finds every return
    header and account anchor with no ordering assumption; each line's
    block section is the nearest anchor at/before it; summary lines are
    routed by grammar, transactions by their span's block section.

Mapping contract (return transcript):
  - Each summary line is normalized (strip, collapse internal whitespace,
    UPPERCASE), its label region is extracted (text before the value/colon,
    leading tax-year token removed), and matched against an explicit table
    of the IRS Tax Return Transcript's actual label strings. Matching is
    exact-first, then longest/most-specific prefix wins where labels nest
    ("TOTAL TAX" vs "TOTAL TAX PAYMENTS") — never first-match-wins on
    substrings.
  - Ambiguity is surfaced, never silently resolved: a line whose label
    matches several table entries with different keys leaves every
    candidate field unset and is recorded in ``unparsed_lines`` prefixed
    ``"AMBIGUOUS: "``. No conflict-raising infrastructure exists yet; a
    later arc will raise these as review conflicts. Until then they are
    visible and flaggable here, never a quiet wrong value.
  - No silent drops: every non-blank, non-structural line is either mapped
    to a field, consumed as a transaction, or listed in ``unparsed_lines``
    (verbatim, or prefixed ``AMBIGUOUS:`` / ``DUPLICATE <key>:``).
  - Provenance hook (R15): ``line_raw_text`` maps each mapped key to the
    verbatim source line it was parsed from, so downstream field builders
    can carry real evidence instead of synthesized ``""`` raw_text.

Design note: these formats vary across sources. Both parsers prefer recall
over precision: any non-blank line that contributes nothing to the structured
output is kept verbatim in ``unparsed_lines``. Nothing is silently dropped.
"""

import re

# R15: transcript parsing carries field provenance. The parsers record,
# for every parsed key, the verbatim source line's character span in the
# input text (``line_spans`` / box ``span``), so downstream field
# builders carry real evidence instead of synthesized raw_text. Bump on
# ANY parser-logic change (feeds the R15 extractor id "transcript:<n>").
# "2": X2 -- return-transcript money is Decimal-safe strings (D2, was
# floats) and transcript title lines tolerate a "Form NNNN" prefix.
# "3": X3b -- the ROA is parsed as anchor blocks with no ordering
# assumption (byte-identical output on ordered ROAs); X4 -- repeated
# TC codes get ordinal-suffixed ingest field keys (tc_806_2), which is
# an ingest.py keying change riding on the same parse.
TRANSCRIPT_VERSION = "3"


def _line_offsets(text: str) -> list[int]:
    """Start offset of each line in ``text`` (splitlines order)."""
    offsets: list[int] = []
    pos = 0
    for line in text.splitlines(keepends=True):
        offsets.append(pos)
        pos += len(line)
    return offsets

# Structural lines: the transcript title / standalone tax-year declaration.
# These are represented by form_type / tax_year, so they are consumed rather
# than reported as unparsed.
# X2: a title line may carry a "Form NNNN" prefix ("Form 1040 Tax Return
# Transcript") and may share its line with surrounding words (the real
# title line carries extra words) -- like the document-level detector,
# the title matches ANYWHERE in the line. A line the detector calls a
# title, the parsers consume as structural, never as unparsed content.
_FORM_TITLE_PREFIX = r"(?:form\s+[0-9][0-9a-z\-]*\s+)?"
_STRUCTURAL_LINE_RES = [
    re.compile(_FORM_TITLE_PREFIX
               + r"tax\s+return\s+transcript\b", re.IGNORECASE),
    re.compile(_FORM_TITLE_PREFIX
               + r"wage\s+and\s+income\s+transcript\b", re.IGNORECASE),
    re.compile(_FORM_TITLE_PREFIX
               + r"(?:tax\s+)?account\s+transcript\b", re.IGNORECASE),
    re.compile(_FORM_TITLE_PREFIX
               + r"record\s+of\s+account\b", re.IGNORECASE),
    re.compile(r"^\s*tax\s*(year|period)\s*[:\-]?\s*\d{4}\s*$", re.IGNORECASE),
    # D5: "Tax Period Ending: Dec. 31, 2024" is a header, never a
    # label. Without this, the bare ("TAX", "total_tax") table entry
    # prefix-matches "TAX PERIOD ENDING" and the day number 31 reads
    # as total_tax.
    re.compile(r"^\s*tax\s+period\s+ending\b", re.IGNORECASE),
]


def _is_structural(line: str) -> bool:
    # search (not match): X2 title patterns match anywhere in the line.
    # The ^-anchored entries (tax year / period ending) behave
    # identically under search.
    return any(pat.search(line) for pat in _STRUCTURAL_LINE_RES)

# ---------------------------------------------------------------------------
# Return transcript: exact normalized label table.
#
# Each entry is (NORMALIZED_LABEL, key): the IRS Tax Return Transcript's
# actual label string, normalized (stripped, single spaces, UPPERCASE).
# A summary line is normalized the same way, its label region is extracted
# (see _label_candidate), and matched as follows:
#   * exact label match wins;
#   * otherwise the longest table label that prefixes the label region
#     (followed by a separator) wins -- most-specific wins where labels
#     nest ("TOTAL TAX" vs "TOTAL TAX PAYMENTS"), never first-match-wins
#     on substrings;
#   * if the longest match is shared by entries with different keys, the
#     line is AMBIGUOUS (see module docstring): no field is set.
# Table entries are (label, key) pairs rather than a dict so that a
# conflicting duplicate can never be silently resolved by dict ordering --
# the matcher flags it instead.
# ---------------------------------------------------------------------------

_RETURN_LABEL_TABLE = [
    # -- core summary vocabulary (original 9 keys) --
    ("ADJUSTED GROSS INCOME", "agi"),
    ("ADJUSTED GROSS INCOME PER COMPUTER", "agi"),
    ("AGI", "agi"),
    ("TAXABLE INCOME", "taxable_income"),
    ("TOTAL TAX", "total_tax"),
    ("TOTAL TAX PER COMPUTER", "total_tax"),
    ("TOTAL TAX LIABILITY", "total_tax"),
    ("TAX", "total_tax"),
    ("TAX PER COMPUTER", "total_tax"),
    ("FEDERAL INCOME TAX WITHHELD", "withholding"),
    ("WITHHOLDING", "withholding"),
    ("ESTIMATED TAX PAYMENTS", "estimated_payments"),
    ("ESTIMATED PAYMENTS", "estimated_payments"),
    ("REFUND", "refund"),
    ("REFUND AMOUNT", "refund"),
    ("OVERPAID", "refund"),
    ("OVERPAYMENT", "refund"),
    ("AMOUNT OWED", "amount_owed"),
    ("AMOUNT YOU OWE", "amount_owed"),
    ("BALANCE DUE", "amount_owed"),
    ("AMOUNT DUE", "amount_owed"),
    ("EXEMPTIONS", "exemptions"),
    ("NUMBER OF EXEMPTIONS", "exemptions"),
    ("FILING STATUS", "filing_status"),
    # -- payments detail (kept distinct from total_tax) --
    ("TOTAL TAX PAYMENTS", "total_payments"),
    ("TOTAL PAYMENTS", "total_payments"),
    # -- other withholding (never merged into withholding) --
    ("SOCIAL SECURITY TAX WITHHELD", "ss_tax_withheld"),
    # -- income detail (extended vocabulary) --
    ("WAGES, SALARIES, TIPS, ETC.", "wages"),
    ("WAGES", "wages"),
    ("TAXABLE INTEREST", "taxable_interest"),
    ("TAX-EXEMPT INTEREST", "tax_exempt_interest"),
    ("ORDINARY DIVIDENDS", "ordinary_dividends"),
    ("QUALIFIED DIVIDENDS", "qualified_dividends"),
    ("CAPITAL GAIN OR (LOSS)", "capital_gain_loss"),
    ("CAPITAL GAIN OR LOSS", "capital_gain_loss"),
    # -- Schedule D --
    ("SHORT-TERM CAPITAL GAIN OR (LOSS)", "short_term_gain_loss"),
    ("LONG-TERM CAPITAL GAIN OR (LOSS)", "long_term_gain_loss"),
    ("SHORT-TERM CAPITAL LOSS CARRYOVER", "short_term_carryover"),
    ("LONG-TERM CAPITAL LOSS CARRYOVER", "long_term_carryover"),
    ("CAPITAL LOSS CARRYOVER", "capital_loss_carryover"),
]

# Keys whose value is free text / an integer rather than money.
_TEXT_KEYS = {"filing_status"}
_INT_KEYS = {"exemptions"}

# Separators allowed between a prefix-matched label and the rest of the
# label region (e.g. "TOTAL TAX" prefixing "TOTAL TAX.").
_PREFIX_SEPARATORS = (" ", ":", "-", ".", ",")

# Leading tax-year token on a summary line ("2023 ADJUSTED GROSS INCOME").
_LEADING_YEAR_RE = re.compile(r"^(?:19|20)\d{2}\b[\s\-:]*")


def _normalize_line(raw: str) -> str:
    """Strip, collapse internal whitespace, uppercase."""
    return re.sub(r"\s+", " ", raw.strip()).upper()


def _label_candidate(norm: str) -> str:
    """Extract the label region from a normalized summary line.

    The label is the text before the value: cut at the first money match,
    then at the first colon ("Label: value" layout), then strip a leading
    tax-year token. Trailing "." is preserved -- real IRS labels such as
    "WAGES, SALARIES, TIPS, ETC." end with one.
    """
    m = _MONEY_RE.search(norm)
    head = norm[: m.start()] if m else norm
    if ":" in head:
        head = head.split(":", 1)[0]
    head = head.strip(" ,;-")
    head = _LEADING_YEAR_RE.sub("", head).strip(" ,;-")
    return head


def _match_label(candidate: str, table) -> tuple[str | None, str | None, bool]:
    """Match a label candidate against an exact-label table.

    Returns (key, matched_label, ambiguous). Exact match wins; otherwise
    the longest prefixing label wins. If the longest length is shared by
    entries with different keys, ambiguous=True and no key is returned.
    """
    if not candidate:
        return None, None, False
    hits: list[tuple[int, str, str]] = []
    for label, key in table:
        if candidate == label:
            hits.append((len(label), key, label))
        elif candidate.startswith(label):
            nxt = candidate[len(label):len(label) + 1]
            if nxt in _PREFIX_SEPARATORS:
                hits.append((len(label), key, label))
    if not hits:
        return None, None, False
    best = max(length for length, _, _ in hits)
    winners = [(key, label) for length, key, label in hits if length == best]
    keys = {key for key, _ in winners}
    if len(keys) > 1:
        return None, None, True
    return winners[0][0], winners[0][1], False


def _match_return_label(candidate: str) -> tuple[str | None, str | None, bool]:
    """Match a label candidate against the return-transcript table."""
    return _match_label(candidate, _RETURN_LABEL_TABLE)


def _label_span_re(label: str) -> re.Pattern:
    """Regex matching the label in a raw line (flexible whitespace)."""
    return re.compile(
        r"\s+".join(re.escape(tok) for tok in label.split(" ")),
        re.IGNORECASE,
    )


def _summary_value(raw: str, key: str, label: str):
    """Extract the value for a matched key from the raw line.

    The value region is the text after the matched label; falls back to
    the whole line. Returns None when no usable value is present.
    Money values are Decimal-safe strings (D2), never floats -- the
    same _money_str convention the account parser uses.
    """
    after = raw
    m = _label_span_re(label).search(raw)
    if m:
        after = raw[m.end():]
    if key in _TEXT_KEYS:
        value = after.strip(" :-\t") or None
        if not value:
            value = _MONEY_RE.sub("", raw).strip(" :-\t") or None
        return value
    if key in _INT_KEYS:
        m_int = re.search(r"\d+", after)
        return int(m_int.group(0)) if m_int else None
    # D5: dates are blanked before the money search -- numbers inside
    # dates ("Dec. 31, 2024", "12-31-2024") are never amounts.
    value = _money_str(_blank_dates(after))
    if value is None:
        value = _money_str(_blank_dates(raw))
    return value

# Money extraction: $1,234.00, 1234.00, ($1,234.00) for negatives, "1234.00CR".
_MONEY_RE = re.compile(r"\$?\s*\(?(\d{1,3}(?:,\d{3})*|\d+)(?:\.(\d{1,2}))?\)?\s*(CR)?")

# Tax-year hints: "Tax Year: 2023", "Tax Period 202312", "2023 Tax Year".
_TAX_YEAR_RE = re.compile(
    r"(?:tax\s*(?:year|period)[:\s]*|period\s*ending\s*)"
    r"(?:20(?:0\d|1\d|2\d|30))\b", re.IGNORECASE
)
_TAX_YEAR_ANY_RE = re.compile(r"\b(20(?:0\d|1\d|2\d|30))\b")

# Transaction line: 3-digit code, optional MM-DD-YYYY date, optional money,
# rest is description. e.g. "150 Tax return filed 04-15-2024 $1,234.00"
_TRANSACTION_CODE_RE = re.compile(r"^\s*(\d{3})\s+")
_DATE_RE = re.compile(r"\b(\d{2}-\d{2}-\d{4})\b")
# Amount at end of a transaction line: "... $1,234.00" or "... -$1,234.00"
_TXN_AMOUNT_RE = re.compile(
    r"[-−]?\s*\$?\s*\(?\s*(\d{1,3}(?:,\d{3})*|\d+)(?:\.(\d{1,2}))?\s*\)?\s*(CR)?\s*$"
)

# Account-transcript cycle: 8 digits YYYYWWDD, e.g. 20241205.
_CYCLE_RE = re.compile(r"\b((?:19|20)\d{6})\b")

# Record-of-Account section boundaries: the account section starts at the
# first "TAX ACCOUNT TRANSCRIPT" (or "ACCOUNT TRANSCRIPT") line; the return
# section starts at "TAX RETURN TRANSCRIPT" when present.
_ACCOUNT_SECTION_HEADER_RE = re.compile(
    r"^\s*(?:tax\s+)?account\s+transcript\s*$", re.IGNORECASE)
_RETURN_SECTION_HEADER_RE = re.compile(
    r"^\s*tax\s+return\s+transcript\s*$", re.IGNORECASE)

# X3: the account-section anchor. The whole-line _ACCOUNT_SECTION_HEADER_RE
# above misses real ROAs, whose account section often carries no clean
# title line at all. The anchor is the first line (at/after the return
# section start) that is either a tolerant account-transcript title --
# X2 semantics: "account transcript" anywhere in the line, optional
# "Form NNNN"/"tax" prefix and surrounding words -- or an
# account-balance/accrual label. The document title "record of account"
# is never an anchor (most-specific-wins, as in detect_transcript_type).
# TC transaction lines are deliberately NOT anchors: the return parser
# also consumes them (real return transcripts list TC 150/806/...), so
# they are ambiguous between sections.
_ACCOUNT_TITLE_ANCHOR_RE = re.compile(
    r"(?:form\s+[0-9][0-9a-z\-]*\s+)?(?:tax\s+)?account\s+transcript\b",
    re.IGNORECASE)


def _is_account_section_anchor(line: str) -> bool:
    """Does this line start the ROA's account section?"""
    norm = _normalize_line(line)
    if "RECORD OF ACCOUNT" in norm:
        return False
    if _ACCOUNT_TITLE_ANCHOR_RE.search(line):
        return True
    candidate = _label_candidate(norm)
    key, _, ambiguous = _match_label(candidate, _ACCOUNT_LABEL_TABLE)
    return key is not None or ambiguous


# ---------------------------------------------------------------------------
# Account transcript: exact normalized label table.
#
# The IRS Tax Account Transcript's balance/accrual vocabulary is small and
# exact. Same contract as the return table: entries are (label, key) pairs,
# matching is exact-first then longest-prefix, and a longest-match shared
# by entries with different keys is AMBIGUOUS, never silently resolved.
# Real label layouts covered:
#   "Account Balance: $1,234.56"                    -> exact match
#   "Accrued Interest: $12.34 as of 09/22/2025"    -> exact match
#   "Accrued interest as of 09/22/2025: $12.34"    -> prefix match
#     ("ACCRUED INTEREST" + separator, value after the label span)
# ---------------------------------------------------------------------------

_ACCOUNT_LABEL_TABLE = [
    ("ACCOUNT BALANCE", "account_balance"),
    ("ACCRUED INTEREST", "accrued_interest"),
    ("ACCRUED PENALTY", "accrued_penalty"),
]

# ---------------------------------------------------------------------------
# Wage & income transcript
# ---------------------------------------------------------------------------

_FORM_TYPES = [
    "1099-INT", "1099-DIV", "1099-B", "1099-NEC",
    "1099-R", "1099-MISC", "1099-G",
    "W-2",
]
_FORM_TYPE_RE = re.compile(
    r"\b(" + "|".join(re.escape(f) for f in _FORM_TYPES) + r")\b"
)

# Payer block headers: "ACME CORP 12-3456789", "Payer: ACME CORP", "EIN 12-3456789"
_PAYER_HEADER_RES = [
    re.compile(r"(?i)^\s*(?:payer|employer)\s*[:\-]\s*(.+)$"),
    re.compile(r"^\s*([A-Z][A-Za-z0-9 .,'&\-]{3,}?)\s+(\d{2}-\d{7,9})\s*$"),
]
_EIN_RE = re.compile(r"\b(\d{2}-\d{7,9})\b")

# Box lines: "Box 1 Wages, tips, other compensation: $50,000.00"
_BOX_RE = re.compile(
    r"(?i)^\s*(?:box\s+)?([0-9]{1,2}[a-zA-Z]?)\s*[:\-.\s]+\s*(.+)$"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_money(raw: str) -> float | None:
    """Extract the first money value from a string, else None.

    Handles $1,234.56, (1,234.56) / -$1,234.56 / 1234.56CR as negative.
    """
    m = _MONEY_RE.search(raw)
    if not m:
        return None
    dollars, cents, cr = m.groups()
    value = float(dollars.replace(",", "")) + (
        float(cents) / (10 ** len(cents)) if cents else 0.0
    )
    negative = "(" in raw or cr or re.match(r"^\s*[-−]", raw.strip())
    return -value if negative else value


# Money as a Decimal-safe string: the exact digits from the source, never
# floated. "$85,420.00" -> "85420.00"; "($50.00)" / "$50.00CR" / "-$50.00"
# -> "-50.00". None when no money is present. Negativity is read from the
# matched money region (parens/CR) or a leading dash on the searched text.
_MONEY_STR_RE = re.compile(
    r"\$?\s*\(?(\d{1,3}(?:,\d{3})*|\d+)(?:\.(\d{1,2}))?\)?\s*(CR)?")


def _money_str(raw: str) -> str | None:
    """Decimal-safe money string from a string, else None."""
    m = _MONEY_STR_RE.search(raw)
    if not m:
        return None
    dollars, cents, cr = m.groups()
    body = dollars.replace(",", "") + ("." + cents if cents else "")
    # Negativity: parens/CR on the match, or a "(" / leading dash
    # immediately before it ("($10.00)", "Balance: -$50.00").
    prefix = raw[:m.start()].rstrip()
    neg = (("(" in m.group(0)) or prefix.endswith("(")
           or prefix.endswith(("-", "\u2212")) or cr
           or re.match(r"^\s*[-−]", raw.strip()))
    return ("-" if neg else "") + body


def _detect_tax_year(text: str) -> int | None:
    m = _TAX_YEAR_RE.search(text)
    if m:
        year = _TAX_YEAR_ANY_RE.search(m.group(0))
        return int(year.group(1)) if year else None
    return None


def _detect_tax_year_loose(text: str) -> int | None:
    """Fallback: any 2000-2030 year near 'tax' on the same line."""
    for line in text.splitlines():
        if "tax" in line.lower():
            m = _TAX_YEAR_ANY_RE.search(line)
            if m:
                return int(m.group(1))
    return None


# ---------------------------------------------------------------------------
# Return transcript
# ---------------------------------------------------------------------------

def parse_return_transcript(text: str, tax_year: int | None = None) -> dict:
    """Parse IRS Tax Return Transcript text into a dict.

    Returns {"tax_year", "lines", "line_raw_text", "transactions",
    "unparsed_lines"} per the module contract. ``lines`` maps each parsed
    key to its value; ``line_raw_text`` maps the same key to the verbatim
    source line (R15 evidence hook).
    """
    if tax_year is None:
        tax_year = _detect_tax_year(text) or _detect_tax_year_loose(text)

    lines: dict = {}
    line_raw_text: dict = {}  # key -> verbatim source line it was parsed from
    line_spans: dict = {}     # R15: key -> (start, end) char span of that
                              #   verbatim line in the input text
    line_confidence: dict = {}  # R15: key -> "high" (exact label match) |
                                #   "medium" (longest-prefix match). Derived
                                #   from the match, never hardcoded.
    transactions: list = []
    unparsed_lines: list = []
    unparsed_spans: list = []  # R15: parallel to unparsed_lines; the span
                               #   of the verbatim raw line (the
                               #   "AMBIGUOUS: "/"DUPLICATE " prefixes are
                               #   display-only, never part of the span)
    # Track (line, offset) pairs that were consumed by transaction parsing so
    # they are not also treated as summary lines.
    consumed_as_transaction: set = set()

    raw_lines = text.splitlines()
    offsets = _line_offsets(text)

    # First pass: transactions (3-digit code led lines).
    for idx, raw in enumerate(raw_lines):
        if not raw.strip():
            continue
        m = _TRANSACTION_CODE_RE.match(raw)
        if not m:
            continue
        code = m.group(1)
        rest = raw[m.end():].strip()
        date_m = _DATE_RE.search(rest)
        date = date_m.group(1) if date_m else None
        amt_m = _TXN_AMOUNT_RE.search(rest)
        # D2: Decimal-safe string, never a float (matches the account
        # parser's convention).
        amount = _money_str(amt_m.group(0)) if amt_m else None
        description = rest
        if amt_m:
            description = (rest[: amt_m.start()] + rest[amt_m.end():]).strip()
        if date_m and date in description:
            description = description.replace(date, "", 1).strip()
        description = re.sub(r"\s{2,}", " ", description).strip(" -:,;")
        transactions.append({
            "code": code,
            "date": date,
            "amount": amount,
            "description": description,
            # R15: verbatim evidence -- the full raw line, never the
            # code/date/amount-stripped description.
            "raw": raw,
            "span": (offsets[idx], offsets[idx] + len(raw)),
        })
        consumed_as_transaction.add(idx)

    # Second pass: summary lines -- exact normalized label table, never
    # first-match-wins on substrings. Every non-blank, non-structural line
    # is either mapped, flagged AMBIGUOUS / DUPLICATE, or kept verbatim in
    # unparsed_lines. Nothing is silently dropped.
    for idx, raw in enumerate(raw_lines):
        if not raw.strip() or idx in consumed_as_transaction:
            continue
        norm = _normalize_line(raw)
        if _is_structural(raw) or _is_structural(
                _LEADING_YEAR_RE.sub("", norm)):
            continue
        candidate = _label_candidate(norm)
        key, label, ambiguous = _match_return_label(candidate)
        span = (offsets[idx], offsets[idx] + len(raw))
        if ambiguous:
            # Matches several table entries: every candidate field stays
            # unset; the line is visible and flaggable, never a quiet
            # wrong value.
            unparsed_lines.append("AMBIGUOUS: " + raw)
            unparsed_spans.append(span)
            continue
        if key is None:
            unparsed_lines.append(raw)
            unparsed_spans.append(span)
            continue
        value = _summary_value(raw, key, label)
        if value is None:
            # Label recognized but no usable value: visible, not mapped.
            unparsed_lines.append(raw)
            unparsed_spans.append(span)
            continue
        if key in lines:
            # Deterministic keep-first; the repeat stays visible rather
            # than being silently dropped.
            unparsed_lines.append(f"DUPLICATE {key}: " + raw)
            unparsed_spans.append(span)
            continue
        lines[key] = value
        line_raw_text[key] = raw
        line_spans[key] = span
        # Derived confidence: exact label match -> high, longest-prefix
        # match -> medium. (candidate == label) is exactly the
        # exact-match case -- _match_label only returns a prefix hit
        # when the next char is a separator.
        line_confidence[key] = "high" if candidate == label else "medium"

    return {
        "tax_year": tax_year,
        "lines": lines,
        "line_raw_text": line_raw_text,
        "line_spans": line_spans,
        "line_confidence": line_confidence,
        "transactions": transactions,
        "unparsed_lines": unparsed_lines,
        "unparsed_spans": unparsed_spans,
    }


# ---------------------------------------------------------------------------
# Account transcript
# ---------------------------------------------------------------------------

def _account_summary_value(raw: str, label: str) -> str | None:
    """Extract the money value for a matched account key as a Decimal-safe
    string. The value region is the text after the matched label; falls
    back to the whole line. Dates ("as of 09/22/2025") are blanked first
    so their digits are never misread as money. None when no usable
    money is present."""
    after = raw
    m = _label_span_re(label).search(raw)
    if m:
        after = raw[m.end():]
    value = _money_str(_blank_dates(after))
    if value is None:
        value = _money_str(_blank_dates(raw))
    return value


_SLASH_DATE_RE = re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b")

# Month-name dates: "Dec. 31, 2024", "December 31 2024".
_MONTH_DATE_RE = re.compile(
    r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|"
    r"Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|"
    r"Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?"
    r"\s+\d{1,2},?\s+\d{4}\b",
    re.IGNORECASE,
)


def _blank_dates(text: str) -> str:
    """Blank dash/slash/month-name dates so their digits can't read as
    money. (D5: numbers inside dates are never amounts.)"""
    text = _DATE_RE.sub(" ", text)
    text = _SLASH_DATE_RE.sub(" ", text)
    return _MONTH_DATE_RE.sub(" ", text)


def _parse_account_transaction(raw: str) -> dict | None:
    """Parse one account-transcript transaction line.

    "150 Tax return filed 20241205 04-15-2025 $1,234.00" ->
    {"code": "150", "description": "Tax return filed", "cycle": "20241205",
     "date": "04-15-2025", "amount": "1234.00"}.
    Date, cycle, and amount are stripped from the description in that
    order so a dateless/amountless line can never misread its date or
    cycle as money. Returns None when the line is not code-led.
    """
    m = _TRANSACTION_CODE_RE.match(raw)
    if not m:
        return None
    code = m.group(1)
    work = raw[m.end():].strip()
    date = None
    dm = _DATE_RE.search(work)
    if dm:
        date = dm.group(1)
        work = work[:dm.start()] + " " + work[dm.end():]
    cycle = None
    cm = _CYCLE_RE.search(work)
    if cm:
        cycle = cm.group(1)
        work = work[:cm.start()] + " " + work[cm.end():]
    amount = None
    am = _TXN_AMOUNT_RE.search(work)
    if am:
        amount = _money_str(am.group(0))
        work = work[:am.start()] + work[am.end():]
    description = re.sub(r"\s{2,}", " ", work).strip(" -:,;")
    return {
        "code": code,
        "description": description,
        "cycle": cycle,
        "date": date,
        "amount": amount,
    }


def parse_account_transcript(text: str, tax_year: int | None = None) -> dict:
    """Parse IRS Tax Account Transcript text into a dict.

    Returns {"lines", "line_raw_text", "transactions", "unparsed_lines"}
    per the R17 contract -- exactly these four keys. ``lines`` maps each
    parsed key (account_balance, accrued_interest, accrued_penalty) to a
    Decimal-safe money string, never a float; ``line_raw_text`` maps the
    same key to the verbatim source line (R15 evidence hook);
    ``transactions`` are {"code", "description", "cycle", "date",
    "amount"} dicts covering the account TC vocabulary (150, 806,
    290/291, 971/977, 766/768, 846, and any other code-led line).
    Same D4 discipline as the return parser: exact normalized labels
    from an explicit table, longest-match where labels nest, AMBIGUOUS
    raised never silently resolved, every non-blank non-structural line
    mapped or in unparsed_lines.
    """
    lines: dict = {}
    line_raw_text: dict = {}
    line_spans: dict = {}       # R15: key -> (start, end) of the verbatim
                                #   line in the input text
    line_confidence: dict = {}  # R15: "high" (exact) | "medium" (prefix)
    transactions: list = []
    unparsed_lines: list = []
    unparsed_spans: list = []   # R15: parallel to unparsed_lines
    consumed_as_transaction: set = set()

    raw_lines = text.splitlines()
    offsets = _line_offsets(text)

    # First pass: transactions (3-digit code led lines, cycle-aware).
    for idx, raw in enumerate(raw_lines):
        if not raw.strip():
            continue
        txn = _parse_account_transaction(raw)
        if txn is None:
            continue
        # R15: verbatim evidence -- the full raw line and its span.
        txn["raw"] = raw
        txn["span"] = (offsets[idx], offsets[idx] + len(raw))
        transactions.append(txn)
        consumed_as_transaction.add(idx)

    # Second pass: balance/accrual summary lines.
    for idx, raw in enumerate(raw_lines):
        if not raw.strip() or idx in consumed_as_transaction:
            continue
        norm = _normalize_line(raw)
        if _is_structural(raw) or _is_structural(
                _LEADING_YEAR_RE.sub("", norm)):
            continue
        candidate = _label_candidate(norm)
        key, label, ambiguous = _match_label(candidate, _ACCOUNT_LABEL_TABLE)
        span = (offsets[idx], offsets[idx] + len(raw))
        if ambiguous:
            unparsed_lines.append("AMBIGUOUS: " + raw)
            unparsed_spans.append(span)
            continue
        if key is None:
            unparsed_lines.append(raw)
            unparsed_spans.append(span)
            continue
        value = _account_summary_value(raw, label)
        if value is None:
            unparsed_lines.append(raw)
            unparsed_spans.append(span)
            continue
        if key in lines:
            unparsed_lines.append(f"DUPLICATE {key}: " + raw)
            unparsed_spans.append(span)
            continue
        lines[key] = value
        line_raw_text[key] = raw
        line_spans[key] = span
        line_confidence[key] = "high" if candidate == label else "medium"

    return {
        "lines": lines,
        "line_raw_text": line_raw_text,
        "line_spans": line_spans,
        "line_confidence": line_confidence,
        "transactions": transactions,
        "unparsed_lines": unparsed_lines,
        "unparsed_spans": unparsed_spans,
    }


# ---------------------------------------------------------------------------
# Record of Account — block model (X3b)
# ---------------------------------------------------------------------------

def _roa_anchor_events(raw_lines: list) -> list:
    """Anchor-event scan over the whole document.

    Returns [(line_idx, kind)] in document order for every return-header
    match (_RETURN_SECTION_HEADER_RE) and every account anchor
    (_is_account_section_anchor), searching from line 0 -- no
    return-then-account ordering assumption. A line matching both is a
    return header (precedence). X3's deliberate rules preserved: TC
    transaction lines are never anchors; the "RECORD OF ACCOUNT" doc
    title is never an anchor.
    """
    events = []
    for i, line in enumerate(raw_lines):
        if _RETURN_SECTION_HEADER_RE.match(line):
            events.append((i, "return"))
        elif _is_account_section_anchor(line):
            events.append((i, "account"))
    return events


def _roa_block_kinds(n_lines: int, events: list) -> list:
    """Block section ("return" / "account" / "doc") for each line.

    A line's block section is the kind of the nearest anchor at/before
    it. Lines before the first anchor: doc-level when the first anchor
    is a return header, return-block content when the first anchor is
    an account anchor (preserves the X3 behavior where text before the
    account anchor was parsed as return text).
    """
    kinds = []
    ev = 0
    cur = None
    pre = "doc" if events and events[0][1] == "return" else "return"
    for i in range(n_lines):
        while ev < len(events) and events[ev][0] <= i:
            cur = events[ev][1]
            ev += 1
        kinds.append(cur if cur is not None else pre)
    return kinds


def _roa_summary_claims(run: dict, off_to_idx: dict) -> tuple:
    """Per-line summary claims from a full-text parser run.

    Returns (mapped, unparsed): idx -> key for mapped summary lines,
    idx -> the verbatim unparsed entry (with any AMBIGUOUS:/DUPLICATE
    prefix) for lines the parser saw but did not map. Index keys come
    from the run's R15 spans, which are document-relative because the
    run covered the full text.
    """
    mapped, unparsed = {}, {}
    for key, span in (run.get("line_spans") or {}).items():
        mapped[off_to_idx[span[0]]] = key
    for entry, span in zip(run.get("unparsed_lines", []),
                           run.get("unparsed_spans", [])):
        unparsed[off_to_idx[span[0]]] = entry
    return mapped, unparsed


def _roa_pick_unparsed(ret_entry, acct_entry):
    """Deterministic unparsed entry when no parser mapped the line.

    A prefixed entry (AMBIGUOUS: / DUPLICATE) carries strictly more
    information than the bare raw line, so it wins; prefixed-in-both is
    unreachable on disjoint label tables -- the return parser's entry
    breaks that tie.
    """
    for entry in (ret_entry, acct_entry):
        if entry is not None and (
                entry.startswith("AMBIGUOUS: ")
                or entry.startswith("DUPLICATE ")):
            return entry
    return ret_entry if ret_entry is not None else acct_entry


def parse_record_of_account(text: str, tax_year: int | None = None) -> dict:
    """Parse IRS Record of Account text into a dict.

    Returns exactly {"return_section", "account_section",
    "unparsed_lines", "unparsed_spans"}. The block model (X3b): an
    anchor-event scan over the whole text finds every return header and
    account anchor with no ordering assumption; each line's block
    section is the nearest anchor at/before it. Both section parsers
    run once over the FULL text (so every R15 span is document-relative
    -- no span shifting), and claims are assigned per line:

      - summary lines by grammar: mapped by the return parser ->
        return_section, by the account parser -> account_section,
        mapped by both -> the line's block section wins (deterministic
        tie-break);
      - transaction lines are deduplicated by span (both parsers consume
        TC-led lines) and assigned to their span's block section,
        keeping that block section's parser's version of the dict;
      - lines no parser mapped -> unparsed of their block section
        (identical raws from both parsers' unparsed lists are deduped;
        AMBIGUOUS:/DUPLICATE prefixes are kept).

    Lines before the first anchor are document-level (top-level
    unparsed_lines/unparsed_spans, exactly as before) when the first
    anchor is a return header; when it is an account anchor they are
    return-block content. When there is no anchor at all the whole text
    is the return section, as before.
    """
    raw_lines = text.splitlines()
    offsets = _line_offsets(text)
    events = _roa_anchor_events(raw_lines)

    if not events:
        # No anchor anywhere: the whole text is the return section (X3
        # behavior preserved byte-identical).
        return {
            "return_section":
                parse_return_transcript(text, tax_year=tax_year),
            "account_section":
                parse_account_transcript("", tax_year=tax_year),
            "unparsed_lines": [],
            "unparsed_spans": [],
        }

    ret = parse_return_transcript(text, tax_year=tax_year)
    acct = parse_account_transcript(text, tax_year=tax_year)
    off_to_idx = {off: i for i, off in enumerate(offsets)}
    ret_mapped, ret_unparsed = _roa_summary_claims(ret, off_to_idx)
    acct_mapped, acct_unparsed = _roa_summary_claims(acct, off_to_idx)

    # The return section's tax_year is detected on the return block's
    # text, exactly as the pre-X3b section-slice parse did (a bare
    # tax_year=None therefore keeps the old detection quirks, e.g. a
    # TC-line date winning when no year line is in the block).
    kinds_pre = _roa_block_kinds(len(raw_lines), events)
    return_block_text = "\n".join(
        raw for i, raw in enumerate(raw_lines) if kinds_pre[i] == "return")
    resolved_year = (tax_year if tax_year is not None
                     else _detect_tax_year(return_block_text)
                     or _detect_tax_year_loose(return_block_text))

    # Transaction dedupe by span: both parsers consume the same TC-led
    # lines; the span is the line's identity.
    txn_by_idx: dict = {}
    for run, tag in ((ret, "ret"), (acct, "acct")):
        for t in run.get("transactions", []):
            idx = off_to_idx[t["span"][0]]
            txn_by_idx.setdefault(idx, {})[tag] = t

    def _new_section(with_year: bool) -> dict:
        sec = {
            "lines": {}, "line_raw_text": {}, "line_spans": {},
            "line_confidence": {}, "transactions": [],
            "unparsed_lines": [], "unparsed_spans": [],
        }
        if with_year:
            sec["tax_year"] = resolved_year
        return sec

    return_section = _new_section(True)
    account_section = _new_section(False)
    sections = {"return": return_section, "account": account_section}
    runs = {"return": ret, "account": acct}

    def _copy_summary(src: dict, key: str, dst: dict) -> None:
        dst["lines"][key] = src["lines"][key]
        dst["line_raw_text"][key] = src["line_raw_text"][key]
        dst["line_spans"][key] = src["line_spans"][key]
        dst["line_confidence"][key] = src["line_confidence"][key]

    kinds = kinds_pre
    doc_lines, doc_spans = [], []
    for i, raw in enumerate(raw_lines):
        kind = kinds[i]
        if kind == "doc":
            if raw.strip() and not _is_structural(raw):
                doc_lines.append(raw)
                doc_spans.append((offsets[i], offsets[i] + len(raw)))
            continue
        if not raw.strip() or _is_structural(raw):
            continue  # blank / structural: consumed by both parsers
        if i in txn_by_idx:
            got = txn_by_idx[i]
            t = got.get("ret" if kind == "return" else "acct")
            if t is None:  # unreachable: both parsers consume TC-led
                # lines, but never KeyError on a half claim
                t = next(iter(got.values()))
            sections[kind]["transactions"].append(t)
            continue
        rkey, akey = ret_mapped.get(i), acct_mapped.get(i)
        if rkey is not None and akey is not None:
            # Mapped by both: the line's block section wins, keeping
            # that section's parser's version of the entry.
            _copy_summary(runs[kind], rkey if kind == "return" else akey,
                          sections[kind])
        elif rkey is not None:
            _copy_summary(ret, rkey, return_section)
        elif akey is not None:
            _copy_summary(acct, akey, account_section)
        else:
            # Claimed by neither parser as a summary line: unparsed in
            # the line's block section (dedupe the identical raws both
            # parsers list; keep AMBIGUOUS:/DUPLICATE prefixes).
            entry = _roa_pick_unparsed(ret_unparsed.get(i),
                                      acct_unparsed.get(i))
            sections[kind]["unparsed_lines"].append(entry)
            sections[kind]["unparsed_spans"].append(
                (offsets[i], offsets[i] + len(raw)))

    return {
        "return_section": return_section,
        "account_section": account_section,
        "unparsed_lines": doc_lines,
        "unparsed_spans": doc_spans,
    }


# ---------------------------------------------------------------------------
# Wage & income transcript
# ---------------------------------------------------------------------------

def _new_payer(payer: str, payer_ein: str | None, form_type: str) -> dict:
    return {"payer": payer, "payer_ein": payer_ein,
            "form_type": form_type, "boxes": {},
            # R15 evidence: box_spans[box] = {"raw", "span", "confidence"};
            # header_* describe the payer-block header line (None when the
            # block was started by a form-type lead with no header yet).
            "box_spans": {},
            "header_raw": None, "header_span": None,
            "header_confidence": "low"}


def _parse_box_line(raw: str) -> tuple[str, object, bool, bool] | None:
    """Parse a 'Box N ... $X' line -> (box_key, value, labeled, money)
    or None.

    ``labeled`` is True when the line carries the explicit "Box N"
    keyword; ``money`` is True when the value parsed as money. Both
    drive the derived confidence (R15): "high" when labeled and money,
    "medium" otherwise.
    """
    m = _BOX_RE.match(raw)
    if not m:
        return None
    box_key, rest = m.group(1).strip(), m.group(2).strip()
    labeled = bool(re.match(r"(?i)^\s*box\b", raw))
    money = _parse_money(rest)
    if money is not None:
        # Require the box line to look money-ish: box labels are numeric.
        if re.search(r"\d", box_key):
            return box_key, money, labeled, True
        return None
    # Non-money box value: keep raw label -> value if it has substance.
    if len(rest) >= 2:
        return box_key, rest, labeled, False
    return None


def _box_confidence(labeled: bool, money: bool) -> str:
    """Derived confidence for a wage & income box line (R15)."""
    return "high" if (labeled and money) else "medium"


def parse_wage_income_transcript(text: str, tax_year: int | None = None) -> dict:
    """Parse IRS Wage & Income Transcript text into a dict.

    Returns {"tax_year", "payers", "unparsed_lines", "unparsed_spans"} per
    the module contract. Each payer dict additionally carries R15
    evidence: ``box_spans`` maps each box key to {"raw", "span",
    "confidence"} (the verbatim box line, its (start, end) char span in
    the input text, and the derived confidence), and ``header_raw`` /
    ``header_span`` / ``header_confidence`` describe the payer-block
    header line ("high" with an EIN, "medium" without, "low" when the
    block never got a header).
    """
    if tax_year is None:
        tax_year = _detect_tax_year(text) or _detect_tax_year_loose(text)

    payers: list = []
    unparsed_lines: list = []
    unparsed_spans: list = []
    current: dict | None = None
    pending_form_type: str | None = None
    offsets = _line_offsets(text)

    def flush_pending_header(name: str, ein: str | None) -> None:
        nonlocal current
        current = _new_payer(name, ein, pending_form_type or "UNKNOWN")
        payers.append(current)

    def _record_box(payer: dict, raw: str, span: tuple[int, int]) -> bool:
        """Parse one box line into the payer block. True when consumed."""
        parsed = _parse_box_line(raw.strip())
        if not parsed:
            return False
        key, value, labeled, money = parsed
        if key in payer["boxes"]:
            # Duplicate box label: keep both, suffix the repeat.
            n = 2
            while f"{key}({n})" in payer["boxes"]:
                n += 1
            key = f"{key}({n})"
        payer["boxes"][key] = value
        payer["box_spans"][key] = {
            "raw": raw,
            "span": span,
            "confidence": _box_confidence(labeled, money),
        }
        return True

    def _record_header(payer: dict, raw: str, span: tuple[int, int],
                       ein: str | None) -> None:
        payer["header_raw"] = raw
        payer["header_span"] = span
        payer["header_confidence"] = "high" if ein else "medium"

    for idx, raw in enumerate(text.splitlines()):
        if not raw.strip():
            continue
        stripped = raw.strip()
        span = (offsets[idx], offsets[idx] + len(raw))

        # Form-type line: attaches to the current payer block when it has
        # none yet (payer-first layout); otherwise starts a new block
        # (form-first layout, or a new form after a typed block).
        ft_m = _FORM_TYPE_RE.search(stripped)
        if ft_m:
            form_type = ft_m.group(1).upper()
            if current is None:
                pending_form_type = form_type
                current = _new_payer("UNKNOWN", None, form_type)
                payers.append(current)
            elif current["form_type"] == "UNKNOWN":
                current["form_type"] = form_type
                pending_form_type = None
            else:
                pending_form_type = form_type
                current = _new_payer("UNKNOWN", None, form_type)
                payers.append(current)
            continue

        # Payer block header.
        header = None
        for pat in _PAYER_HEADER_RES:
            m = pat.match(raw)
            if m:
                groups = m.groups()
                if len(groups) == 2:  # name + EIN
                    header = (groups[0].strip(), groups[1])
                else:
                    name = groups[0].strip()
                    ein_m = _EIN_RE.search(name)
                    ein = ein_m.group(1) if ein_m else None
                    if ein:
                        name = name.replace(ein, "").strip()
                    header = (name, ein)
                break
        if header:
            name, ein = header
            if ein is None:
                ein_m = _EIN_RE.search(raw)
                ein = ein_m.group(1) if ein_m else None
            if current is not None and current["payer"] == "UNKNOWN":
                # Fill in the placeholder started by a form-type lead.
                current["payer"] = name or "UNKNOWN"
                current["payer_ein"] = ein
                _record_header(current, raw, span, ein)
            else:
                flush_pending_header(name or "UNKNOWN", ein)
                _record_header(current, raw, span, ein)
            continue

        # Box line within a block.
        if current is not None:
            if _record_box(current, raw, span):
                continue

        # Standalone box-like line before any payer block: start an UNKNOWN
        # payer block rather than losing it.
        if _parse_box_line(stripped):
            current = _new_payer("UNKNOWN", None, pending_form_type or "UNKNOWN")
            payers.append(current)
            _record_box(current, raw, span)
            continue

        if not _is_structural(raw):
            unparsed_lines.append(raw)
            unparsed_spans.append(span)

    return {
        "tax_year": tax_year,
        "payers": payers,
        "unparsed_lines": unparsed_lines,
        "unparsed_spans": unparsed_spans,
    }
