"""Ingest: walk an input directory, extract text, classify, extract fields.

R4 identity (stable, content-derived): doc_id = sha256(SOURCE BYTES)[:16]
-- no filename component anywhere (this also fixes the R8 identifier
leak at the source). Split children compose as
<hash>-p<page_range>-<section-hash> (the section hash disambiguates
sections sharing a page range).
Re-ingest is idempotent: validated status/values/edits are never
overwritten; if re-extraction disagrees with validated values the
validated values are kept and the doc is flagged re_review; new text
for the same source attaches to the same doc_id with provenance.
``taxprep sync`` marks documents whose source file is missing ORPHANED.

R5 text-sufficiency gate: per-page deterministic signals (chars per
page, near-full-page image dominance, garble ratio, AcroForm values,
encryption) route each document to native | form-field | OCR
(--skip-text / --redo-ocr / --force-ocr via ocr.ocr_with_escalation)
| BLOCKED-encrypted | ERROR(reason_code). OCR never modifies originals;
its outputs go under <data_dir>/ocr_work.

R6 intake: .pdf / .txt plus images (jpg/jpeg/png/heic/heif/tiff/tif/
bmp -- converted to PDF under <data_dir>/converted, then the R5 path),
all matched case-insensitively. Per-run accounting is returned AND
printed: {files_seen, ingested, skipped:[{file, reason_code}],
errored:[{file, reason_code}]}; reason codes, never exception text.

R8: transcript payer blocks use positional keys (payer1.box1); the
payer name is stored as a payer1.name field VALUE, never in a key.

Required binaries / libraries (no sudo assumed):
  pypdf            hard dependency: page text, image signals, encryption
                   detection, AcroForm get_fields.
  pillow           image -> PDF conversion (R6). If absent, image files
                   are SKIPPED with reason "image-support-missing" (fail
                   closed, never silent). HEIC/HEIF additionally needs
                   pillow_heif registered; without it those files are
                   skipped with "heic-unsupported".
  tesseract | ocrmypdf   OCR engine behind taxprep.ocr (R5). If OCR is
                   required but no engine is available, the document is
                   BLOCKED with reason "needs-ocr" -- never an empty
                   document.
"""

from __future__ import annotations

import hashlib
import os
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from . import extractors, transcript
from .models import Document
from .store import DocumentStore

TRANSCRIPT_FORMS = {"WAGE_INCOME_TRANSCRIPT", "RETURN_TRANSCRIPT"}

# form types with box-level extractors (mirrors extractors' supported set)
BOX_FORMS = {
    "W-2",
    "1099-B",
    "1099-INT",
    "1099-DIV",
    "1099-NEC",
    "1099-R",
    "1099-MISC",
    "1098",
}

# -- R6: intake ---------------------------------------------------------

PDF_EXTS = {".pdf"}
TXT_EXTS = {".txt"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".heif",
              ".tif", ".tiff", ".bmp"}
HEIC_EXTS = {".heic", ".heif"}

# Stable reason codes (never exception text -- R6).
RC_UNSUPPORTED_TYPE = "unsupported-type"
RC_IMAGE_SUPPORT_MISSING = "image-support-missing"
RC_HEIC_UNSUPPORTED = "heic-unsupported"
RC_IMAGE_CONVERT_FAILED = "image-convert-failed"
RC_READ_FAILED = "read-failed"
RC_EXTRACT_FAILED = "extract-failed"
RC_ENCRYPTED = "encrypted"
RC_NEEDS_OCR = "needs-ocr"
RC_OCR_INSUFFICIENT = "ocr-insufficient"

# text_source vocabulary (Document.text_source provenance).
TS_NATIVE = "native"
TS_SIDECAR = "sidecar"
TS_FORM_FIELD = "form-field"
TS_OCR = "ocr"
TS_ERROR = "error"
TS_BLOCKED = "blocked"


class _SkipFile(Exception):
    """Internal: this file is skipped, not ingested. Carries a stable
    reason_code (never exception text)."""

    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


# -- R4: stable identity -------------------------------------------------

DOC_ID_BYTES = 16  # hex chars of the sha256 prefix used as doc_id


def source_doc_id(source_bytes: bytes) -> str:
    """doc_id = sha256 hex of the SOURCE BYTES, prefix. No filename
    component (R4/R8)."""
    return hashlib.sha256(source_bytes).hexdigest()[:DOC_ID_BYTES]


def _slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s or "doc"


def make_doc_id(source_name: str, text: str) -> str:
    """Compatibility shim kept for the R1 split tests.

    ``source_name`` is accepted but IGNORED -- it is not part of the
    digest (R4/R8: identifiers carry no filename component). For .txt
    sources the file bytes are the UTF-8 encoding of ``text``, so this
    equals source_doc_id(file bytes).
    """
    return source_doc_id(text.encode("utf-8"))


