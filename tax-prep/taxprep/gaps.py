"""Gap analysis: what the IRS transcript expects vs what was ingested.

Mechanical and blind-orchestrator safe. Expected forms per year come
from two signals, both metadata-only:

1. WAGE_INCOME_TRANSCRIPT payer blocks: every form type the IRS has on
   file for the year is expected to have a corresponding ingested doc.
2. RETURN_TRANSCRIPT schedule mentions: a "Schedule D" on the filed
   return expects 1099-B support, "Schedule B" expects 1099-INT/DIV,
   "Schedule C" expects 1099-NEC/MISC.

Return value is PII-free: per year {expected_forms, missing_forms,
n_transcript_payers, n_document_payers, transcript_forms} plus a top-
level report_path. Per-payer detail (names -> missing forms) goes ONLY
to the local report file under data/reports/ -- operator's eyes, never
committed, never returned over a tool boundary.
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


def _wage_payers(store, year: int) -> list[dict]:
    """Re-parse WAGE_INCOME_TRANSCRIPT OCR for a year into raw payer dicts.

    Same guards as the reconciliation check: only fully-parsed
    transcripts (no unparsed lines at ingest) in transcribed/validated
    status. Payer dicts carry the RAW names/EINs -- they are used for
    the expected-form computation and the local human report, never for
    an agent-facing return value.
    """
    payers = []
    for d in store.list(year=year, form="WAGE_INCOME_TRANSCRIPT"):
        if d.status not in ("transcribed", "validated"):
            continue
        try:
            text = store.load_ocr(d.doc_id)
        except (FileNotFoundError, OSError):
            continue
        parsed = _transcript.parse_wage_income_transcript(text, tax_year=year)
        if parsed.get("unparsed_lines"):
            continue
        payers.extend(parsed.get("payers", []))
    return payers


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
        payers = _wage_payers(store, y)
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
        }

        # -- per-payer detail: local report only (names live here) ----
        report_sections.append(f"=== {y} ===")
        if not payers:
            report_sections.append("no wage & income transcript parsed for this year")
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
