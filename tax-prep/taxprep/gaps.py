"""Gap analysis: what the IRS transcript expects vs what was ingested.

Mechanical and blind-orchestrator safe. Expected forms per year come
from two signals, both metadata-only:

1. WAGE_INCOME_TRANSCRIPT payer blocks: every form type the IRS has on
   file for the year is expected to have a corresponding ingested doc.
2. RETURN_TRANSCRIPT schedule mentions: a "Schedule D" on the filed
   return expects 1099-B support, "Schedule B" expects 1099-INT/DIV,
   "Schedule C" expects 1099-NEC/MISC.

Return value is PII-free: per year {expected_forms, missing_forms,
n_transcript_payers, n_document_payers, transcript_forms, schedules_seen,
n_docs, has_transcript, n_skipped_transcripts, skipped_transcripts}
plus a top-level report_path. skipped_transcripts lists transcript
docs that exist for the year but could not be used, with a
reason_code -- never silently dropped. Per-payer detail (names ->
missing forms) goes ONLY to the local report file under
data/reports/ -- operator's eyes, never committed, never returned
over a tool boundary.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from . import transcript as _transcript
from .models import FORM_TYPES

# schedule letter -> form types that would support it
_SCHEDULE_FORMS: dict[str, set[str]] = {
    "d": {"1099-B", "SCHEDULE_D"},
    "b": {"1099-INT", "1099-DIV"},
    "c": {"1099-NEC", "1099-MISC"},
}
_SCHEDULE_RE = re.compile(r"schedule\s+([a-z])\b", re.IGNORECASE)

# form types that count as "payer documents" for coverage counts
_PAYER_FORMS = {"W-2", "1099-B", "1099-INT", "1099-DIV", "1099-NEC",
                "1099-R", "1099-MISC"}

# G1: IRS transcript header / notice lines. Realistic transcripts always
# carry these (title, tax-year banner, notice boilerplate, taxpayer
# identity header). They are structural -- represented by form_type /
# tax_year -- not content, so they must not count as unparsed lines and
# must not trigger skipping a transcript. Heuristic and documented as
# such: a line matching here only ever SUPPRESSES a skip, it never adds
# content. (transcript.py keeps its own parallel structural set; this
# module does not touch that file.)
_HEADER_LINE_RES = [
    # title lines: "WAGE AND INCOME TRANSCRIPT", "TAX RETURN TRANSCRIPT",
    # "ACCOUNT TRANSCRIPT", "RECORD OF ACCOUNT"
    re.compile(
        r"^\s*((wage\s+and\s+income|tax\s+return|account)\s+transcript"
        r"|record\s+of\s+account)\b", re.IGNORECASE),
    # "For Tax Year 2024", "Tax Year: 2024", "Tax Period 2024"
    re.compile(r"^\s*(for\s+)?tax\s*(year|period)\s*[:\-]?\s*\d{4}\b",
               re.IGNORECASE),
    # taxpayer identity header: "Taxpayer: ...", "SSN: ..."
    re.compile(r"^\s*(taxpayer(\s+(name|ssn))?|ssn|tin)\s*[:\-]",
               re.IGNORECASE),
    # notice boilerplate
    re.compile(r"^\s*note\s*[:\-]", re.IGNORECASE),
    re.compile(r"^\s*(this|the)\s+(transcript|product|document)\b",
               re.IGNORECASE),
    re.compile(r"^\s*for\s+your\s+(information|records)\b", re.IGNORECASE),
    re.compile(r"^\s*(please|important)\b.*\b(transcript|information)\b",
               re.IGNORECASE),
]


def is_transcript_header_line(line: str) -> bool:
    """True for a known IRS transcript header/notice line (see above).

    Classification only -- never echoes the line anywhere. verify.py
    imports this for the reconciliation path.
    """
    return any(pat.match(line) for pat in _HEADER_LINE_RES)


# transcript form -> parser; ACCOUNT_TRANSCRIPT and RECORD_OF_ACCOUNT
# parsers are the R17 workstream's (absent from transcript.py for now).
_TRANSCRIPT_PARSERS = {
    "WAGE_INCOME_TRANSCRIPT": "parse_wage_income_transcript",
    "RETURN_TRANSCRIPT": "parse_return_transcript",
    "ACCOUNT_TRANSCRIPT": "parse_account_transcript",
    "RECORD_OF_ACCOUNT": "parse_record_of_account",
}

# statuses a transcript may still be parsed under: a "needs_review" doc
# whose only unparsed lines are headers is usable, not skipped.
_USABLE_STATUSES = ("transcribed", "validated", "needs_review")


def parser_for(form_type: str):
    """The transcript.py parser for a transcript form, or None when the
    R17 workstream has not added it yet."""
    parser_name = _TRANSCRIPT_PARSERS.get(form_type)
    return getattr(_transcript, parser_name, None) if parser_name else None


def effective_unparsed_lines(parsed: dict) -> list:
    """Parser-reported unparsed lines minus header/notice lines (G1)."""
    return [line for line in (parsed.get("unparsed_lines") or [])
            if not is_transcript_header_line(line)]


def parse_transcript_doc(doc, store) -> tuple[dict | None, str | None]:
    """Parse one transcript doc's OCR text with its form's parser.

    Returns (parsed, None) when usable, else (None, reason_code) with
    reason_code in {"wrong_status", "ocr_unavailable",
    "parser_unavailable", "still_unusable"}. Header/notice lines (see
    is_transcript_header_line) are excluded from the unusable judgment:
    a transcript whose only unparsed lines are headers is fully usable.
    The returned parsed dict has "unparsed_lines" replaced by the
    effective (post-header-filter) list.
    """
    if doc.status not in _USABLE_STATUSES:
        return None, "wrong_status"
    try:
        text = store.load_ocr(doc.doc_id)
    except (FileNotFoundError, OSError):
        return None, "ocr_unavailable"
    parser = parser_for(doc.form_type)
    if parser is None:
        return None, "parser_unavailable"
    parsed = parser(text, tax_year=doc.tax_year)
    effective = effective_unparsed_lines(parsed)
    if effective:
        return None, "still_unusable"
    parsed = dict(parsed)
    parsed["unparsed_lines"] = effective
    return parsed, None


def _wage_payers(store, year: int) -> tuple[list[dict], list[dict]]:
    """Re-parse WAGE_INCOME_TRANSCRIPT OCR for a year into raw payer dicts.

    Returns (payers, skipped). Skipped entries are {"doc_id",
    "reason_code"} dicts for transcript docs that exist for the year
    but could not be used -- never silently dropped. Payer dicts carry
    the RAW names/EINs -- used for the expected-form computation and
    the local human report, never for an agent-facing return value.
    """
    payers: list[dict] = []
    skipped: list[dict] = []
    for d in store.list(year=year, form="WAGE_INCOME_TRANSCRIPT"):
        parsed, reason = parse_transcript_doc(d, store)
        if reason is not None:
            skipped.append({"doc_id": d.doc_id, "reason_code": reason})
            continue
        payers.extend(parsed.get("payers", []))
    return payers, skipped


def _schedule_forms(store, year: int) -> tuple[set[str], set[str]]:
    """(expected form types, schedule letters seen) from RETURN_TRANSCRIPT OCR.

    Scans the transcript OCR text for schedule mentions. Heuristic and
    documented as such: a mention only ADDS an expectation; it never
    removes one.
    """
    expected: set[str] = set()
    seen: set[str] = set()
    for d in store.list(year=year, form="RETURN_TRANSCRIPT"):
        if d.status not in ("transcribed", "validated"):
            continue
        try:
            text = store.load_ocr(d.doc_id)
        except (FileNotFoundError, OSError):
            continue
        for letter in _SCHEDULE_RE.findall(text):
            letter = letter.lower()
            if letter in _SCHEDULE_FORMS:
                seen.add(letter.upper())
                expected |= _SCHEDULE_FORMS[letter]
    return expected, seen


def analyze_gaps(store, scope_years: list[int],
                 year: int | None = None) -> dict:
    """Per-year gap shapes + local per-payer report path.

    missing_forms = expected form types with zero ingested docs that
    year. Years with no transcript at all report expected_forms=[] (no
    ground truth to compare against) -- never a false "all clear".
    """
    years = [year] if year is not None else sorted(set(scope_years))
    out: dict = {}
    report_sections: list[str] = []

    for y in years:
        payers, skipped = _wage_payers(store, y)
        txn_forms = sorted({(p.get("form_type") or "UNKNOWN").upper()
                            for p in payers
                            if (p.get("form_type") or "UNKNOWN").upper()
                            in FORM_TYPES})
        txn_forms = [f for f in txn_forms if f != "UNKNOWN"]
        sched_forms, sched_seen = _schedule_forms(store, y)
        expected = set(txn_forms) | sched_forms

        docs = store.list(year=y)
        actual = {d.form_type for d in docs}
        missing = sorted(f for f in expected if f not in actual)
        n_doc_payers = sum(1 for d in docs if d.form_type in _PAYER_FORMS)

        out[str(y)] = {
            "expected_forms": sorted(expected),
            "missing_forms": missing,
            "n_transcript_payers": len(payers),
            "n_document_payers": n_doc_payers,
            "transcript_forms": txn_forms,
            "schedules_seen": sorted(sched_seen),
            "n_docs": len(docs),
            "has_transcript": bool(payers),
            # G1: transcripts that exist for the year but could not be
            # used -- reported explicitly, never a silent gap.
            "n_skipped_transcripts": len(skipped),
            "skipped_transcripts": sorted(
                skipped, key=lambda s: s["doc_id"]),
        }

        # -- per-payer detail: local report only (names live here) ----
        report_sections.append(f"=== {y} ===")
        if not payers:
            report_sections.append("no wage & income transcript parsed for this year")
        if skipped:
            report_sections.append(
                "  skipped transcripts (unusable -- needs human): " +
                ", ".join(f"{s['doc_id']}({s['reason_code']})"
                          for s in sorted(skipped,
                                          key=lambda s: s["doc_id"])))
        for p in payers:
            present = (p.get("form_type") or "UNKNOWN").upper() in actual
            report_sections.append(
                f"  payer={p.get('payer') or '?'} ein={p.get('payer_ein') or '?'} "
                f"form={p.get('form_type') or '?'} "
                f"doc_present={'yes' if present else 'NO -- MISSING'}"
            )
        if sched_seen:
            report_sections.append(
                "  return transcript schedules: " + ", ".join(sorted(sched_seen)))
        if missing:
            report_sections.append("  missing forms: " + ", ".join(missing))
        report_sections.append("")

    reports_dir = Path(store.data_dir) / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = reports_dir / f"gaps_{stamp}.txt"
    report_path.write_text(
        "taxprep gap report (operator's eyes only -- per-payer detail)\n"
        f"generated: {datetime.now().isoformat(timespec='seconds')}\n\n"
        + "\n".join(report_sections),
        encoding="utf-8",
    )
    out["report_path"] = str(report_path)
    return out