# -- R5: text-sufficiency gate --------------------------------------------

# A page with >= this fraction of its area covered by images and <
# _NATIVE_MIN_CHARS text chars is image-dominant -> OCR.
_IMAGE_DOMINANCE_RATIO = 0.75
_NATIVE_MIN_CHARS = 100
# Garble ratio above this -> the text layer is unusable -> OCR
# (redo/force; skip-text would keep the garbage layer).
_GARBLE_THRESHOLD = 0.15
# OCR text below this many chars is not a usable extraction.
_OCR_MIN_CHARS = 40

_NONPRINT = set("\x00\x01\x02\x03\x04\x05\x06\x07\x08\x0b\x0c\x0e\x0f"
                "\x10\x11\x12\x13\x14\x15\x16\x17\x18\x19\x1a\x1b\x1c"
                "\x1d\x1e\x1f\x7f")


def _garble_ratio(text: str) -> float:
    """Fraction of the text that is encoding garbage: non-printable
    chars, U+FFFD replacements, "(cid:NNN)" runs (missing ToUnicode)."""
    if not text:
        return 0.0
    bad = text.count("\ufffd")
    bad += len(re.findall(r"\(cid:\d+\)", text)) * 5
    for ch in text:
        if ch in _NONPRINT or unicodedata.category(ch) in ("Cc", "Cf",
                                                           "Cs", "Co"):
            bad += 1
    return bad / len(text)


def _page_text(page) -> str:
    try:
        return page.extract_text() or ""
    except Exception:
        return ""


def _image_area_ratio(page) -> float:
    """Summed raster-image pixel area / page area. 0.0 when images
    cannot be inspected. Deterministic proxy for full-page-image
    dominance (placement is not parsed -- pixel coverage is the
    conservative signal)."""
    try:
        box = page.mediabox
        page_area = float(box.width * box.height)
        if page_area <= 0:
            return 0.0
        pixels = 0
        for img in page.images:
            try:
                pil = img.image
                pixels += pil.width * pil.height
            except Exception:
                continue
        return pixels / page_area
    except Exception:
        return 0.0


def _page_needs_ocr(page, text: str) -> tuple[bool, str]:
    """(needs_ocr, why) for one PDF page. why is a short signal label."""
    chars = len("".join(text.split()))
    if chars == 0:
        # A truly blank page (no images either) needs no OCR.
        try:
            has_images = len(page.images) > 0
        except Exception:
            has_images = False
        return (True, "image-only") if has_images else (False, "blank")
    if _garble_ratio(text) > _GARBLE_THRESHOLD:
        return True, "garbled"
    if (chars < _NATIVE_MIN_CHARS
            and _image_area_ratio(page) >= _IMAGE_DOMINANCE_RATIO):
        return True, "image-dominant"
    return False, "native"


def _acroform_values(reader) -> dict[str, str]:
    """AcroForm fields holding non-empty values: {name: value}."""
    out: dict[str, str] = {}
    try:
        fields = reader.get_fields() or {}
    except Exception:
        return out
    for name, f in fields.items():
        try:
            v = f.get("/V") if isinstance(f, dict) else f
        except Exception:
            continue
        if isinstance(v, str) and v.strip():
            out[str(name)] = v.strip()
    return out


@dataclass
class PageBundle:
    """Per-page text plus the R5 routing decision and provenance."""
    pages: list[str]
    route: str  # native | form-field | ocr | blocked | error
    text_source: str
    reason_code: str | None = None
    ocr_engine: str | None = None
    engine_version: str | None = None
    ocr_mode: str | None = None
    attempts: list = field(default_factory=list)
    mean_confidence: float | None = None


def _ocr_pdf(pdf_path: Path, mode: str, work_dir: Path) -> dict:
    """Hook point: whole-PDF OCR (taxprep.ocr.ocr_pdf). Monkeypatched in
    tests to avoid needing a real engine."""
    from . import ocr as _ocr

    return _ocr.ocr_pdf(pdf_path, mode, work_dir)


def _ocr_escalate(pdf_path: Path, work_dir: Path, modes: list[str]) -> dict:
    """Hook point: ocr_with_escalation (try modes, keep best, record
    attempts)."""
    from . import ocr as _ocr

    return _ocr.ocr_with_escalation(pdf_path, work_dir, modes)


def _ocr_text_usable(text: str) -> bool:
    """Deterministic quality bar for an OCR result: enough chars AND
    (a tax year or a classified form) -- otherwise escalate."""
    t = text.strip()
    if len(t) < _OCR_MIN_CHARS:
        return False
    return (extractors.detect_tax_year(t) is not None
            or extractors.classify_form(t) != "UNKNOWN")


