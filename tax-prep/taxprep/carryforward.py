"""Capital-loss carryforward engine (Phase 3).

Recomputes the capital loss carryforward chain for amended returns
(Form 1040-X, tax years 2023-2026) from validated 1099-B lots.

All money math is Decimal-only. Float inputs are rejected loudly --
never silently converted.

Sign conventions
----------------
* ``st_carry_in`` / ``lt_carry_in``: POSITIVE magnitudes of prior-year
  losses carried into this year (the IRS worksheet carries them as
  positive amounts).
* ``st_current`` / ``lt_current``: SIGNED net gain/loss for the year
  (negative = net loss) -- the Schedule D line 7 / line 15 concepts.

  Hence ``st_net = st_current - st_carry_in``: the carry-in is a loss
  magnitude, so it enters the signed net with a minus sign. (A literal
  ``st_carry_in + st_current`` reading would shrink the loss pool
  instead of growing it and contradicts the chained-year behavior.)

Worksheet model
---------------
Implements the IRS Schedule D Capital Loss Carryover Worksheet
literally, lines 1-13 (verified against the 2024 Schedule D
instructions, https://www.irs.gov/pub/irs-pdf/i1040sd.pdf; the
2023/2025/2026 worksheets are structurally identical -- only the
"from/to" years differ):

* ``line7``  = ``st_current - st_carry_in``  (signed ST total)
* ``line15`` = ``lt_current - lt_carry_in``  (signed LT total)
* ``line16`` = ``line7 + line15``; the capital loss deduction
  (line 21 concept) is ``min(|line16|, limit)`` when line 16 is a
  loss, else 0, with limit $3,000 ($1,500 MFS).
* L1 = ``taxable_income``: Form 1040 line 15 *as it would be*,
  possibly negative (the worksheet asks for the hypothetical
  negative amount in parentheses). When None, the worksheet's
  low-income path cannot be evaluated: L4 is set to L2 and a
  warning is recorded -- i.e. we assume enough ordinary income
  to absorb the deduction. Phase 4 (the 1040-X builder) feeds
  actual taxable income back in and recomputes.
* L2 = the deduction as a positive amount.
* L3 = max(0, L1 + L2); L4 = min(L2, L3): the portion of the
  deduction that actually reduced taxable income.
* ST carryover: if line 7 is a loss, L5 = -line7; L6 = max(0,
  line15); L7 = L4 + L6; st_carry = max(0, L5 - L7). The L6 term
  is the key cross-term absorption: an LT gain reduces the ST
  loss pool before any carryover is figured.
* LT carryover: if line 15 is a loss, L9 = -line15;
  L10 = max(0, line7); L11 = max(0, L4 - L5); L12 = L10 + L11;
  lt_carry = max(0, L9 - L12).

All worksheet lines are returned in ``worksheet_lines`` for audit.

Known simplifications (out of scope)
------------------------------------
* The taxable-income limitation (worksheet lines 1-4) is modeled but
  needs Form 1040 line 15 per year; pass ``taxable_income`` (or
  ``taxable_income_by_year``) once Phase 4 builds the 1040s --
  otherwise a warning records the assumption.
* Unrecaptured section 1250 gain (25% rate), 28% collectibles rate,
  and qualified-dividend / capital-gain worksheet interactions --
  flagged via ``flags`` into the ``warnings`` list when indicated.
* Wash sale (F3): box 1g (wash sale loss disallowed) is extracted per
  lot and ADDED BACK to the lot's gain/loss: per-lot gain/loss =
  1d proceeds - 1e basis + 1g. Box 1f is ACCRUED MARKET DISCOUNT
  (B1F: on Form 1099-B it is NOT federal income tax withheld) --
  Schedule B interest income (Phase 4), never part of gain/loss and
  never a withholding credit: from_store sums it separately as
  ``accrued_market_discount_1f_total`` for Phase 4 visibility. Box 4
  (federal income tax withheld) IS the withholding credit: from_store
  sums it separately as ``fed_withheld_4_total`` for the 1040
  withholding line (Phase 4).
* State carryforward rules (states differ; several do not conform to
  the federal worksheet).
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from . import exclusions

ANNUAL_LIMIT = Decimal("3000")
ANNUAL_LIMIT_MFS = Decimal("1500")

# Reason codes for the R3 carryforward guard. Form/status codes are
# checked defensively: MULTI_FORM, BLOCKED and ORPHANED are not in the
# current models.py enums (R1/R4/R5 add them), but the guard must
# refuse on them the moment any producer can emit them.
REASON_UNKNOWN_FORM = "unknown_form"
REASON_MULTI_FORM = "multi_form"
REASON_BLOCKED = "blocked"
REASON_ORPHANED = "orphaned"
REASON_MISSING_YEAR = "missing_year"
REASON_ZERO_LOTS = "zero_lots"
# G2: present-but-incomplete lots are blockers, never silently
# excluded. One entry per doc per code.
REASON_LOT_TERM_UNKNOWN = "lot_term_unknown"
REASON_LOT_MISSING_AMOUNTS = "lot_missing_amounts"
REASON_CODES = (
    REASON_UNKNOWN_FORM,
    REASON_MULTI_FORM,
    REASON_BLOCKED,
    REASON_ORPHANED,
    REASON_MISSING_YEAR,
    REASON_ZERO_LOTS,
    REASON_LOT_TERM_UNKNOWN,
    REASON_LOT_MISSING_AMOUNTS,
)

# canonical filing statuses -> annual limit is only status-sensitive for MFS
_STATUS_ALIASES = {
    "single": "single",
    "mfj": "mfj",
    "married filing jointly": "mfj",
    "mfs": "mfs",
    "married filing separately": "mfs",
    "hoh": "hoh",
    "head of household": "hoh",
    "qw": "qw",
    "qualifying widow(er)": "qw",
    "qualifying surviving spouse": "qw",
}

_FLAG_WARNINGS = {
    "unrecaptured_1250": (
        "unrecaptured section 1250 gain indicated: taxed at a maximum 25% "
        "rate -- not modeled; carryforward character may need manual splitting"
    ),
    "collectibles": (
        "collectibles gain/loss indicated: 28% maximum rate not modeled"
    ),
    "qualified_dividends": (
        "qualified dividends indicated: capital-gain worksheet interaction "
        "not modeled"
    ),
}


# -- input handling ----------------------------------------------------


def _coerce(name: str, v: Any) -> Decimal:
    """Coerce to Decimal; floats are rejected loudly, never converted."""
    if isinstance(v, bool):
        raise TypeError(f"{name}: bool is not a money amount")
    if isinstance(v, Decimal):
        return v
    if isinstance(v, int):
        return Decimal(v)
    if isinstance(v, float):
        raise TypeError(
            f"{name}: float {v!r} not allowed -- pass Decimal for exact money math"
        )
    if isinstance(v, str):
        s = v.strip().replace("$", "").replace(",", "")
        if not s:
            raise ValueError(f"{name}: empty money string")
        try:
            return Decimal(s)
        except InvalidOperation:
            raise ValueError(f"{name}: not a money amount: {v!r}")
    raise TypeError(f"{name}: unsupported type {type(v).__name__}; use Decimal")


def _normalize_status(filing_status: str) -> str:
    key = str(filing_status).strip().lower().replace("_", " ").replace("-", " ")
    key = " ".join(key.split())
    if key not in _STATUS_ALIASES:
        raise ValueError(
            f"unknown filing_status {filing_status!r}; "
            f"expected one of {sorted(set(_STATUS_ALIASES))}"
        )
    return _STATUS_ALIASES[key]


def _limit_for(status: str) -> Decimal:
    return ANNUAL_LIMIT_MFS if _normalize_status(status) == "mfs" else ANNUAL_LIMIT


def _fmt_money(d: Decimal) -> str:
    d = +d  # normalize -0 etc.
    s = f"${abs(d):,.2f}"
    return f"({s})" if d < 0 else s


# -- core --------------------------------------------------------------


def compute_year(
    st_carry_in: Any,
    lt_carry_in: Any,
    st_current: Any,
    lt_current: Any,
    filing_status: str,
    flags: dict | None = None,
    taxable_income: Any | None = None,
) -> dict:
    """One year's capital-loss computation -- the IRS Capital Loss
    Carryover Worksheet, lines 1-13, implemented literally.

    ``st_carry_in`` / ``lt_carry_in`` are positive loss magnitudes;
    ``st_current`` / ``lt_current`` are signed (negative = loss).
    ``taxable_income`` is the worksheet's line 1: Form 1040 line 15
    *as it would be*, possibly negative (pass a negative Decimal for
    the parenthesized hypothetical loss). When None, the low-income
    path cannot be evaluated -- L4 is set to L2 and a warning is
    recorded.

    Returns the full breakdown, ``worksheet_lines`` (L1..L13), and a
    ``warnings`` list.
    """
    st_carry_in = _coerce("st_carry_in", st_carry_in)
    lt_carry_in = _coerce("lt_carry_in", lt_carry_in)
    st_current = _coerce("st_current", st_current)
    lt_current = _coerce("lt_current", lt_current)
    if st_carry_in < 0 or lt_carry_in < 0:
        raise ValueError("carry-ins are positive loss magnitudes, got negatives")
    if taxable_income is not None:
        taxable_income = _coerce("taxable_income", taxable_income)
    status = _normalize_status(filing_status)
    limit = _limit_for(status)
    warnings: list[str] = []

    # Schedule D line concepts.
    line7 = st_current - st_carry_in
    line15 = lt_current - lt_carry_in
    line16 = line7 + line15
    deduction = min(-line16, limit) if line16 < 0 else Decimal("0")  # line 21

    # Worksheet lines 1-4: how much of the deduction actually reduced
    # taxable income.
    L1 = taxable_income
    L2 = deduction
    if L1 is None:
        L4 = L2
        warnings.append(
            "taxable income not supplied: worksheet line 4 set to line 2, "
            "i.e. the low-taxable-income limitation is not modeled -- "
            "recompute with taxable_income once the 1040 is built (Phase 4)"
        )
    else:
        L3 = L1 + L2
        if L3 < 0:
            L3 = Decimal("0")
        L4 = min(L2, L3)

    # Lines 5-8: short-term carryover.
    if line7 < 0:
        L5 = -line7
        L6 = line15 if line15 > 0 else Decimal("0")
        L7 = L4 + L6
        st_carry_out = L5 - L7
        if st_carry_out < 0:
            st_carry_out = Decimal("0")
    else:
        L5 = L6 = L7 = Decimal("0")
        st_carry_out = Decimal("0")

    # Lines 9-13: long-term carryover.
    if line15 < 0:
        L9 = -line15
        L10 = line7 if line7 > 0 else Decimal("0")
        L11 = L4 - L5
        if L11 < 0:
            L11 = Decimal("0")
        L12 = L10 + L11
        lt_carry_out = L9 - L12
        if lt_carry_out < 0:
            lt_carry_out = Decimal("0")
    else:
        L9 = L10 = L11 = L12 = Decimal("0")
        lt_carry_out = Decimal("0")

    for flag, active in (flags or {}).items():
        if not active:
            continue
        msg = _FLAG_WARNINGS.get(flag)
        warnings.append(msg if msg else f"unrecognized flag {flag!r} -- ignored")

    return {
        "filing_status": status,
        "st_carry_in": st_carry_in,
        "lt_carry_in": lt_carry_in,
        "st_current": st_current,
        "lt_current": lt_current,
        "st_net": line7,  # kept name for compatibility: Schedule D line 7
        "lt_net": line15,  # Schedule D line 15
        "net_loss": -line16 if line16 < 0 else Decimal("0"),
        "annual_limit": limit,
        "deductible_loss": deduction,
        "st_carry_out": st_carry_out,
        "lt_carry_out": lt_carry_out,
        "worksheet_lines": {
            "L1_taxable_income": L1,
            "L2_deduction": L2,
            "L4_used_deduction": L4,
            "L5_st_loss": L5,
            "L6_lt_gain": L6,
            "L7": L7,
            "L8_st_carryover": st_carry_out,
            "L9_lt_loss": L9,
            "L10_st_gain": L10,
            "L11": L11,
            "L12": L12,
            "L13_lt_carryover": lt_carry_out,
        },
        "warnings": warnings,
    }


def compute_chain(
    yearly_inputs: dict[int, dict],
    filing_status_by_year: dict[int, str],
    prior_carryover: dict | None = None,
    taxable_income_by_year: dict[int, Any] | None = None,
) -> dict:
    """Chain yearly computations; each year's carry-in is the prior carry-out.

    ``yearly_inputs``: {year: {"st_current": Decimal, "lt_current": Decimal,
    "flags"?: {...}}}. ``filing_status_by_year``: {year: status}.
    ``prior_carryover``: {"st": D, "lt": D} carried into the first year
    (e.g. the 2022 carryover into 2023); defaults to zeros.
    ``taxable_income_by_year``: optional {year: Decimal} worksheet line 1
    values (Form 1040 line 15 as it would be, possibly negative); years
    absent from the dict compute with the low-income warning.

    Returns {"years": {year: compute_year(...) result + "year"},
    "table": printable chain table,
    "warnings": [year-prefixed warnings],
    "carryforward_into_2026": {"st", "lt"}} -- the carry-out of the
    latest chained year before 2026 (for the upcoming return when 2026
    is the last chained year, this is 2025's carry-out).
    """
    years = sorted(yearly_inputs)
    if not years:
        raise ValueError("yearly_inputs is empty")
    prior = prior_carryover or {}
    st_in = _coerce("prior_carryover.st", prior.get("st", 0))
    lt_in = _coerce("prior_carryover.lt", prior.get("lt", 0))
    ti_by_year = taxable_income_by_year or {}

    results: dict[int, dict] = {}
    warnings: list[str] = []
    for y in years:
        if y not in filing_status_by_year:
            raise ValueError(f"no filing_status for year {y}")
        inp = yearly_inputs[y]
        r = compute_year(
            st_in,
            lt_in,
            inp.get("st_current", 0),
            inp.get("lt_current", 0),
            filing_status_by_year[y],
            flags=inp.get("flags"),
            taxable_income=ti_by_year.get(y),
        )
        r["year"] = y
        results[y] = r
        warnings.extend(f"{y}: {w}" for w in r["warnings"])
        st_in, lt_in = r["st_carry_out"], r["lt_carry_out"]

    # Carryforward INTO 2026 = carry-out of the latest chained year < 2026.
    into = {"st": Decimal("0"), "lt": Decimal("0")}
    earlier = [y for y in years if y < 2026]
    if earlier:
        last = results[max(earlier)]
        into = {"st": last["st_carry_out"], "lt": last["lt_carry_out"]}

    return {
        "years": results,
        "table": format_table(results, into),
        "warnings": warnings,
        "carryforward_into_2026": into,
    }


def format_table(results: dict[int, dict], into_2026: dict) -> str:
    """Printable chain table: year | ST in | LT in | ST current |
    LT current | deductible | ST out | LT out."""
    header = ["year", "ST in", "LT in", "ST current", "LT current",
              "deductible", "ST out", "LT out"]
    rows = []
    for y in sorted(results):
        r = results[y]
        rows.append([
            str(y),
            _fmt_money(r["st_carry_in"]),
            _fmt_money(r["lt_carry_in"]),
            _fmt_money(r["st_current"]),
            _fmt_money(r["lt_current"]),
            _fmt_money(r["deductible_loss"]),
            _fmt_money(r["st_carry_out"]),
            _fmt_money(r["lt_carry_out"]),
        ])
    widths = [max(len(row[i]) for row in [header] + rows) for i in range(len(header))]
    lines = [" | ".join(h.ljust(w) for h, w in zip(header, widths))]
    lines.append("-+-".join("-" * w for w in widths))
    for row in rows:
        lines.append(" | ".join(c.rjust(w) for c, w in zip(row, widths)))
    lines.append("")
    lines.append(
        f"Carryforward into 2026: ST {_fmt_money(into_2026['st'])}, "
        f"LT {_fmt_money(into_2026['lt'])}"
    )
    return "\n".join(lines)


# -- store adapter -----------------------------------------------------


def _parse_money_opt(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    return _coerce("1099-B box", value)


# The 1099-B lot table lives at fields["lots"]["value"]: a list of
# per-lot dicts (see extractors._extract_1099_b). Consumers iterate ALL
# lots -- there is no single-lot fallback; a document with an empty or
# missing lot table carries zero lots.


def _doc_lots(doc: Any) -> list[dict]:
    """The 1099-B lot table as a list of per-lot dicts (possibly empty)."""
    fields = getattr(doc, "fields", None) or {}
    lots = fields.get("lots")
    v = lots.get("value") if isinstance(lots, dict) else None
    return [l for l in v if isinstance(l, dict)] if isinstance(v, list) else []


def carryforward_blockers(store: Any, chained_years: list[int] | None = None) -> list[dict]:
    """R3 guard: PII-free blocker list [{"doc_id", "reason_code"}].

    Refuses (via the caller raising) while ANY document in the store is
    UNKNOWN, MULTI_FORM, BLOCKED, or ORPHANED, or has tax_year None,
    or while any 1099-B in a chained year carries no lot record at
    all, or carries a lot with unknown term (G2: ``lot_term_unknown``)
    or missing proceeds/basis (G2: ``lot_missing_amounts``) -- unless
    the Operator recorded an exclusion with a reason for that doc_id
    (taxprep.exclusions). Excluded or incomplete lots are blockers
    until the Operator disposes (supplies the term/amounts or excludes
    with a reason): never a silent omission. The scan is store-wide
    for document-level blockers; the lot checks cover ``chained_years``
    (defaults to every year present in the store).

    A document can carry several blocker entries (e.g. UNKNOWN form AND
    missing year; several lots with unknown term still yield ONE
    ``lot_term_unknown`` entry); the list is sorted by
    (doc_id, reason_code) for determinism. Only doc_ids and fixed
    reason codes appear -- never values, names, or exclusion reasons.
    """
    docs = store.list()
    data_dir = getattr(store, "data_dir", None)
    excluded: set[str] = set()
    if data_dir is not None:
        excluded = {e["doc_id"] for e in exclusions.list_exclusions(data_dir)}

    blockers: list[dict] = []
    for d in docs:
        if d.doc_id in excluded:
            continue
        form_type = getattr(d, "form_type", None)
        status = getattr(d, "status", None)
        if form_type == "UNKNOWN":
            blockers.append({"doc_id": d.doc_id,
                             "reason_code": REASON_UNKNOWN_FORM})
        elif form_type == "MULTI_FORM":
            blockers.append({"doc_id": d.doc_id,
                             "reason_code": REASON_MULTI_FORM})
        if status == "BLOCKED":
            blockers.append({"doc_id": d.doc_id,
                             "reason_code": REASON_BLOCKED})
        elif status == "ORPHANED":
            blockers.append({"doc_id": d.doc_id,
                             "reason_code": REASON_ORPHANED})
        if getattr(d, "tax_year", None) is None:
            blockers.append({"doc_id": d.doc_id,
                             "reason_code": REASON_MISSING_YEAR})

    if chained_years is None:
        chained_years = sorted({d.tax_year for d in docs
                                if getattr(d, "tax_year", None) is not None})
    for y in chained_years:
        for d in store.list(year=y, form="1099-B"):
            if d.doc_id in excluded:
                continue
            lots = _doc_lots(d)
            if not lots:
                blockers.append({"doc_id": d.doc_id,
                                 "reason_code": REASON_ZERO_LOTS})
                continue
            # G2: one entry per doc per code, however many lots trip it.
            if any(lot.get("term") not in ("short", "long") for lot in lots):
                blockers.append({"doc_id": d.doc_id,
                                 "reason_code": REASON_LOT_TERM_UNKNOWN})
            if any(_parse_money_opt(lot.get("proceeds_1d")) is None
                   or _parse_money_opt(lot.get("basis_1e")) is None
                   for lot in lots):
                blockers.append({"doc_id": d.doc_id,
                                 "reason_code": REASON_LOT_MISSING_AMOUNTS})

    blockers.sort(key=lambda b: (b["doc_id"], b["reason_code"]))
    return blockers


def from_store(store: Any, year: int) -> dict:
    """Sum validated 1099-B lots for ``year`` into signed ST/LT currents.

    Refuses loudly (R3 guard) if ANY document in the store is UNKNOWN,
    MULTI_FORM, BLOCKED, or ORPHANED, or has tax_year None, or if any
    1099-B for the year has zero lots, an unknown-term lot
    (``lot_term_unknown``), or a lot missing proceeds/basis
    (``lot_missing_amounts``) -- unless the Operator recorded an
    exclusion with a reason for that document. Excluded documents are
    skipped by both the guard and the sums (the exclusion reason is
    the Operator's disposal); documents with a recorded exclusion are
    never summed. Also refuses if any 1099-B for the year is not yet
    validated (validation is never excludable).

    Every lot in every non-excluded document's lot table is summed (no
    single-lot fallback). Per-lot gain/loss = 1d proceeds - 1e basis +
    1g wash sale loss disallowed. Box 4 (federal income tax withheld)
    is summed separately as ``fed_withheld_4_total`` -- it is a
    withholding credit, never part of gain/loss. Box 1f (accrued
    market discount) is summed separately as
    ``accrued_market_discount_1f_total`` for Phase 4 (Schedule B
    interest income) visibility -- never in gain/loss, never in
    withholding.
    """
    blockers = carryforward_blockers(store, chained_years=[year])
    if blockers:
        items = ", ".join(f"{b['doc_id']}({b['reason_code']})"
                          for b in blockers)
        raise ValueError(
            f"cannot compute carryforward for {year}: "
            f"{len(blockers)} blocker(s): {items} -- resolve each blocker "
            "or record an Operator exclusion with a reason for it "
            "(`taxprep exclude <doc_id> --reason <reason>`), then retry"
        )
    data_dir = getattr(store, "data_dir", None)
    excluded: set[str] = set()
    if data_dir is not None:
        excluded = {e["doc_id"] for e in exclusions.list_exclusions(data_dir)}
    docs = store.list(year=year, form="1099-B")
    unvalidated = [d.doc_id for d in docs if d.status != "validated"]
    if unvalidated:
        raise ValueError(
            f"cannot compute carryforward for {year}: "
            f"{len(unvalidated)} 1099-B document(s) not yet validated: "
            + ", ".join(unvalidated)
            + " -- validate them with `taxprep review` first"
        )
    st = Decimal("0")
    lt = Decimal("0")
    fed_withheld_total = Decimal("0")
    amd_total = Decimal("0")
    included = 0
    for d in docs:
        if d.doc_id in excluded:
            continue  # Operator-disposed: skipped by guard and by sums
        for n, lot in enumerate(_doc_lots(d), start=1):
            label = f"{d.doc_id} lot {n}"
            term = lot.get("term")
            proceeds = _parse_money_opt(lot.get("proceeds_1d"))
            basis = _parse_money_opt(lot.get("basis_1e"))
            wash = _parse_money_opt(lot.get("wash_1g"))
            withheld = _parse_money_opt(lot.get("fed_withheld_4"))
            amd = _parse_money_opt(lot.get("accrued_market_discount_1f"))
            # The R3 guard already refused on unknown terms and missing
            # amounts; these raises are defensive and unreachable --
            # a lot must never be silently dropped or misbucketed.
            if term not in ("short", "long"):
                raise ValueError(
                    f"{label}: term {term!r} unknown -- "
                    "carryforward_blockers should have refused")
            if proceeds is None or basis is None:
                raise ValueError(
                    f"{label}: missing proceeds/basis -- "
                    "carryforward_blockers should have refused")
            gain_loss = proceeds - basis + (wash or Decimal("0"))
            if term == "short":
                st += gain_loss
            else:
                lt += gain_loss
            fed_withheld_total += withheld or Decimal("0")
            amd_total += amd or Decimal("0")
            included += 1
    return {
        "st_current": st,
        "lt_current": lt,
        "fed_withheld_4_total": fed_withheld_total,
        "accrued_market_discount_1f_total": amd_total,
        "warnings": [],
        "lots_included": included,
        "lots_excluded": 0,
    }
