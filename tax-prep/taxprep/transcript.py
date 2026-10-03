"""IRS transcript parsers — local-only, stdlib only.

Two entry points:
  - parse_return_transcript: IRS Tax Return Transcript -> lines / transactions.
  - parse_wage_income_transcript: IRS Wage & Income Transcript -> payer blocks.

Design note: these formats vary across sources. Both parsers prefer recall
over precision: any non-blank line that contributes nothing to the structured
output is kept verbatim in ``unparsed_lines``. Nothing is silently dropped.
"""

import re

# Structural lines: the transcript title / standalone tax-year declaration.
# These are represented by form_type / tax_year, so they are consumed rather
# than reported as unparsed.
_STRUCTURAL_LINE_RES = [
    re.compile(r"^\s*tax return transcript\s*$", re.IGNORECASE),
    re.compile(r"^\s*wage and income transcript\b", re.IGNORECASE),
    re.compile(r"^\s*tax\s*(year|period)\s*[:\-]?\s*\d{4}\s*$", re.IGNORECASE),
]


def _is_structural(line: str) -> bool:
    return any(pat.match(line) for pat in _STRUCTURAL_LINE_RES)

# ---------------------------------------------------------------------------
# Return transcript: normalized keys for common summary labels.
# Each entry: (snake_case key, list of label regexes matched case-insensitively
# against a line). First matching label wins within its own line.
# ---------------------------------------------------------------------------

_RETURN_LABEL_PATTERNS = [
    ("agi", [
        r"adjusted\s*gross\s*income",
        r"\bagi\b",
    ]),
    ("taxable_income", [
        r"taxable\s*income",
    ]),
    ("total_tax", [
        r"total\s*tax",
    ]),
    ("withholding", [
        r"federal\s*income\s*tax\s*withheld",
        r"\bwithholding\b",
        r"tax\s*withheld",
    ]),
    ("estimated_payments", [
        r"estimated\s*tax\s*payments?",
        r"estimated\s*payments?",
    ]),
    ("refund", [
        r"\brefund\b",
        r"overpayment",
    ]),
    ("amount_owed", [
        r"amount\s*owed",
        r"balance\s*due",
        r"amount\s*due",
    ]),
    ("exemptions", [
        r"\bexemptions?\b",
    ]),
    ("filing_status", [
        r"filing\s*status",
    ]),
]

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

    Returns {"tax_year", "lines", "transactions", "unparsed_lines"} per the
    module contract.
    """
    if tax_year is None:
        tax_year = _detect_tax_year(text) or _detect_tax_year_loose(text)

    lines: dict = {}
    transactions: list = []
    unparsed_lines: list = []
    # Track (line, offset) pairs that were consumed by transaction parsing so
    # they are not also treated as summary lines.
    consumed_as_transaction: set = set()

    raw_lines = text.splitlines()

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
        amount = _parse_money(amt_m.group(0)) if amt_m else None
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
        })
        consumed_as_transaction.add(idx)

    # Second pass: summary lines.
    for idx, raw in enumerate(raw_lines):
        if not raw.strip() or idx in consumed_as_transaction:
            continue
        matched = False
        lower = raw.lower()
        for key, patterns in _RETURN_LABEL_PATTERNS:
            for pat in patterns:
                m = re.search(pat, lower)
                if not m:
                    continue
                # Value region: prefer text after the matched label, else the
                # whole line (e.g. "2023 Adjusted Gross Income: $65,000").
                after = raw[m.end():]
                value: object
                if key == "filing_status":
                    value = after.strip(" :-\t") or None
                    if not value:
                        value = _MONEY_RE.sub("", raw).strip(" :-\t") or None
                    if value is None:
                        break  # label seen but no usable value
                elif key == "exemptions":
                    m_int = re.search(r"\d+", after)
                    value = int(m_int.group(0)) if m_int else None
                    if value is None:
                        break
                else:
                    value = _parse_money(after)
                    if value is None:
                        value = _parse_money(raw)
                    if value is None:
                        break  # label seen but no usable value
                if key not in lines:  # keep first occurrence
                    lines[key] = value
                matched = True
                break
            if matched:
                break
        if not matched and not _is_structural(raw):
            unparsed_lines.append(raw)

    return {
        "tax_year": tax_year,
        "lines": lines,
        "transactions": transactions,
        "unparsed_lines": unparsed_lines,
    }


# ---------------------------------------------------------------------------
# Wage & income transcript
# ---------------------------------------------------------------------------

def _new_payer(payer: str, payer_ein: str | None, form_type: str) -> dict:
    return {"payer": payer, "payer_ein": payer_ein,
            "form_type": form_type, "boxes": {}}


def _parse_box_line(raw: str) -> tuple[str, object] | None:
    """Parse a 'Box N ... $X' line -> (box_key, value) or None."""
    m = _BOX_RE.match(raw)
    if not m:
        return None
    box_key, rest = m.group(1).strip(), m.group(2).strip()
    money = _parse_money(rest)
    if money is not None:
        # Require the box line to look money-ish: box labels are numeric.
        if re.search(r"\d", box_key):
            return box_key, money
        return None
    # Non-money box value: keep raw label -> value if it has substance.
    if len(rest) >= 2:
        return box_key, rest
    return None


def parse_wage_income_transcript(text: str, tax_year: int | None = None) -> dict:
    """Parse IRS Wage & Income Transcript text into a dict.

    Returns {"tax_year", "payers", "unparsed_lines"} per the module contract.
    """
    if tax_year is None:
        tax_year = _detect_tax_year(text) or _detect_tax_year_loose(text)

    payers: list = []
    unparsed_lines: list = []
    current: dict | None = None
    pending_form_type: str | None = None

    def flush_pending_header(name: str, ein: str | None) -> None:
        nonlocal current
        current = _new_payer(name, ein, pending_form_type or "UNKNOWN")
        payers.append(current)

    for raw in text.splitlines():
        if not raw.strip():
            continue
        stripped = raw.strip()

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
            else:
                flush_pending_header(name or "UNKNOWN", ein)
            continue

        # Box line within a block.
        if current is not None:
            box = _parse_box_line(stripped)
            if box:
                key, value = box
                if key in current["boxes"]:
                    # Duplicate box label: keep both, suffix the repeat.
                    n = 2
                    while f"{key}({n})" in current["boxes"]:
                        n += 1
                    key = f"{key}({n})"
                current["boxes"][key] = value
                continue

        # Standalone box-like line before any payer block: start an UNKNOWN
        # payer block rather than losing it.
        box = _parse_box_line(stripped)
        if box:
            current = _new_payer("UNKNOWN", None, pending_form_type or "UNKNOWN")
            payers.append(current)
            current["boxes"][box[0]] = box[1]
            continue

        if not _is_structural(raw):
            unparsed_lines.append(raw)

    return {
        "tax_year": tax_year,
        "payers": payers,
        "unparsed_lines": unparsed_lines,
    }