def _ocr_page(page_pdf: Path, work_dir: Path, garbled: bool) -> dict:
    """OCR one single-page PDF with measure-then-escalate.

    First mode: "redo-ocr" for a garbled text layer (skip-text would
    keep the garbage), else "skip-text". If the result is not usable,
    escalate through the remaining modes via ocr_with_escalation (best
    kept, every attempt recorded).
    """
    modes = (["redo-ocr", "force-ocr"] if garbled
             else ["skip-text", "redo-ocr", "force-ocr"])
    first = _ocr_pdf(page_pdf, modes[0], work_dir)
    attempts = list(first.get("attempts", []))
    best = first
    if not first.get("ok") or not _ocr_text_usable(first.get("text", "")):
        if len(modes) > 1:
            esc = _ocr_escalate(page_pdf, work_dir, modes[1:])
            attempts.extend(esc.get("attempts", []))
            # keep the best by extracted chars (ties: earlier mode wins)
            if esc.get("ok") and len(esc.get("text", "")) > len(
                    best.get("text", "")):
                best = esc
    out = dict(best)
    out["attempts"] = attempts
    return out


def _pdf_page_bundle(pdf_path: Path, store: DocumentStore) -> PageBundle:
    """Run the R5 gate over one PDF: per-page signals, then native |
    form-field | OCR | BLOCKED-encrypted | ERROR."""
    from pypdf import PdfReader, PdfWriter

    try:
        reader = PdfReader(str(pdf_path))
    except Exception:
        return PageBundle([], "error", TS_ERROR,
                           reason_code=RC_EXTRACT_FAILED)

    try:
        encrypted = bool(reader.is_encrypted)
    except Exception:
        encrypted = False
    if encrypted:
        # BLOCKED-encrypted: the Operator decrypts; passwords are
        # never handled here. (Checked before touching pages: pypdf
        # raises FileNotDecryptedError on page access.)
        return PageBundle([], "blocked", TS_BLOCKED,
                           reason_code=RC_ENCRYPTED)

    try:
        n_pages = len(reader.pages)
    except Exception:
        return PageBundle([], "error", TS_ERROR,
                           reason_code=RC_EXTRACT_FAILED)
    _ = n_pages

    form_values = _acroform_values(reader)

    page_texts: list[str] = []
    ocr_pages: list[int] = []       # 1-based pages needing OCR
    ocr_garbled: dict[int, bool] = {}
    try:
        for i, page in enumerate(reader.pages, start=1):
            text = _page_text(page)
            needs, _why = _page_needs_ocr(page, text)
            if needs:
                ocr_pages.append(i)
                ocr_garbled[i] = _garble_ratio(text) > _GARBLE_THRESHOLD
                page_texts.append("")  # placeholder; filled after OCR
            else:
                page_texts.append(text)
    except Exception:
        return PageBundle([], "error", TS_ERROR,
                           reason_code=RC_EXTRACT_FAILED)

    if form_values and not ocr_pages:
        # Fillable form with values and no OCR-worthy pages: supplement
        # the native text with the field values (the values ARE data).
        native = "\n".join(page_texts)
        form_lines = "\n".join(f"{k}: {v}"
                               for k, v in sorted(form_values.items()))
        return PageBundle([native + "\n" + form_lines] if native.strip()
                          else [form_lines],
                          "form-field", TS_FORM_FIELD)

    attempts: list = []
    engine = engine_version = None
    confidences: list[float] = []
    if ocr_pages:
        from . import ocr as _ocr

        if not _ocr.available():
            # BLOCKED-needs-ocr: never an empty document.
            return PageBundle([], "blocked", TS_BLOCKED,
                               reason_code=RC_NEEDS_OCR)
        work_dir = store.data_dir / "ocr_work"
        work_dir.mkdir(parents=True, exist_ok=True)
        for i in ocr_pages:
            single = work_dir / f"page-{os.getpid()}-{i}.pdf"
            try:
                writer = PdfWriter()
                writer.add_page(reader.pages[i - 1])
                with open(single, "wb") as fh:
                    writer.write(fh)
                result = _ocr_page(single, work_dir, ocr_garbled[i])
            except Exception:
                return PageBundle([], "error", TS_ERROR,
                                   reason_code=RC_EXTRACT_FAILED)
            finally:
                try:
                    single.unlink()
                except OSError:
                    pass
            attempts.extend(result.get("attempts", []))
            engine = result.get("engine")
            engine_version = result.get("engine_version")
            if result.get("mean_confidence") is not None:
                confidences.append(result["mean_confidence"])
            page_texts[i - 1] = result.get("text", "") if result.get(
                "ok") else ""

    full = "\n".join(page_texts)
    if ocr_pages and not full.strip():
        return PageBundle(page_texts, "blocked", TS_BLOCKED,
                           reason_code=RC_OCR_INSUFFICIENT,
                           ocr_engine=engine, engine_version=engine_version,
                           attempts=attempts)

    route = "ocr" if ocr_pages else ("form-field" if form_values
                                    else "native")
    text_source = TS_OCR if ocr_pages else (TS_FORM_FIELD if form_values
                                            else TS_NATIVE)
    # If AcroForm values exist alongside OCR'd pages, append them so the
    # field data is not lost.
    if form_values and ocr_pages:
        form_lines = "\n".join(f"{k}: {v}"
                               for k, v in sorted(form_values.items()))
        page_texts = list(page_texts)
        page_texts[-1] = page_texts[-1] + "\n" + form_lines
    return PageBundle(
        page_texts, route, text_source,
        ocr_engine=engine, engine_version=engine_version,
        ocr_mode=(attempts[-1].get("mode") if attempts else None),
        attempts=attempts,
        mean_confidence=(sum(confidences) / len(confidences)
                         if confidences else None),
    )


# -- R6: image intake -------------------------------------------------------

def _pil_image():
    """PIL.Image, or None when pillow is unavailable (fail closed)."""
    try:
        from PIL import Image  # type: ignore

        return Image
    except Exception:
        return None


def _heif_supported() -> bool:
    Image = _pil_image()
    if Image is None:
        return False
    try:
        return ".heic" in Image.registered_extensions()
    except Exception:
        return False


def _image_to_pdf(path: Path, source_sha: str, store: DocumentStore) -> Path:
    """Convert an image to a single-page PDF under <data_dir>/converted/
    (content-derived name; the original is never modified)."""
    Image = _pil_image()
    if Image is None:  # pragma: no cover -- guarded by caller
        raise _SkipFile(RC_IMAGE_SUPPORT_MISSING)
    converted = store.data_dir / "converted"
    converted.mkdir(parents=True, exist_ok=True)
    out = converted / f"img_{source_sha}.pdf"
    if not out.exists():
        with Image.open(path) as img:
            img.convert("RGB").save(str(out), "PDF", resolution=150.0)
    return out


def extract_pdf_pages(path: Path) -> list[str]:
    """Per-page text from a PDF with pypdf; pdfplumber fallback per page."""
    pages: list[str] = []
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        pages = [_page_text(p) for p in reader.pages]
    except Exception:
        pages = []
    if not any(p.strip() for p in pages):
        try:
            import pdfplumber  # type: ignore

            with pdfplumber.open(str(path)) as pdf:
                pages = [page.extract_text() or "" for page in pdf.pages]
        except Exception:
            pass
    return pages


def extract_pdf_text(path: Path) -> str:
    """Whole-document text from a PDF (pages joined). Kept for compatibility."""
    return "\n".join(extract_pdf_pages(path))


def _fields_from_transcript(form_type: str, text: str,
                            year: int | None) -> tuple[dict, str]:
    """Adapt transcript parser output to the Document fields shape.

    R8: positional payer keys (payer1.box1); the payer name is stored as
    a payer1.name field VALUE, never embedded in a key.
    """
    if form_type == "WAGE_INCOME_TRANSCRIPT":
        parsed = transcript.parse_wage_income_transcript(text, tax_year=year)
        fields: dict = {}
        for i, payer in enumerate(parsed.get("payers", [])):
            prefix = f"payer{i + 1}"
            fields[f"{prefix}.name"] = {
                "value": payer.get("payer", "unknown"),
                "confidence": "high",
                "raw_text": "",
            }
            for box, val in payer.get("boxes", {}).items():
                code = f"{prefix}.{box}"
                fields[code] = {
                    "value": val,
                    "confidence": "high",
                    "raw_text": f"{payer.get('form_type', '')} box {box}",
                }
        unparsed = parsed.get("unparsed_lines", [])
    else:
        parsed = transcript.parse_return_transcript(text, tax_year=year)
        fields = {
            label: {"value": val, "confidence": "high", "raw_text": ""}
            for label, val in parsed.get("lines", {}).items()
        }
        for t in parsed.get("transactions", []):
            code = f"tc_{t.get('code')}"
            fields[code] = {
                "value": t.get("amount"),
                "confidence": "medium",
                "raw_text": t.get("description", ""),
            }
        unparsed = parsed.get("unparsed_lines", [])
    if unparsed:
        fields["_unparsed_lines"] = {
            "value": unparsed,
            "confidence": "low",
            "raw_text": "",
        }
    status = "transcribed" if not unparsed else "needs_review"
    return fields, status


def _page_range_str(section: extractors.FormSection) -> str:
    if section.page_start == section.page_end:
        return str(section.page_start)
    return f"{section.page_start}-{section.page_end}"


def _extract_for_type(
    form_type: str, text: str, year: int | None
) -> tuple[dict, str]:
    """Route section text to the right extractor (legacy routing)."""
    if form_type in TRANSCRIPT_FORMS:
        return _fields_from_transcript(form_type, text, year)
    if form_type in BOX_FORMS:
        return extractors.extract_fields(form_type, text)
    return {}, "needs_review"


def _section_year(section: extractors.FormSection, full_text: str) -> int | None:
    """Tax year from the section text, falling back to the whole file."""
    year = extractors.detect_tax_year(section.text)
    if year is None:
        year = extractors.detect_tax_year(full_text)
    return year


def _apply_provenance(doc: Document, bundle: PageBundle,
                      source_sha: str) -> None:
    doc.source_sha256 = source_sha
    doc.text_source = bundle.text_source
    doc.reason_code = bundle.reason_code
    doc.ocr_engine = bundle.ocr_engine
    doc.engine_version = bundle.engine_version
    doc.ocr_mode = bundle.ocr_mode
    doc.attempts = list(bundle.attempts)
    doc.mean_confidence = bundle.mean_confidence


def _canon_value(v):
    """Canonical form for comparing extracted values across re-ingests.

    Numeric values compare by value, not by representation: an
    Operator correction stored as the Decimal-safe string "10000.00"
    agrees with an extracted float 10000.0. Non-numeric values compare
    as strings; containers recurse.
    """
    from decimal import Decimal, InvalidOperation

    if isinstance(v, bool):
        return ("bool", v)
    if isinstance(v, (int, float, Decimal)):
        try:
            return ("num", str(Decimal(str(v)).normalize()))
        except InvalidOperation:
            pass
    if isinstance(v, str):
        s = v.strip().replace("$", "").replace(",", "")
        if s:
            try:
                return ("num", str(Decimal(s).normalize()))
            except InvalidOperation:
                pass
        return ("str", v)
    if isinstance(v, (list, tuple)):
        return ("list", tuple(_canon_value(x) for x in v))
    if isinstance(v, dict):
        return ("dict", tuple(sorted((str(k), _canon_value(x))
                                     for k, x in v.items())))
    return ("str", str(v))


def _fields_agree(old: dict, new: dict) -> bool:
    """True when two field dicts carry the same canonical values."""
    if set(old) != set(new):
        return False
    for code in old:
        o, n = old[code], new[code]
        ov = o.get("value") if isinstance(o, dict) else o
        nv = n.get("value") if isinstance(n, dict) else n
        if _canon_value(ov) != _canon_value(nv):
            return False
    return True


def _store_idempotent(store: DocumentStore, doc: Document, text: str,
                      bundle: PageBundle, source_sha: str) -> Document:
    """R4 non-destructive re-ingest.

    - unknown doc_id -> store fresh (possibly a BLOCKED/ERROR record).
    - re-extraction refused or failed (blocked/error route) on an
      existing doc -> keep existing text/fields/status; record the new
      provenance only. A failed re-ingest never destroys what we have.
      (Unvalidated docs do move to BLOCKED -- the file honestly is
      blocked now; validated status is never overwritten.)
    - validated doc + agreeing re-extraction -> refresh text/provenance
      only; validated status/values/edits untouched.
    - validated doc + disagreeing re-extraction -> keep validated
      values, flag re_review (status stays validated).
    - unvalidated doc + successful re-extraction -> fresh extraction
      wins (same doc_id).
    """
    existing = store.get(doc.doc_id)
    if existing is None:
        doc.ocr_text_ref = store.save_ocr(doc.doc_id, text)
        _apply_provenance(doc, bundle, source_sha)
        store.upsert(doc)
        return doc
    if bundle.route in ("blocked", "error"):
        existing.source_path = doc.source_path
        _apply_provenance(existing, bundle, source_sha)
        if existing.status != "validated" and bundle.route == "blocked":
            existing.status = "BLOCKED"
            existing.status_reason = bundle.reason_code
        store.upsert(existing)
        return existing
    if existing.status == "validated":
        if not _fields_agree(existing.fields, doc.fields):
            existing.re_review = True
            existing.status_reason = "extraction-disagrees"
        existing.source_path = doc.source_path
        existing.ocr_text_ref = store.save_ocr(existing.doc_id, text)
        _apply_provenance(existing, bundle, source_sha)
        store.upsert(existing)
        return existing
    # Not validated: the fresh extraction replaces fields/status/text,
    # keeping the stable doc_id (and clearing any stale re_review flag).
    doc.re_review = False
    doc.ocr_text_ref = store.save_ocr(doc.doc_id, text)
    _apply_provenance(doc, bundle, source_sha)
    store.upsert(doc)
    return doc


def _child_document(
    path: Path,
    section: extractors.FormSection,
    parent_doc_id: str,
    full_text: str,
    store: DocumentStore,
    *,
    bundle: PageBundle | None = None,
    source_sha: str | None = None,
) -> Document:
    """One Document for a single form section of a multi-form file.

    R4: child id = <source-bytes-hash>-p<page_range>.
    """
    assert section.form_type is not None
    year = _section_year(section, full_text)
    fields, status = _extract_for_type(section.form_type, section.text, year)
    # R4: <source-bytes-hash>-p<page_range>-<section-hash>. The section
    # hash keeps children unique when two sections share a page range
    # (e.g. a single-page .txt holding two forms); the mandated
    # <bytes-hash>-p<page_range> shape is the prefix.
    section_hash = hashlib.sha256(
        section.text.encode("utf-8")).hexdigest()[:8]
    doc_id = f"{parent_doc_id}-p{_page_range_str(section)}-{section_hash}"
    doc = Document(
        doc_id=doc_id,
        tax_year=year,
        form_type=section.form_type,
        source_path=str(path),
        ocr_text_ref="",
        fields=fields,
        status=status,
        page_range=_page_range_str(section),
        parent_doc_id=parent_doc_id,
    )
    if bundle is not None and source_sha is not None:
        return _store_idempotent(store, doc, section.text, bundle,
                                 source_sha)
    # Legacy direct call (R1 tests): plain upsert, no provenance.
    doc.ocr_text_ref = store.save_ocr(doc_id, section.text)
    store.upsert(doc)
    return doc


def _blocked_document(path: Path, doc_id: str, bundle: PageBundle,
                      source_sha: str, store: DocumentStore,
                      form_type: str = "UNKNOWN") -> Document:
    """A BLOCKED or ERROR document: honest about the failure, with a
    reason code -- never exception text, never an empty silent record."""
    status = "BLOCKED" if bundle.route == "blocked" else "needs_review"
    doc = Document(
        doc_id=doc_id,
        tax_year=None,
        form_type=form_type,
        source_path=str(path),
        ocr_text_ref="",
        fields={},
        status=status,
        status_reason=bundle.reason_code,
    )
    return _store_idempotent(store, doc, "", bundle, source_sha)


def _blocked_multi_form_document(
    path: Path, parent_doc_id: str, text: str, store: DocumentStore,
    *,
    bundle: PageBundle | None = None,
    source_sha: str | None = None,
) -> Document:
    """A multi-form file whose sections carry no content beyond bare title
    mentions cannot be split honestly: block it as one MULTI_FORM Document.

    form_type stays UNKNOWN — a multi-form file is never collapsed into a
    single form_type.
    """
    year = extractors.detect_tax_year(text)
    doc = Document(
        doc_id=parent_doc_id,
        tax_year=year,
        form_type="UNKNOWN",
        source_path=str(path),
        ocr_text_ref="",
        fields={},
        status="MULTI_FORM",
    )
    if bundle is not None and source_sha is not None:
        return _store_idempotent(store, doc, text, bundle, source_sha)
    doc.ocr_text_ref = store.save_ocr(parent_doc_id, text)
    store.upsert(doc)
    return doc


def _build_documents(path: Path, doc_id: str, bundle: PageBundle,
                     source_sha: str, store: DocumentStore) -> list[Document]:
    """Split gated pages into form sections and build Documents."""
    pages = bundle.pages
    text = "\n".join(pages)

    sections = extractors.split_form_sections(pages)
    typed = [s for s in sections if not s.excluded and s.form_type]
    distinct = list(dict.fromkeys(s.form_type for s in typed))

    if len(distinct) >= 2:
        if all(
            extractors.section_has_content(s.text, s.form_type)  # type: ignore[arg-type]
            for s in typed
        ):
            return [
                _child_document(path, s, doc_id, text, store,
                                bundle=bundle, source_sha=source_sha)
                for s in typed
            ]
        return [_blocked_multi_form_document(path, doc_id, text, store,
                                             bundle=bundle,
                                             source_sha=source_sha)]

    # Single-form (or unclassifiable) file: one Document, as before.
    form_type = distinct[0] if distinct else "UNKNOWN"
    section_text = typed[0].text if typed else text
    year = extractors.detect_tax_year(section_text)
    if year is None:
        year = extractors.detect_tax_year(text)
    fields, status = _extract_for_type(form_type, section_text, year)

    doc = Document(
        doc_id=doc_id,
        tax_year=year,
        form_type=form_type,
        source_path=str(path),
        ocr_text_ref="",
        fields=fields,
        status=status,
    )
    return [_store_idempotent(store, doc, section_text, bundle, source_sha)]


def _ingest_pdf(path: Path, source_bytes: bytes,
                store: DocumentStore) -> list[Document]:
    """Ingest one PDF file through the R5 gate."""
    doc_id = source_doc_id(source_bytes)
    source_sha = hashlib.sha256(source_bytes).hexdigest()
    bundle = _pdf_page_bundle(path, store)
    if bundle.route in ("blocked", "error"):
        return [_blocked_document(path, doc_id, bundle, source_sha, store)]
    return _build_documents(path, doc_id, bundle, source_sha, store)


def _ingest_txt(path: Path, source_bytes: bytes,
                store: DocumentStore) -> list[Document]:
    """Ingest one .txt file (a sidecar already claimed by a PDF/image is
    never passed here -- see ingest_dir)."""
    doc_id = source_doc_id(source_bytes)
    source_sha = hashlib.sha256(source_bytes).hexdigest()
    # A same-basename .txt next to nothing is a standalone text file.
    text = source_bytes.decode("utf-8", errors="replace")
    bundle = PageBundle([text], "native", TS_NATIVE)
    return _build_documents(path, doc_id, bundle, source_sha, store)


def _ingest_image(path: Path, source_bytes: bytes,
                  store: DocumentStore) -> list[Document]:
    """Ingest one image: convert to PDF under the data dir, then the R5
    path on the converted PDF. doc_id still derives from the ORIGINAL
    image bytes (R4)."""
    suffix = path.suffix.lower()
    if _pil_image() is None:
        raise _SkipFile(RC_IMAGE_SUPPORT_MISSING)
    if suffix in HEIC_EXTS and not _heif_supported():
        raise _SkipFile(RC_HEIC_UNSUPPORTED)
    doc_id = source_doc_id(source_bytes)
    source_sha = hashlib.sha256(source_bytes).hexdigest()
    try:
        pdf_path = _image_to_pdf(path, source_sha, store)
    except _SkipFile:
        raise
    except Exception:
        raise _SkipFile(RC_IMAGE_CONVERT_FAILED)
    bundle = _pdf_page_bundle(pdf_path, store)
    if bundle.route in ("blocked", "error"):
        return [_blocked_document(path, doc_id, bundle, source_sha, store)]
    return _build_documents(path, doc_id, bundle, source_sha, store)


def _sidecar_for(path: Path) -> Path | None:
    """A same-basename .txt/.TXT sidecar wins as the OCR text (it is the
    pre-existing OCR). Case-insensitive (R6)."""
    for ext in (".txt", ".TXT"):
        cand = path.parent / (path.stem + ext)
        if cand.is_file() and cand.resolve() != path.resolve():
            return cand
    return None


def ingest_file(path: Path, store: DocumentStore) -> list[Document]:
    """Ingest one file; returns the Document(s) created.

    Usually one Document per file. A file holding several form sections
    (consolidated broker 1099, stacked scan) yields one Document per
    section, each with page_range / parent_doc_id; a file whose sections
    cannot be separated honestly yields one MULTI_FORM-blocked Document.

    R4: doc_id derives from the source bytes; re-ingest is idempotent
    and never overwrites validated values (disagreement flags
    re_review). R5: PDFs go through the text-sufficiency gate.
    Raises _SkipFile for skipped files (R6 accounting); other
    exceptions propagate to ingest_dir's errored accounting.
    """
    path = Path(path)
    suffix = path.suffix.lower()
    try:
        source_bytes = path.read_bytes()
    except OSError:
        raise _SkipFile(RC_READ_FAILED)

    # A same-basename .txt sidecar wins as the OCR text for PDFs and
    # converted images (pre-existing OCR). The doc_id still derives
    # from the source file's bytes, so the sidecar text attaches to the
    # same doc_id with provenance text_source="sidecar" (R4).
    if suffix in PDF_EXTS | IMAGE_EXTS:
        sidecar = _sidecar_for(path)
        if sidecar is not None:
            doc_id = source_doc_id(source_bytes)
            source_sha = hashlib.sha256(source_bytes).hexdigest()
            text = sidecar.read_bytes().decode("utf-8", errors="replace")
            bundle = PageBundle([text], "native", TS_SIDECAR)
            return _build_documents(path, doc_id, bundle, source_sha,
                                    store)

    if suffix in PDF_EXTS:
        return _ingest_pdf(path, source_bytes, store)
    if suffix in TXT_EXTS:
        return _ingest_txt(path, source_bytes, store)
    if suffix in IMAGE_EXTS:
        return _ingest_image(path, source_bytes, store)
    raise _SkipFile(RC_UNSUPPORTED_TYPE)


# -- R6: directory walk + accounting ----------------------------------------

@dataclass
class IngestReport:
    """Per-run accounting (R6). ``docs`` holds every Document created;
    split children count under their source file in the file counters."""

    docs: list[Document] = field(default_factory=list)
    files_seen: int = 0
    ingested: int = 0            # files that produced document(s)
    skipped: list[dict] = field(default_factory=list)  # [{file, reason_code}]
    errored: list[dict] = field(default_factory=list)  # [{file, reason_code}]
    seen_paths: list[str] = field(default_factory=list)  # for sync()

    def __len__(self) -> int:  # backward compat: len(report) == n docs
        return len(self.docs)

    def __iter__(self):
        return iter(self.docs)

    def summary(self) -> dict:
        return {
            "files_seen": self.files_seen,
            "ingested": self.ingested,
            "skipped": list(self.skipped),
            "errored": list(self.errored),
            "n_documents": len(self.docs),
        }


def _candidate_files(root: Path,
                   store: DocumentStore) -> tuple[list[Path], set[Path]]:
    """All regular files under root (sorted), minus dotfiles and minus
    anything inside the store's own data dir (ingest must never ingest
    its converted/ocr_work artifacts), plus the set of .txt sidecars
    claimed by a PDF/image source (never ingested standalone)."""
    data_dir = store.data_dir.resolve()
    files = sorted(
        (p for p in root.rglob("*")
         if p.is_file()
         and not p.name.startswith(".")
         and data_dir not in p.resolve().parents),
        key=lambda p: str(p).lower(),
    )
    claimed: set[Path] = set()
    for p in files:
        if p.suffix.lower() in PDF_EXTS | IMAGE_EXTS:
            for ext in (".txt", ".TXT"):
                cand = p.parent / (p.stem + ext)
                if cand.is_file():
                    claimed.add(cand)
    return [p for p in files if p not in claimed], claimed


def _rel(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return path.name


def ingest_dir(input_dir: str | Path, store: DocumentStore) -> IngestReport:
    """Walk input_dir; ingest PDFs, text files, and images.

    Extensions match case-insensitively (R6): *.PDF and photos are no
    longer dropped silently. Returns an IngestReport with per-run
    accounting (reason codes, never exception text). Split children
    count under their source file. One bad file never stops the batch.
    """
    root = Path(input_dir)
    if not root.is_dir():
        raise ValueError(f"not a directory: {input_dir}")

    report = IngestReport()
    files, _claimed = _candidate_files(root, store)
    for path in files:
        report.files_seen += 1
        report.seen_paths.append(str(path))
        try:
            docs = ingest_file(path, store)
        except _SkipFile as skip:
            report.skipped.append({"file": _rel(root, path),
                                   "reason_code": skip.reason_code})
            continue
        except Exception:
            # Reason code, never exception text (R6). The failure is
            # still recorded as a document so nothing is silent.
            reason = RC_EXTRACT_FAILED
            report.errored.append({"file": _rel(root, path),
                                   "reason_code": reason})
            try:
                source_bytes = path.read_bytes()
                doc_id = source_doc_id(source_bytes)
                source_sha = hashlib.sha256(source_bytes).hexdigest()
            except OSError:
                doc_id = source_doc_id(
                    f"unreadable:{path}".encode("utf-8"))
                source_sha = hashlib.sha256(
                    f"unreadable:{path}".encode("utf-8")).hexdigest()
            bundle = PageBundle([], "error", TS_ERROR,
                                 reason_code=reason)
            docs = [_blocked_document(path, doc_id, bundle, source_sha,
                                      store)]
        report.ingested += 1
        report.docs.extend(docs)
    return report


# -- R4: sync -----------------------------------------------------------------

def sync(input_dir: str | Path, store: DocumentStore) -> dict:
    """Reconcile the store with a source directory.

    Walks input_dir (idempotent ingest: new files ingested, existing
    re-ingested without clobbering validated values), then marks every
    document whose source file is missing as ORPHANED (status +
    status_reason "source-missing"). Returns the ingest accounting plus
    the orphaned doc_ids.
    """
    root = Path(input_dir)
    report = ingest_dir(root, store)
    seen_ids = {d.doc_id for d in report.docs}
    seen_paths = {str(Path(p).resolve()) for p in report.seen_paths}

    def _source_present(doc: Document) -> bool:
        sp = doc.source_path
        if not sp:
            return True  # no source recorded: nothing to orphan on
        p = Path(sp)
        if not p.is_absolute():
            p = root / p
        if str(p.resolve()) in seen_paths:
            return True
        return p.exists()

    orphaned: list[str] = []
    for doc in store.list():
        if doc.doc_id in seen_ids:
            continue
        if doc.status == "ORPHANED":
            continue
        if not _source_present(doc):
            doc.status = "ORPHANED"
            doc.status_reason = "source-missing"
            store.upsert(doc)
            orphaned.append(doc.doc_id)

    out = report.summary()
    out["orphaned"] = sorted(orphaned)
    return out
