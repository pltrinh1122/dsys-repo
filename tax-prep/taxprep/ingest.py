"""Ingest: walk an input directory, extract text, classify, extract fields.

Medallion flow (Arc B, contract section 8):

1. read bytes -> sha256 (source identity = sha256 of the SOURCE BYTES,
   I1; no filename component anywhere -- this also fixes the R8
   identifier leak at the source).
2. Derivation-cache check: a silver derivation already at
   (EXTRACTOR_VERSION, config_hash) for this bronze is an I2 no-op --
   only bronze/alias ``last_seen`` is bumped; no new rows, decisions
   untouched.
3. Else build the R5 PageBundle, then register the bronze
   (``register_bronze`` first so the first insert carries
   encryption/source_root -- re-register never clobbers -- then
   ``store_bronze_bytes`` + ``add_alias``).
4. Derive in ONE transaction (I7): classify -> R1 split -> extract ->
   ``upsert_silver_doc`` + ``replace_artifacts`` (silver.derive_artifacts)
   + per-page text fingerprinting, with I6 re-derivation semantics on a
   version/config bump (validated values win; vanished validated fields
   drop + orphan-flag their decisions; ``re_review`` flagged).
5. ``duplicates.assess_new_bronze`` hook, then
   ``duplicates.assess_silver_doc`` per doc (W3; lazy import, hook
   failures are recorded on the report and never fail the ingest).

R4 identity (stable, content-derived): doc_id = sha256(SOURCE BYTES)[:16].
Split children compose as <hash>-p<page_range>-<section-hash> (the
section hash disambiguates sections sharing a page range).
Re-ingest is idempotent: validated status/values/edits are never
overwritten; a version bump that disagrees with validated values keeps
them and moves the doc to ``rereview`` via the R13 lifecycle
(taxprep/lifecycle.py); new text for the same source attaches to the
same doc_id with provenance. Every status change in this module goes
through ``lifecycle.transition()`` -- there are no direct ``.status``
writes.
``taxprep sync`` marks bronze objects with zero on-disk alias paths as
ORPHANED (their silver docs flip to ORPHANED, values preserved).

R5 text-sufficiency gate: per-page deterministic signals (chars per
page, near-full-page image dominance, garble ratio, AcroForm values,
encryption) route each document to native | form-field | OCR
(--skip-text / --redo-ocr / --force-ocr via ocr.ocr_with_escalation)
| BLOCKED-encrypted | ERROR(reason_code). Owner-password-only PDFs (empty
user password) try the empty password first and proceed with
encryption="owner-only" provenance; only a required USER password is
BLOCKED-encrypted for the Operator to decrypt. OCR never modifies originals;
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

from . import extractors, lifecycle, silver, transcript
from .models import Document
from .provenance import (GeometryResolver, attach_field_provenance,
                         page_spans_for_joined)
from .store import DocumentStore

# R17: ACCOUNT_TRANSCRIPT + RECORD_OF_ACCOUNT have parsers in
# transcript.py and branches in _fields_from_transcript.
TRANSCRIPT_FORMS = {
    "WAGE_INCOME_TRANSCRIPT",
    "RETURN_TRANSCRIPT",
    "ACCOUNT_TRANSCRIPT",
    "RECORD_OF_ACCOUNT",
}

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
#
# R15: the value names WHICH text was actually used --
#   native                  text layer of the source file
#   sidecar:<relpath>       a same-basename .txt sidecar (P1: the record
#                           must name the .txt, not just the PDF)
#   form-field              AcroForm widget values (+ native text)
#   ocr:<engine>/<mode>     OCR text, e.g. "ocr:tesseract/redo-ocr"
#   broker-csv              broker CSV rows (brokercsv.py)
#   error | blocked         no usable text
TS_NATIVE = "native"
TS_SIDECAR_PREFIX = "sidecar:"
TS_FORM_FIELD = "form-field"
TS_OCR_PREFIX = "ocr:"
TS_ERROR = "error"
TS_BLOCKED = "blocked"


def _sidecar_text_source(relpath: str) -> str:
    """text_source for sidecar-routed text (R15/P1)."""
    return f"{TS_SIDECAR_PREFIX}{relpath}"


def _ocr_text_source(engine: str | None, mode: str | None) -> str:
    """text_source for OCR-routed text (R15)."""
    if engine and mode:
        return f"{TS_OCR_PREFIX}{engine}/{mode}"
    return "ocr"


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


def _acroform_rects(reader) -> dict:
    """AcroForm widget rects: {name: {"page", "bbox", "line"}} (R15).

    ``page`` is 0-based, ``bbox`` is [x0, y0, x1, y1] in PDF points
    (bottom-left origin), and ``line`` is the "name: value" text the
    form-field route appends to the page text -- the geometry resolver
    matches a field's raw_text against it. Best effort: pages or
    annotations that cannot be read are skipped, never fatal.
    """
    out: dict = {}
    try:
        pages = list(reader.pages)
    except Exception:
        return out
    for i, page in enumerate(pages):
        try:
            annots = page.get("/Annots") or []
        except Exception:
            continue
        for annot in annots:
            try:
                obj = annot.get_object()
            except Exception:
                continue
            try:
                if str(obj.get("/Subtype")) != "/Widget":
                    continue
                name = obj.get("/T")
                rect = obj.get("/Rect")
                if name is None or rect is None:
                    continue
                x0, y0, x1, y1 = (float(v) for v in rect)
                # Widget rects are already bottom-left origin in PDF.
                bbox = [round(min(x0, x1), 2), round(min(y0, y1), 2),
                        round(max(x0, x1), 2), round(max(y0, y1), 2)]
                out[str(name)] = {"page": i, "bbox": bbox}
            except Exception:
                continue
    # The caller fills each entry's "line" ("name: value" as appended to
    # the page text) once the widget values are known.
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
    # X1: "owner-only" when the PDF carried only an owner password (empty
    # user password unlocked it); None otherwise. Operational metadata.
    encryption: str | None = None
    # R15 geometry inputs (all optional; None = source unavailable):
    # - pdf_path: the PDF the native/form-field text was read from, for
    #   pdfplumber word boxes (None for sidecar/txt/image sources).
    # - ocr_words: {page_0based: [word, ...]} tesseract TSV word boxes
    #   (None on the ocrmypdf path -- its sidecar carries no word boxes).
    # - acroform_rects: {field_name: {"page": p0, "bbox": [...],
    #   "line": "name: value"}} widget rects for the form-field route.
    pdf_path: Path | None = None
    ocr_words: dict | None = None
    acroform_rects: dict | None = None


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


def _pages_readable(reader) -> bool:
    """True when the reader's pages yield text without raising.

    Used after a decrypt attempt: pypdf raises FileNotDecryptedError on
    page access while still locked, so a clean first-page read is the
    signal that the empty password actually unlocked the file.
    """
    try:
        pages = reader.pages
        if len(pages):
            _ = pages[0].extract_text() or ""
        return True
    except Exception:
        return False


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
    encryption: str | None = None
    if encrypted:
        # Owner-password-only PDFs (empty user password; common on
        # gov/financial PDFs): try the empty password first. BLOCKED-
        # encrypted is reserved for files that genuinely need a USER
        # password -- the Operator decrypts those; passwords are never
        # handled here. (Checked before touching pages: pypdf raises
        # FileNotDecryptedError on page access while still locked.)
        try:
            unlocked = bool(reader.decrypt(""))
        except Exception:
            unlocked = False
        if not unlocked or not _pages_readable(reader):
            return PageBundle([], "blocked", TS_BLOCKED,
                               reason_code=RC_ENCRYPTED)
        encryption = "owner-only"

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
        # R15: widget rects for the form-field geometry source. "line"
        # is the exact appended text the resolver matches raw_text on.
        rects = _acroform_rects(reader)
        for name, value in form_values.items():
            if name in rects:
                rects[name]["line"] = f"{name}: {value}"
        return PageBundle([native + "\n" + form_lines] if native.strip()
                          else [form_lines],
                          "form-field", TS_FORM_FIELD,
                          encryption=encryption,
                          pdf_path=pdf_path,
                          acroform_rects=rects or None)

    attempts: list = []
    engine = engine_version = None
    confidences: list[float] = []
    ocr_words: dict[int, list] = {}
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
            # R15: tesseract TSV word boxes, keyed by 0-based bundle page.
            # The OCR ran on a single-page PDF, so remap each word's
            # page to the bundle page it belongs to.
            words = result.get("words")
            if words:
                for word in words:
                    word["page"] = i - 1
                ocr_words[i - 1] = words

    full = "\n".join(page_texts)
    if ocr_pages and not full.strip():
        return PageBundle(page_texts, "blocked", TS_BLOCKED,
                           reason_code=RC_OCR_INSUFFICIENT,
                           ocr_engine=engine, engine_version=engine_version,
                           attempts=attempts)

    route = "ocr" if ocr_pages else ("form-field" if form_values
                                    else "native")
    ocr_mode = attempts[-1].get("mode") if attempts else None
    # R15: text_source names WHICH text was used --
    # "ocr:<engine>/<mode>", never a bare "ocr".
    text_source = (_ocr_text_source(engine, ocr_mode) if ocr_pages
                   else (TS_FORM_FIELD if form_values else TS_NATIVE))
    # If AcroForm values exist alongside OCR'd pages, append them so the
    # field data is not lost.
    acroform_rects = None
    if form_values and ocr_pages:
        form_lines = "\n".join(f"{k}: {v}"
                               for k, v in sorted(form_values.items()))
        page_texts = list(page_texts)
        page_texts[-1] = page_texts[-1] + "\n" + form_lines
        rects = _acroform_rects(reader)
        for name, value in form_values.items():
            if name in rects:
                rects[name]["line"] = f"{name}: {value}"
        acroform_rects = rects or None
    return PageBundle(
        page_texts, route, text_source,
        ocr_engine=engine, engine_version=engine_version,
        ocr_mode=ocr_mode,
        attempts=attempts,
        mean_confidence=(sum(confidences) / len(confidences)
                         if confidences else None),
        encryption=encryption,
        # R15: native/form-field text comes from this PDF (pdfplumber
        # word boxes); OCR pages carry tesseract word boxes instead.
        pdf_path=pdf_path if route in ("native", "form-field") else None,
        ocr_words=ocr_words or None,
        acroform_rects=acroform_rects,
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


def _tfield(value, confidence, raw_text, span):
    """One transcript field entry (R15).

    ``raw_text`` is always the verbatim source line (never synthesized,
    never "" for a field with an extracted value); ``confidence`` is
    derived from the parse (never hardcoded); ``span`` is the transient
    ``(start, end)`` extraction-text span for provenance attachment.
    """
    entry = {"value": value, "confidence": confidence,
             "raw_text": raw_text}
    if span is not None:
        entry["_extract_span"] = span
    return entry


def _unparsed_field(unparsed: list, unparsed_spans: list) -> dict:
    """The ``_unparsed_lines`` bookkeeping field.

    raw_text is the verbatim unparsed lines joined (non-empty whenever
    the value is non-empty); the span covers the first..last unparsed
    line in extraction-text coordinates.
    """
    spans = [s for s in (unparsed_spans or []) if s is not None]
    span = ((min(s for s, _ in spans), max(e for _, e in spans))
            if spans else None)
    return _tfield(unparsed, "low", "\n".join(unparsed), span)


def _transcript_line_fields(parsed: dict,
                            txn_counts: dict | None = None) -> tuple[dict, list, list]:
    """Shared builder for return/account transcript parsed dicts.

    Returns (fields, unparsed_lines, unparsed_spans). Every field gets
    verbatim raw_text, a derived confidence, and an extraction span.

    X4: repeated TC codes get ordinal-suffixed keys. The first
    occurrence keeps ``tc_<code>`` (existing consumers depend on it);
    repeats become ``tc_<code>_2``, ``tc_<code>_3``, ... in parser
    order (deterministic). ``txn_counts`` is the shared ordinal
    namespace: pass one dict across calls to share it (the
    RECORD_OF_ACCOUNT branch does, so cross-section repeats share the
    namespace); omit it for a fresh per-call namespace.
    """
    line_raw = parsed.get("line_raw_text", {})
    line_spans = parsed.get("line_spans", {})
    line_conf = parsed.get("line_confidence", {})
    fields = {
        label: _tfield(val, line_conf.get(label, "medium"),
                       line_raw.get(label, ""), line_spans.get(label))
        for label, val in parsed.get("lines", {}).items()
    }
    if txn_counts is None:
        txn_counts = {}
    for t in parsed.get("transactions", []):
        base = f"tc_{t.get('code')}"
        txn_counts[base] = txn_counts.get(base, 0) + 1
        n = txn_counts[base]
        key = base if n == 1 else f"{base}_{n}"
        fields[key] = _tfield(
            t.get("amount"), "medium",
            t.get("raw", "") or t.get("description", ""), t.get("span"))
    return (fields, parsed.get("unparsed_lines", []),
            parsed.get("unparsed_spans", []))


def _fields_from_transcript(form_type: str, text: str,
                            year: int | None) -> tuple[dict, str]:
    """Adapt transcript parser output to the Document fields shape.

    R8: positional payer keys (payer1.box1); the payer name is stored as
    a payer1.name field VALUE, never embedded in a key.

    R15: every field carries verbatim raw_text (the actual source line),
    a derived confidence, and an extraction span -- never synthesized
    evidence, never hardcoded "high".

    R17: ACCOUNT_TRANSCRIPT maps balance/accrual lines as fields plus
    tc_<code> transaction fields, same field shape as the return branch.
    X4: repeated TC codes get ordinal-suffixed keys (tc_806_2, ...);
    RECORD_OF_ACCOUNT merges both sections' fields with ONE ordinal
    namespace across sections; section provenance is carried by each
    field's char_span (R15), not by a synthesized tag prefix in raw_text.
    """
    if form_type == "WAGE_INCOME_TRANSCRIPT":
        parsed = transcript.parse_wage_income_transcript(text, tax_year=year)
        fields: dict = {}
        for i, payer in enumerate(parsed.get("payers", [])):
            prefix = f"payer{i + 1}"
            fields[f"{prefix}.name"] = _tfield(
                payer.get("payer", "unknown"),
                payer.get("header_confidence", "low"),
                payer.get("header_raw") or "",
                payer.get("header_span"),
            )
            box_spans = payer.get("box_spans", {})
            for box, val in payer.get("boxes", {}).items():
                bs = box_spans.get(box, {})
                fields[f"{prefix}.{box}"] = _tfield(
                    val, bs.get("confidence", "medium"),
                    bs.get("raw", ""), bs.get("span"))
        unparsed = parsed.get("unparsed_lines", [])
        unparsed_spans = parsed.get("unparsed_spans", [])
    elif form_type == "ACCOUNT_TRANSCRIPT":
        parsed = transcript.parse_account_transcript(text, tax_year=year)
        fields, unparsed, unparsed_spans = _transcript_line_fields(parsed)
    elif form_type == "RECORD_OF_ACCOUNT":
        parsed = transcript.parse_record_of_account(text, tax_year=year)
        fields = {}
        # Top-level unparsed (document lines outside both sections) plus
        # each section's own unparsed -- all verbatim, spans parallel.
        unparsed = list(parsed.get("unparsed_lines", []))
        unparsed_spans = list(parsed.get("unparsed_spans", []))
        # X4: ONE ordinal namespace across both sections, so a TC code
        # repeated in return_section and account_section yields
        # tc_<code> and tc_<code>_2 instead of one silently overwriting
        # the other.
        txn_counts: dict = {}
        for section in ("return_section", "account_section"):
            sec = parsed.get(section, {})
            sec_fields, sec_unparsed, sec_spans = _transcript_line_fields(
                sec, txn_counts)
            fields.update(sec_fields)
            unparsed.extend(sec_unparsed)
            unparsed_spans.extend(sec_spans)
    else:
        parsed = transcript.parse_return_transcript(text, tax_year=year)
        fields, unparsed, unparsed_spans = _transcript_line_fields(parsed)
    if unparsed:
        fields["_unparsed_lines"] = _unparsed_field(unparsed, unparsed_spans)
    status = "transcribed" if not unparsed else "needs_review"
    return fields, status


def _page_range_str(section: extractors.FormSection) -> str:
    if section.page_start == section.page_end:
        return str(section.page_start)
    return f"{section.page_start}-{section.page_end}"


def _extract_for_type(
    form_type: str, text: str, year: int | None,
    text_source: str | None = None,
) -> tuple[dict, str]:
    """Route section text to the right extractor (legacy routing).

    ``text_source`` is the bundle's text_source vocabulary
    (``ocr:<engine>/<mode>`` for OCR, ``native``/``form-field``/etc.
    otherwise); it reaches the box-form extractors (O1a OCR-tolerant
    1099-B box tokens). Transcript extractors take no text_source.
    """
    if form_type in TRANSCRIPT_FORMS:
        return _fields_from_transcript(form_type, text, year)
    if form_type in BOX_FORMS:
        return extractors.extract_fields(form_type, text,
                                         text_source=text_source)
    return {}, "needs_review"


def _extractor_id_for(form_type: str) -> str:
    """R15 extractor id: "<name>:<version>"."""
    if form_type in TRANSCRIPT_FORMS:
        return f"transcript:{transcript.TRANSCRIPT_VERSION}"
    return f"extractors:{extractors.EXTRACTOR_VERSION}"


def _geometry_for(bundle: PageBundle | None) -> GeometryResolver:
    """Build the R15 geometry resolver for an ingest bundle.

    Native/form-field text resolves word boxes from the source PDF via
    pdfplumber (fillable forms try AcroForm widget rects first); OCR
    text resolves tesseract TSV word boxes; sidecar/.txt text has no
    layout source (char spans only).
    """
    if bundle is None:
        return GeometryResolver()
    if bundle.route == "ocr":
        return GeometryResolver(ocr_words=bundle.ocr_words)
    if bundle.route == "form-field":
        return GeometryResolver(pdf_path=bundle.pdf_path,
                                acroform_rects=bundle.acroform_rects)
    if bundle.route == "native":
        return GeometryResolver(pdf_path=bundle.pdf_path)
    return GeometryResolver()


def _attach_provenance(fields: dict, page_spans, form_type: str,
                       bundle: PageBundle | None,
                       page_texts: list[str] | None) -> dict:
    """R15: replace transient extraction spans with provenance dicts.

    ``page_spans`` maps the extraction text back to source pages;
    ``page_texts`` is the stored per-page text (for word-box alignment;
    None/empty degrades bboxes to None, char spans still compute).
    """
    return attach_field_provenance(
        fields, page_spans, _extractor_id_for(form_type),
        _geometry_for(bundle), page_texts or [])


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
    doc.encryption = bundle.encryption


def _utcnow_iso() -> str:
    """UTC timestamp for decision-log payloads."""
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# -- R13 lifecycle helpers -------------------------------------------------
#
# Every Document status change in ingest goes through
# lifecycle.transition(). Helpers below fire the right event for each
# call site; a refused transition is a loud RuntimeError (the table
# guarantees these rows -- a refusal means the table or the caller is
# wrong, never something to swallow).

def _check_transition(res: "lifecycle.TransitionResult",
                      doc: Document) -> "lifecycle.TransitionResult":
    if not res.ok:
        raise RuntimeError(
            f"lifecycle {res.event} refused for {doc.doc_id} "
            f"({res.from_state}, actor={res.actor}): {res.reason_code}")
    return res


def _fire_scan_select(store: DocumentStore, doc: Document) -> Document:
    """New-doc preamble: scan (none -> discovered) then select.

    Batch ingest runs under the standing auto-select policy (R13 table
    row: discovered --select(system)--> selected, guard auto_select).
    """
    _check_transition(
        lifecycle.transition(doc, lifecycle.SCAN, actor=lifecycle.SYSTEM,
                             event_input=lifecycle.ScanInput(), store=store),
        doc)
    _check_transition(
        lifecycle.transition(doc, lifecycle.SELECT, actor=lifecycle.SYSTEM,
                             event_input=lifecycle.SelectInput(auto=True),
                             store=store),
        doc)
    return doc


def _ingest_input(bundle: PageBundle, *, clean: bool = True,
                 multiform: bool = False) -> "lifecycle.IngestInput":
    route = bundle.route
    if multiform:
        route = "multiform"
    elif route == "blocked":
        route = "blocked"
    elif route == "error":
        route = "error"
    else:
        route = "ok"
    return lifecycle.IngestInput(route=route,
                                route_reason=bundle.reason_code,
                                clean=clean)


def _fire_ingest(store: DocumentStore, doc: Document, bundle: PageBundle,
                 *, clean: bool = True,
                 multiform: bool = False) -> "lifecycle.TransitionResult":
    """Fire the ingest event for doc's current lifecycle state.

    Fresh docs (lifecycle.new_document) get the scan -> select preamble
    first. Returns the TransitionResult; the caller persists when it is
    not a no-op.
    """
    if lifecycle.is_fresh(doc):
        _fire_scan_select(store, doc)
    return _check_transition(
        lifecycle.transition(doc, lifecycle.INGEST, actor=lifecycle.SYSTEM,
                             event_input=_ingest_input(
                                 bundle, clean=clean, multiform=multiform),
                             store=store),
        doc)


def _fire_reextract(store: DocumentStore, doc: Document,
                    values_differ: bool,
                    reason: str = "extraction-disagrees"
                    ) -> "lifecycle.TransitionResult":
    """Fire re_extract on a validated/rereview doc (R4).

    Validated values are always kept (the caller reconciles first);
    disagreement moves validated -> rereview, agreement is a no-op.
    """
    return _check_transition(
        lifecycle.transition(
            doc, lifecycle.RE_EXTRACT, actor=lifecycle.SYSTEM,
            event_input=lifecycle.ReextractInput(values_differ=values_differ,
                                                reason=reason),
            store=store),
        doc)


# -- Medallion silver write (I6/I7/R4; W2) -----------------------------------

def _docs_for_bronze(store: DocumentStore, sha: str) -> list[Document]:
    """Silver documents derived from one bronze object.

    B1: indexed store query (was list()-then-filter-in-Python, which
    decoded every row once per ingested file).
    """
    docs_for_bronze = getattr(store, "docs_for_bronze", None)
    if docs_for_bronze is not None:
        return docs_for_bronze(sha)
    return [d for d in store.list()
            if getattr(d, "source_sha256", None) == sha]


def _doc_derivation(store: DocumentStore,
                    doc: Document) -> tuple[str | None, str | None]:
    """A doc's (derivation_version, config_hash) for its CURRENT fields.

    Reads the artifact rows for the doc's current field anchors only:
    rows for vanished anchors are stale derivations (a known
    replace_artifacts gap -- full replace per derivation is not
    implemented -- flagged to W1) and must not vote. (None, None) when
    the derivation cannot be attributed (no artifacts, or a field
    without a row).
    """
    anchors = silver.field_artifact_anchors(doc.fields)
    if not anchors:
        return None, None
    rows = {(a["artifact_type"], a["anchor"]): a
            for a in store.get_artifacts(doc.doc_id) or []}
    versions: set = set()
    configs: set = set()
    for key in anchors:
        row = rows.get(key)
        if row is None:
            return None, None
        versions.add(row.get("derivation_version"))
        configs.add(row.get("config_hash"))
    if len(versions) == 1 and len(configs) == 1:
        version = next(iter(versions))
        return (version, next(iter(configs))) if version is not None \
            else (None, None)
    return None, None


def _stored_derivation(store: DocumentStore, doc: Document,
                       fallback: silver.DerivationContext
                       ) -> silver.DerivationContext:
    """A doc's derivation, falling back to the given context."""
    version, config_hash = _doc_derivation(store, doc)
    if version is None:
        return fallback
    return silver.DerivationContext(derivation_version=version,
                                    config_hash=config_hash or "")


def _persist_silver_doc(store: DocumentStore, doc: Document,
                        ctx: silver.DerivationContext,
                        bronze_hash: str | None) -> None:
    """Write one silver_doc row (thin wrapper over the shared helper)."""
    silver.persist_silver_doc(store, doc, ctx, bronze_hash)


def _sidecar_changed(store: DocumentStore, path: Path,
                    docs: list[Document]) -> bool:
    """True when the current sidecar differs from derivation time.

    A same-basename .txt sidecar is a derivation INPUT (it becomes the
    document text when present). The derivation consumed exactly the
    sidecar text iff the docs' stored text still equals it; otherwise
    the cache must miss and re-derive. A *removed* sidecar is not
    detected (the kept transcription is still valid text of the
    unchanged bytes) -- documented I2 tradeoff.
    """
    sidecar = _sidecar_for(path)
    if sidecar is None:
        return False
    try:
        text = sidecar.read_bytes().decode("utf-8", errors="replace")
    except OSError:
        return False
    stored_parts = []
    for d in sorted(docs, key=lambda d: d.doc_id):
        try:
            stored_parts.append(store.load_ocr(d.doc_id))
        except (FileNotFoundError, OSError):
            return True  # no stored text: re-derive to be safe
    return "\n".join(stored_parts) != text


def _derivation_cache_hit(store: DocumentStore, sha: str,
                          path: Path | None = None) -> bool:
    """I2/I5: is this bronze already derived at the current version?

    Checks every silver doc for the bronze: hit only when each doc's
    artifacts are stamped (EXTRACTOR_VERSION, current config_hash) AND
    the sidecar situation is unchanged (a sidecar is a derivation
    input). Docs with no artifacts (BLOCKED) can never hit -- they
    re-run the gate, which is a DB no-op when the outcome is unchanged.
    """
    ctx = silver.DerivationContext.current()
    docs = _docs_for_bronze(store, sha)
    if not docs:
        return False
    for d in docs:
        version, config_hash = _doc_derivation(store, d)
        if (version != ctx.derivation_version
                or config_hash != ctx.config_hash):
            return False
    if path is not None and _sidecar_changed(store, path, docs):
        return False
    return True


def _validated_field_keys(store: DocumentStore, doc: Document) -> set[str]:
    """Field keys the Operator validated, from the decision log (I6).

    Union of ``validated_fields`` across kind=validate decisions plus
    kind=edit fields. Pre-decision-log fallback: when a validated doc
    has no decisions at all, every field counts as validated
    (conservative -- R4: validated values are never overwritten).
    """
    keys: set[str] = set()
    saw = False
    for d in store.decisions_for(doc_id=doc.doc_id, kind="validate") or []:
        saw = True
        payload = d.get("payload") or {}
        for k in payload.get("validated_fields") or []:
            keys.add(k)
    for d in store.decisions_for(doc_id=doc.doc_id, kind="edit") or []:
        saw = True
        f = (d.get("payload") or {}).get("field")
        if f and not f.startswith(silver.BOOKKEEPING_PREFIX):
            keys.add(f)
    if not saw and doc.status == "validated":
        keys.update(k for k in (doc.fields or {})
                    if not k.startswith(silver.BOOKKEEPING_PREFIX))
    return keys


def _flag_orphaned_decisions(store: DocumentStore, doc_id: str,
                             old_artifacts: list[dict],
                             new_artifacts: list[dict]) -> None:
    """Flag decisions whose artifacts vanished in a re-derivation (I6).

    Appends one follow-up decision per affected validate/edit/exclude
    decision with ``payload["orphaned"] = True`` (actor=system).
    Decision rows are never updated or deleted.
    """
    dropped = silver.dropped_artifacts(old_artifacts, new_artifacts)
    if not dropped:
        return
    dropped_ids = {a["artifact_id"] for a in dropped}
    dropped_fields = {a["anchor"] for a in dropped
                      if a["artifact_type"] == silver.FIELD}
    ts = _utcnow_iso()
    for d in store.decisions_for(doc_id=doc_id) or []:
        kind = d.get("kind")
        if kind not in ("validate", "edit", "exclude"):
            continue
        payload = d.get("payload") or {}
        if payload.get("orphaned"):
            continue  # never re-flag a flag
        row_aid = d.get("artifact_id") or payload.get("artifact_id")
        if kind == "validate":
            orphaned_fields = sorted(
                set(payload.get("validated_fields") or [])
                & dropped_fields)
            if not orphaned_fields:
                continue
            new_payload = {"doc_id": doc_id,
                           "validated_fields": orphaned_fields,
                           "orphaned": True, "ts": ts}
        elif kind == "edit":
            if not (payload.get("field") in dropped_fields
                    or row_aid in dropped_ids):
                continue
            new_payload = {**payload, "orphaned": True, "ts": ts}
        else:  # exclude
            if row_aid not in dropped_ids:
                continue
            new_payload = {**payload, "orphaned": True, "ts": ts}
        store.log_decision(actor="system", kind=kind,
                           artifact_id=d.get("artifact_id"),
                           doc_id=doc_id, group_id=d.get("group_id"),
                           payload=new_payload)


def _store_pages_for(bundle: PageBundle, text: str) -> list[str] | None:
    """Per-page list for save_ocr's page markers, or None for legacy.

    Only the OCR route stores page structure (form-feed separators):
    native/form-field/sidecar text and section-text call sites keep the
    legacy byte-identical stored text. The markers apply only when the
    stored text IS the whole bundle join (``"\\n".join(bundle.pages)``)
    -- the extraction text is always the ``"\\n"`` join, unchanged.

    O2-repair: the OCR indicator is the route OR a set ocr_engine
    (escalation paths such as force-ocr via ocrmypdf may not carry
    route == "ocr" even though per-page OCR produced the bundle text).
    """
    is_ocr = bundle.route == "ocr" or bundle.ocr_engine is not None
    if is_ocr and bundle.pages and text == "\n".join(bundle.pages):
        return list(bundle.pages)
    return None


def _store_ocr_text(store: DocumentStore, doc_id: str, text: str,
                    bundle: PageBundle) -> str:
    """save_ocr plus the O2 OCR extras: page markers and word boxes.

    Page markers (``\\f`` separators) go into the stored text only on
    the whole-document OCR path (see _store_pages_for); the tesseract
    TSV word boxes persist to the ``ocr/<doc_id>.words.json`` sidecar
    so R15/R19 can resolve ``bbox_source="tesseract"`` after ingest,
    not just from the in-memory bundle.
    """
    ref = store.save_ocr(doc_id, text, pages=_store_pages_for(bundle, text))
    if bundle.ocr_words:
        store.save_ocr_words(doc_id, bundle.ocr_words)
    return ref


def _derive_and_store(store: DocumentStore, doc: Document, text: str,
                      bundle: PageBundle, source_sha: str,
                      ctx: silver.DerivationContext) -> Document:
    """Fresh silver write: OCR text, provenance, silver_doc + artifacts."""
    doc.ocr_text_ref = _store_ocr_text(store, doc.doc_id, text, bundle)
    _apply_provenance(doc, bundle, source_sha)
    _persist_silver_doc(store, doc, ctx, source_sha)
    _persist_bronze_text(store, bundle, source_sha, ctx)
    store.replace_artifacts(
        doc.doc_id,
        silver.derive_artifacts(
            doc, bundle, bronze_hash=source_sha,
            derivation_version=ctx.derivation_version,
            config_hash=ctx.config_hash))
    return doc


def _persist_bronze_text(store: DocumentStore, bundle: PageBundle,
                         source_sha: str,
                         ctx: silver.DerivationContext) -> None:
    """Write per-page derived text rows (I5 cache key).

    Keyed by (bronze hash, page, derivation version, config): re-writing
    the same derivation is a no-op; a version bump adds rows. Feeds the
    L2 text fingerprint (duplicates.compute_and_store_text_fingerprint).

    B2: the full per-page row list is built in memory and written in one
    batched write_bronze_texts call (one transaction, one executemany),
    not one store write per page.
    """
    store.write_bronze_texts(
        source_sha,
        [
            {
                "page": i,
                "text_source": bundle.text_source,
                "engine": bundle.ocr_engine,
                "engine_version": bundle.engine_version,
                "ocr_mode": bundle.ocr_mode,
                "derivation_version": ctx.derivation_version,
                "config_hash": ctx.config_hash,
                "text": page_text,
            }
            for i, page_text in enumerate(bundle.pages, start=1)
        ],
    )


def _store_blocked_reingest(store: DocumentStore, existing: Document,
                            doc: Document, bundle: PageBundle,
                            source_sha: str,
                            ctx: silver.DerivationContext) -> Document:
    """A failed re-ingest never destroys what we have (R4).

    Keeps existing text/fields; refreshes provenance in memory.
    Unvalidated docs move to BLOCKED (the file honestly is blocked now);
    validated/rereview docs are never overwritten. A no-op when nothing
    changed (same state and same reason: the transition is not logged).
    """
    _apply_provenance(existing, bundle, source_sha)
    if existing.status in (lifecycle.VALIDATED, lifecycle.REREVIEW):
        return existing  # R4: validated values are never overwritten
    if bundle.route != "blocked":
        return existing
    if (existing.status == lifecycle.BLOCKED
            and existing.status_reason == bundle.reason_code):
        return existing  # no-op: same state, same reason
    res = _fire_ingest(store, existing, bundle)
    if not res.noop:
        _persist_silver_doc(
            store, existing,
            _stored_derivation(store, existing, ctx), source_sha)
    return existing


def _store_version_bump(store: DocumentStore, existing: Document,
                        doc: Document, text: str, bundle: PageBundle,
                        source_sha: str,
                        ctx: silver.DerivationContext) -> Document:
    """I6: rebuild silver on a derivation version/config bump.

    Operator decisions are preserved: validated values win over
    re-derived values (changed -> keep + re_review); validated fields
    that vanished from the new extraction are dropped and their
    decisions flagged orphaned. Unvalidated fields take the new values.
    Artifacts are fully replaced at the new derivation.
    """
    validated_keys = _validated_field_keys(store, existing)
    old_artifacts = store.get_artifacts(existing.doc_id)
    result = silver.reconcile_rederivation(
        old_fields=existing.fields, new_fields=doc.fields,
        validated_keys=validated_keys)
    # Start from the existing record: status / relevance / validated_at /
    # provenance history are Operator or Operator-visible state, never
    # reset by a re-derivation.
    existing.fields = result.fields
    # R13: validated/rereview docs go through the re_extract event.
    # reconcile_rederivation already kept the validated values;
    # disagreement moves validated -> rereview (validated values kept),
    # agreement is a logged no-op.
    if existing.status in (lifecycle.VALIDATED, lifecycle.REREVIEW):
        _fire_reextract(store, existing, result.re_review)
    elif result.re_review and not existing.re_review:
        # Unvalidated docs have no validated keys, so reconcile never
        # flags them; kept as a fail-safe mirroring the old behavior.
        existing.re_review = True
        existing.status_reason = "extraction-disagrees"
    existing.ocr_text_ref = _store_ocr_text(store, existing.doc_id, text, bundle)
    _apply_provenance(existing, bundle, source_sha)
    _persist_silver_doc(store, existing, ctx, source_sha)
    _persist_bronze_text(store, bundle, source_sha, ctx)
    new_artifacts = silver.derive_artifacts(
        existing, bundle, bronze_hash=source_sha,
        derivation_version=ctx.derivation_version,
        config_hash=ctx.config_hash)
    store.replace_artifacts(existing.doc_id, new_artifacts)
    _flag_orphaned_decisions(store, existing.doc_id, old_artifacts,
                             new_artifacts)
    return existing


def _store_idempotent(store: DocumentStore, doc: Document, text: str,
                      bundle: PageBundle, source_sha: str, *,
                      clean: bool = True,
                      multiform: bool = False) -> Document:
    """Medallion-aware idempotent doc write (I6/I7/R4).

    - unknown doc_id -> fresh derivation (silver_doc + artifacts); the
      R13 preamble scan -> select (system auto-select) -> ingest fires
      first, so the event log opens with the doc's full chain.
    - re-derivation refused/failed (blocked/error route) -> keep
      existing text/fields; failed re-ingests never destroy validated
      values (validated/rereview docs are untouched).
    - same (version, config), agreeing re-derivation -> true no-op
      (I2): no writes at all.
    - same (version, config), disagreeing re-derivation -> validated/
      rereview: validated values kept, re_extract -> rereview;
      unvalidated: the fresh extraction wins.
    - version/config bump -> I6 reconcile (see _store_version_bump).
    - terminal states (excluded, ORPHANED): re-ingest never revives.

    Every status change goes through lifecycle.transition(); a refused
    transition is a loud RuntimeError, never a silent skip.

    Runs inside the caller's transaction (contract section 8: derive in
    ONE txn, I7).
    """
    ctx = silver.DerivationContext.current()
    existing = store.get(doc.doc_id)
    if existing is None:
        _fire_ingest(store, doc, bundle, clean=clean, multiform=multiform)
        return _derive_and_store(store, doc, text, bundle, source_sha, ctx)

    if existing.status in (lifecycle.EXCLUDED, lifecycle.ORPHANED):
        return existing  # terminal: re-ingest never revives a disposal

    if bundle.route in ("blocked", "error"):
        return _store_blocked_reingest(store, existing, doc, bundle,
                                       source_sha, ctx)

    old_ctx = _stored_derivation(store, existing, ctx)
    if (old_ctx.derivation_version != ctx.derivation_version
            or old_ctx.config_hash != ctx.config_hash):
        return _store_version_bump(store, existing, doc, text, bundle,
                                   source_sha, ctx)

    if silver.fields_agree(existing.fields, doc.fields):
        return existing  # I2: byte-identical re-derivation, no writes

    # Same-version disagreement: unreachable with deterministic
    # extraction (same bytes -> same fields); kept as a fail-safe
    # mirroring the pre-medallion R4 semantics.
    if existing.status in (lifecycle.VALIDATED, lifecycle.REREVIEW):
        # R13: validated values are kept (nothing to reconcile here --
        # fields were NOT overwritten); disagreement -> rereview.
        res = _fire_reextract(store, existing, True)
        if not res.noop:
            _persist_silver_doc(store, existing, old_ctx, source_sha)
        return existing
    # Not validated: the fresh extraction wins (same doc_id; relevance
    # and other Operator-visible state are preserved). The ingest event
    # moves the existing doc to the fresh extraction's state.
    res = _fire_ingest(store, existing, bundle,
                       clean=(doc.status == "transcribed"))
    relevance = existing.relevance
    validated_at = existing.validated_at
    existing.fields = doc.fields
    existing.re_review = False
    existing.ocr_text_ref = _store_ocr_text(store, existing.doc_id, text, bundle)
    _apply_provenance(existing, bundle, source_sha)
    existing.relevance = relevance
    existing.validated_at = validated_at
    _persist_silver_doc(store, existing, ctx, source_sha)
    store.replace_artifacts(
        existing.doc_id,
        silver.derive_artifacts(
            existing, bundle, bronze_hash=source_sha,
            derivation_version=ctx.derivation_version,
            config_hash=ctx.config_hash))
    return existing


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
    fields, status = _extract_for_type(
        section.form_type, section.text, year,
        text_source=bundle.text_source if bundle is not None else None)
    # R15: extraction-time field provenance (char spans + geometry).
    fields = _attach_provenance(
        fields, section.page_spans, section.form_type, bundle,
        bundle.pages if bundle is not None else None)
    # R4: <source-bytes-hash>-p<page_range>-<section-hash>. The section
    # hash keeps children unique when two sections share a page range
    # (e.g. a single-page .txt holding two forms); the mandated
    # <bytes-hash>-p<page_range> shape is the prefix.
    section_hash = hashlib.sha256(
        section.text.encode("utf-8")).hexdigest()[:8]
    doc_id = f"{parent_doc_id}-p{_page_range_str(section)}-{section_hash}"
    # R13: fresh docs enter with no lifecycle state; the scan -> select
    # -> ingest preamble fires inside _store_idempotent.
    doc = lifecycle.new_document(
        doc_id=doc_id,
        tax_year=year,
        form_type=section.form_type,
        source_path=str(path),
        ocr_text_ref="",
        fields=fields,
        page_range=_page_range_str(section),
        parent_doc_id=parent_doc_id,
    )
    if bundle is not None and source_sha is not None:
        return _store_idempotent(store, doc, section.text, bundle,
                                 source_sha,
                                 clean=(status == "transcribed"))
    # Legacy direct call (R1 tests): plain upsert, no provenance.
    doc.ocr_text_ref = store.save_ocr(doc_id, section.text)
    _fire_scan_select(store, doc)
    _check_transition(
        lifecycle.transition(
            doc, lifecycle.INGEST, actor=lifecycle.SYSTEM,
            event_input=lifecycle.IngestInput(
                route="ok", clean=(status == "transcribed")),
            store=store),
        doc)
    store.upsert(doc)
    return doc


def _blocked_document(path: Path, doc_id: str, bundle: PageBundle,
                      source_sha: str, store: DocumentStore,
                      form_type: str = "UNKNOWN") -> Document:
    """A BLOCKED or ERROR document: honest about the failure, with a
    reason code -- never exception text, never an empty silent record.

    R13: the ingest event maps route "blocked" -> BLOCKED and route
    "error" -> errored (previously error-route docs were needs_review).
    """
    doc = lifecycle.new_document(
        doc_id=doc_id,
        tax_year=None,
        form_type=form_type,
        source_path=str(path),
        ocr_text_ref="",
        fields={},
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
    doc = lifecycle.new_document(
        doc_id=parent_doc_id,
        tax_year=year,
        form_type="UNKNOWN",
        source_path=str(path),
        ocr_text_ref="",
        fields={},
    )
    if bundle is not None and source_sha is not None:
        return _store_idempotent(store, doc, text, bundle, source_sha,
                                 multiform=True)
    doc.ocr_text_ref = store.save_ocr(parent_doc_id, text)
    _fire_scan_select(store, doc)
    _check_transition(
        lifecycle.transition(
            doc, lifecycle.INGEST, actor=lifecycle.SYSTEM,
            event_input=lifecycle.IngestInput(route="multiform"),
            store=store),
        doc)
    store.upsert(doc)
    return doc


def _check_no_transcript_box_mix(
        sections: list[extractors.FormSection]) -> None:
    """X2 guard: one source can never yield both transcript-derived and
    box-form documents.

    The document-level detector (extractors.detect_transcript_type)
    must type every transcript before the R1 split runs. Reaching the
    split with a mixed set means the detector missed a transcript title
    -- exactly the phantom-document regression's shape (a transcript's
    embedded "Form W-2" / "Schedule D" headings spawning box-form
    children under it, an L3 double-count risk). Fail loudly, never
    silently: ingest_dir records the failure as an errored file with
    RC_EXTRACT_FAILED.
    """
    typed = {s.form_type for s in sections
             if not s.excluded and s.form_type}
    transcript = sorted(t for t in typed if t in TRANSCRIPT_FORMS)
    box = sorted(t for t in typed if t in BOX_FORMS)
    if transcript and box:
        raise AssertionError(
            "X2 guard: one source would yield both transcript-derived "
            f"{transcript} and box-form {box} documents -- the "
            "document-level transcript detector missed a transcript title")


def _transcript_document(path: Path, doc_id: str, form_type: str,
                         text: str, year: int | None, bundle: PageBundle,
                         source_sha: str, store: DocumentStore) -> Document:
    """X2: one Document for a transcript-typed source.

    The document-level detector typed this source as a transcript: the
    whole text is parsed by that type's transcript parser. The text is
    NEVER split into form sections -- embedded "Form W-2" / "Schedule
    D" headings are transcript content, handled by the transcript
    parsers, never child documents.
    """
    fields, status = _extract_for_type(form_type, text, year,
                                        text_source=bundle.text_source)
    # R15: extraction-time field provenance over the whole text (page
    # boundaries survive via the joined-text page map -- P4).
    fields = _attach_provenance(fields, page_spans_for_joined(bundle.pages),
                                form_type, bundle, bundle.pages)
    # R13: fresh docs enter with no lifecycle state; the scan -> select
    # -> ingest preamble fires inside _store_idempotent.
    doc = lifecycle.new_document(
        doc_id=doc_id,
        tax_year=year,
        form_type=form_type,
        source_path=str(path),
        ocr_text_ref="",
        fields=fields,
    )
    return _store_idempotent(store, doc, text, bundle, source_sha,
                             clean=(status == "transcribed"))


def _build_documents(path: Path, doc_id: str, bundle: PageBundle,
                     source_sha: str, store: DocumentStore) -> list[Document]:
    """Split gated pages into form sections and build Documents."""
    pages = bundle.pages
    text = "\n".join(pages)

    # X2: the transcript type is decided at DOCUMENT level first, from
    # page-1 title lines (extractors.detect_transcript_type). A
    # transcript-typed source is never split into form sections.
    transcript_type = extractors.detect_transcript_type(pages)
    if transcript_type is not None:
        year = extractors.detect_tax_year(text)
        return [_transcript_document(path, doc_id, transcript_type, text,
                                     year, bundle, source_sha, store)]

    sections = extractors.split_form_sections(pages)
    typed = [s for s in sections if not s.excluded and s.form_type]
    distinct = list(dict.fromkeys(s.form_type for s in typed))

    # R17: a Record of Account is one IRS transcript whose return and
    # account sections carry their own transcript headers. Those inner
    # anchors are content, not separate documents: collapse to a single
    # RECORD_OF_ACCOUNT document parsed over the whole text by
    # parse_record_of_account. (A genuinely different transcript type,
    # e.g. WAGE_INCOME_TRANSCRIPT, still fans out below.)
    _ROA_INNER = {"RETURN_TRANSCRIPT", "ACCOUNT_TRANSCRIPT"}
    if "RECORD_OF_ACCOUNT" in distinct and set(distinct) <= (
        _ROA_INNER | {"RECORD_OF_ACCOUNT"}
    ):
        distinct = ["RECORD_OF_ACCOUNT"]
        typed = [
            extractors.FormSection(
                "RECORD_OF_ACCOUNT", text, 1, max(len(pages), 1),
                page_spans=page_spans_for_joined(pages),
            )
        ]

    # X2 guard: the split below must never mix transcript-derived and
    # box-form children (see _check_no_transcript_box_mix).
    _check_no_transcript_box_mix(typed)

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
    fields, status = _extract_for_type(form_type, section_text, year,
                                        text_source=bundle.text_source)
    # R15: extraction-time field provenance. With no typed sections the
    # extraction text is "\n".join(pages) -- page boundaries survive via
    # the joined-text page map (P4: never lose page boundaries).
    page_spans = (typed[0].page_spans if typed
                  else page_spans_for_joined(pages))
    fields = _attach_provenance(fields, page_spans, form_type, bundle,
                                bundle.pages)

    # R13: fresh docs enter with no lifecycle state; the scan -> select
    # -> ingest preamble fires inside _store_idempotent.
    doc = lifecycle.new_document(
        doc_id=doc_id,
        tax_year=year,
        form_type=form_type,
        source_path=str(path),
        ocr_text_ref="",
        fields=fields,
    )
    return [_store_idempotent(store, doc, section_text, bundle, source_sha,
                              clean=(status == "transcribed"))]


# -- Medallion ingest flow (contract section 8; W2) ----------------------------

def _encryption_hint(path: Path, suffix: str) -> str | None:
    """Cheap pre-ingest encryption probe for PDFs (X1 provenance).

    Returns "owner-only" when the file is encrypted but the empty
    password unlocks it, else None. (A required USER password is
    discovered by the R5 gate, which marks the doc BLOCKED-encrypted.)
    Page content is never parsed here -- just the encryption flag.
    """
    if suffix not in PDF_EXTS:
        return None
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        if not bool(reader.is_encrypted):
            return None
        try:
            unlocked = bool(reader.decrypt(""))
        except Exception:
            return None
        return "owner-only" if unlocked and _pages_readable(reader) else None
    except Exception:
        return None


def _sidecar_for(path: Path) -> Path | None:
    """A same-basename .txt/.TXT sidecar wins as the OCR text (it is the
    pre-existing OCR). Case-insensitive (R6)."""
    for ext in (".txt", ".TXT"):
        cand = path.parent / (path.stem + ext)
        if cand.is_file() and cand.resolve() != path.resolve():
            return cand
    return None


def _page_bundle_for(path: Path, source_bytes: bytes, suffix: str,
                     store: DocumentStore,
                     source_root: Path | None = None) -> PageBundle:
    """Route one file to its PageBundle (R5 gate). May raise _SkipFile.

    Pure derivation: no store writes happen here, so a skip fails closed
    with zero bronze/silver rows (W4 bronze_accounted stays whole).
    ``source_root`` is the ingest root the path is relative to (R11);
    the sidecar text_source names the sidecar relative to it (R15/P1).
    """
    # A same-basename .txt sidecar wins as the OCR text for PDFs and
    # images (pre-existing OCR). The doc_id still derives from the
    # source file's bytes, so the sidecar text attaches to the same
    # doc_id with provenance text_source="sidecar:<relpath>" (R4/R15).
    if suffix in PDF_EXTS | IMAGE_EXTS:
        sidecar = _sidecar_for(path)
        if sidecar is not None:
            text = sidecar.read_bytes().decode("utf-8", errors="replace")
            return PageBundle([text], "native",
                              _sidecar_text_source(
                                  _relpath(source_root, sidecar)))
    if suffix in PDF_EXTS:
        return _pdf_page_bundle(path, store)
    if suffix in TXT_EXTS:
        return PageBundle([source_bytes.decode("utf-8", errors="replace")],
                          "native", TS_NATIVE)
    if suffix in IMAGE_EXTS:
        if _pil_image() is None:
            raise _SkipFile(RC_IMAGE_SUPPORT_MISSING)
        if suffix in HEIC_EXTS and not _heif_supported():
            raise _SkipFile(RC_HEIC_UNSUPPORTED)
        sha = hashlib.sha256(source_bytes).hexdigest()
        try:
            pdf_path = _image_to_pdf(path, sha, store)
        except _SkipFile:
            raise
        except Exception:
            raise _SkipFile(RC_IMAGE_CONVERT_FAILED)
        return _pdf_page_bundle(pdf_path, store)
    raise _SkipFile(RC_UNSUPPORTED_TYPE)  # unreachable: caller pre-checks


def _relpath(source_root: Path | None, path: Path) -> str:
    """Root-relative path for provenance (R15); falls back to the file
    name when no root is known or the path escapes it."""
    if source_root is not None:
        try:
            return str(path.relative_to(source_root))
        except ValueError:
            pass
    return path.name


def _register_bronze(store: DocumentStore, sha: str, source_bytes: bytes,
                     path: str, *, encryption: str | None,
                     source_root: str | None = None,
                     source_relpath: str | None = None,
                     source_mtime: int | None = None) -> None:
    """Bronze steps (contract section 8).

    ``register_bronze`` runs FIRST so the first insert carries
    encryption (and source_root); re-registering never clobbers those.
    ``store_bronze_bytes`` re-registers idempotently inside.

    R15 source identity: the bronze manifest records the sha256 of the
    source bytes (the bronze hash itself), size, mtime, the path
    relative to its source root, and the ingest-time absolute path
    (via the alias table). ``verify_source_integrity`` checks alias
    paths against the stored hash.
    """
    # R11 source root: deferred (nullable per contract); W1's facade
    # path also passes None. Populating it is a coordinator call.
    store.register_bronze(sha, len(source_bytes), source_root=source_root,
                          encryption=encryption,
                          source_relpath=source_relpath,
                          source_mtime=source_mtime)
    store.store_bronze_bytes(sha, source_bytes)
    store.add_alias(sha, path)


def _hook_assess_new_bronze(store: DocumentStore, sha: str):
    """W3 duplicates hook (contract section 8, step 5). Lazy import.

    Never fails the ingest: duplicate assessment is advisory, and the
    hook must be a safe no-op when W3's tables are empty. Returns the
    outcome for the ingest report (group ids, or a skipped/error tag --
    hashes/ids only, never PII).
    """
    try:
        from . import duplicates as _duplicates
    except ImportError:
        return "skipped:duplicates-unavailable"
    assess = getattr(_duplicates, "assess_new_bronze", None)
    if assess is None:
        return "skipped:hook-missing"
    try:
        return assess(store, sha)
    except Exception as exc:  # surface, don't fail the ingest
        return f"error:{type(exc).__name__}"


def _hook_assess_silver_doc(store: DocumentStore, doc_id: str):
    """W3 duplicates hook (contract section 8, step 6). See above."""
    try:
        from . import duplicates as _duplicates
    except ImportError:
        return "skipped:duplicates-unavailable"
    assess = getattr(_duplicates, "assess_silver_doc", None)
    if assess is None:
        return "skipped:hook-missing"
    try:
        return assess(store, doc_id)
    except Exception as exc:  # surface, don't fail the ingest
        return f"error:{type(exc).__name__}"


def _mark_stale_children(store: DocumentStore, old_ids: set[str],
                         new_ids: set[str],
                         ctx: silver.DerivationContext) -> None:
    """Flag previously-derived docs that a re-derivation no longer emits.

    A version bump can change R1 split topology (new child doc_ids).
    Stale children keep their old derivation and decisions, but are
    flagged re_review so the Operator disposes them -- silently keeping
    a validated stale child would double-count once the new children
    validate (W3's L3 is the second line of defense).
    """
    for stale_id in sorted(old_ids - new_ids):
        st = store.get(stale_id)
        if st is None or st.re_review:
            continue
        arts = store.get_artifacts(stale_id)
        bronze_hash = arts[0]["bronze_hash"] if arts else st.source_sha256
        if st.status in (lifecycle.VALIDATED, lifecycle.REREVIEW):
            # R13: a superseded validated doc goes through re_extract ->
            # rereview (validated values kept), not a bare flag flip.
            res = _fire_reextract(store, st, True,
                                  reason="derivation-superseded")
            if not res.noop:
                _persist_silver_doc(store, st,
                                    _stored_derivation(store, st, ctx),
                                    bronze_hash)
        else:
            st.re_review = True
            st.status_reason = "derivation-superseded"
            _persist_silver_doc(store, st,
                                _stored_derivation(store, st, ctx),
                                bronze_hash)


def _ingest_file_medallion(path: Path, source_bytes: bytes, suffix: str,
                           store: DocumentStore, *,
                           hook_notes: list[dict] | None = None,
                           source_root: Path | None = None
                           ) -> list[Document]:
    """One file through the medallion flow (contract section 8).

    sha -> derivation-cache check (I2 no-op on hit) -> R5 PageBundle ->
    bronze steps -> single-txn derive (I7: bronze_text-classify-split-
    extract-silver_doc-artifacts) -> W3 duplicate hooks (advisory).

    ``source_root`` is the ingest root for R15 source identity
    (root-relative path); None when ingesting a lone file.
    """
    sha = hashlib.sha256(source_bytes).hexdigest()
    doc_id = source_doc_id(source_bytes)
    if _derivation_cache_hit(store, sha, path):
        # I2: this bronze is already derived at the current
        # (EXTRACTOR_VERSION, config_hash) -- bump last_seen only. No
        # new rows, no status change, decisions untouched.
        store.register_bronze(sha, len(source_bytes))
        store.add_alias(sha, str(path))
        return _docs_for_bronze(store, sha)
    bundle = _page_bundle_for(path, source_bytes, suffix, store,
                              source_root=source_root)
    try:
        source_mtime = int(path.stat().st_mtime)
    except OSError:
        source_mtime = None
    _register_bronze(store, sha, source_bytes, str(path),
                     encryption=bundle.encryption,
                     source_root=(str(source_root) if source_root else None),
                     source_relpath=_relpath(source_root, path),
                     source_mtime=source_mtime)
    notes: list[dict] = []
    with store.txn():
        old_ids = {d.doc_id for d in _docs_for_bronze(store, sha)}
        if bundle.route in ("blocked", "error"):
            docs = [_blocked_document(path, doc_id, bundle, sha, store)]
        else:
            docs = _build_documents(path, doc_id, bundle, sha, store)
        _mark_stale_children(
            store, old_ids, {d.doc_id for d in docs},
            silver.DerivationContext.current())
    notes.append({"hook": "assess_new_bronze",
                  "outcome": _hook_assess_new_bronze(store, sha)})
    for d in docs:
        notes.append({"hook": "assess_silver_doc", "doc_id": d.doc_id,
                      "outcome": _hook_assess_silver_doc(store, d.doc_id)})
    if hook_notes is not None:
        hook_notes.extend(notes)
    return docs


def ingest_file(path: Path, store: DocumentStore,
                *, source_root: str | Path | None = None) -> list[Document]:
    """Ingest one file; returns the Document(s) created.

    Usually one Document per file. A file holding several form sections
    (consolidated broker 1099, stacked scan) yields one Document per
    section, each with page_range / parent_doc_id; a file whose sections
    cannot be separated honestly yields one MULTI_FORM-blocked Document.

    R4: doc_id derives from the source bytes; re-ingest is idempotent
    and never overwrites validated values (a derivation-version bump
    that disagrees flags re_review). R5: PDFs go through the
    text-sufficiency gate. ``source_root`` feeds R15 source identity
    (root-relative path); None for lone files.
    Raises _SkipFile for skipped files (R6 accounting); other
    exceptions propagate to ingest_dir's errored accounting.
    """
    path = Path(path)
    suffix = path.suffix.lower()
    try:
        source_bytes = path.read_bytes()
    except OSError:
        raise _SkipFile(RC_READ_FAILED)
    if suffix not in PDF_EXTS | TXT_EXTS | IMAGE_EXTS:
        raise _SkipFile(RC_UNSUPPORTED_TYPE)
    root = Path(source_root) if source_root is not None else None
    return _ingest_file_medallion(path, source_bytes, suffix, store,
                                  source_root=root)


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
    # W3 duplicate-assessment hook outcomes per file:
    # [{file, hook, outcome}] -- outcomes are group ids, "ok", or
    # "skipped:<reason>"/"error:<exc>". Never PII (ids/hashes only).
    hook_notes: list[dict] = field(default_factory=list)

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
    # B1: one outer transaction for the whole batch. Per-file txn()
    # calls nest as SAVEPOINTs, so per-file error isolation is
    # preserved: _SkipFile and the error-doc path roll back at most
    # their own savepoint, while a single COMMIT replaces the former
    # per-file fsync fan-out.
    with store.txn():
        for path in files:
            report.files_seen += 1
            report.seen_paths.append(str(path))
            try:
                try:
                    source_bytes = path.read_bytes()
                except OSError:
                    raise _SkipFile(RC_READ_FAILED)
                notes: list[dict] = []
                docs = _ingest_file_medallion(path, source_bytes,
                                              path.suffix.lower(), store,
                                              hook_notes=notes,
                                              source_root=root)
                for n in notes:
                    report.hook_notes.append({"file": _rel(root, path), **n})
            except _SkipFile as skip:
                report.skipped.append({"file": _rel(root, path),
                                       "reason_code": skip.reason_code})
                continue
            except Exception:
                # Reason code, never exception text (R6). The failure is
                # still recorded as a document so nothing is silent. The
                # error document is derived in one txn (I7); its bronze row
                # is registered first so the silver_doc FK always holds.
                reason = RC_EXTRACT_FAILED
                report.errored.append({"file": _rel(root, path),
                                       "reason_code": reason})
                try:
                    source_bytes = path.read_bytes()
                except OSError:
                    source_bytes = None
                if source_bytes is not None:
                    source_sha = hashlib.sha256(source_bytes).hexdigest()
                    doc_id = source_doc_id(source_bytes)
                    try:
                        source_mtime = int(path.stat().st_mtime)
                    except OSError:
                        source_mtime = None
                    _register_bronze(store, source_sha, source_bytes,
                                     str(path), encryption=None,
                                     source_root=str(root),
                                     source_relpath=_relpath(root, path),
                                     source_mtime=source_mtime)
                else:
                    doc_id = source_doc_id(
                        f"unreadable:{path}".encode("utf-8"))
                    source_sha = hashlib.sha256(
                        f"unreadable:{path}".encode("utf-8")).hexdigest()
                    store.register_bronze(source_sha, 0)
                    store.add_alias(source_sha, str(path))
                bundle = PageBundle([], "error", TS_ERROR,
                                     reason_code=reason)
                with store.txn():
                    docs = [_blocked_document(path, doc_id, bundle, source_sha,
                                              store)]
            report.ingested += 1
            report.docs.extend(docs)
    return report


# -- R4: sync -----------------------------------------------------------------

def _doc_source_present(doc: Document, root: Path,
                        seen_paths: set[str]) -> bool:
    """True when the doc's recorded source path exists on disk."""
    sp = doc.source_path
    if not sp:
        return True  # no source recorded: nothing to orphan on
    p = Path(sp)
    if not p.is_absolute():
        p = root / p
    try:
        if str(p.resolve()) in seen_paths:
            return True
    except OSError:
        pass
    return p.exists()


def _bronze_alias_paths(store: DocumentStore, sha: str,
                        docs: list[Document]) -> list[str]:
    """Alias paths recorded for a bronze object.

    Prefers the bronze_alias table (authoritative); falls back to the
    docs' recorded source paths.
    """
    get_bronze = getattr(store, "get_bronze", None)
    if get_bronze is not None:
        try:
            bronze = get_bronze(sha)
        except Exception:
            bronze = None
        if bronze is not None and bronze.get("aliases") is not None:
            return list(bronze["aliases"])
    return [d.source_path for d in docs if d.source_path]


def _bronze_has_on_disk_alias(store: DocumentStore, sha: str,
                              docs: list[Document], root: Path,
                              seen_paths: set[str]) -> bool:
    """True when any recorded alias path for the bronze exists on disk."""
    for alias in _bronze_alias_paths(store, sha, docs):
        p = Path(alias)
        if not p.is_absolute():
            p = root / p
        try:
            if str(p.resolve()) in seen_paths:
                return True
        except OSError:
            pass
        if p.exists():
            return True
    return False


def _mark_orphaned(store: DocumentStore, doc: Document,
                   bronze_hash: str | None) -> None:
    """Flip a silver doc to ORPHANED, preserving values and derivation.

    R13: via the source_missing event (actor=system); validated values
    are untouched (only status/status_reason change). Tombstone/legacy
    docs (no bronze hash) go through the facade upsert, whose bronze
    handling re-attaches them correctly.
    """
    res = _check_transition(
        lifecycle.transition(doc, lifecycle.SOURCE_MISSING,
                             actor=lifecycle.SYSTEM, store=store),
        doc)
    if res.noop:
        return
    if bronze_hash is None:
        store.upsert(doc)
        return
    ctx = _stored_derivation(store, doc,
                             silver.DerivationContext.current())
    _persist_silver_doc(store, doc, ctx, bronze_hash)


def sync(input_dir: str | Path, store: DocumentStore) -> dict:
    """Reconcile the store with a source directory.

    Walks input_dir (idempotent ingest: new files ingested, existing
    re-ingested without clobbering validated values), then applies the
    bronze-level orphan rule: a bronze object with ZERO on-disk alias
    paths has its silver docs flipped to ORPHANED (status +
    status_reason "source-missing"; values preserved). Documents that
    predate bronze tracking fall back to the per-doc source check.

    Returns the ingest accounting plus the orphaned doc_ids.
    """
    root = Path(input_dir)
    report = ingest_dir(root, store)
    seen_ids = {d.doc_id for d in report.docs}
    seen_paths = {str(Path(p).resolve()) for p in report.seen_paths}

    by_bronze: dict[str, list[Document]] = {}
    legacy: list[Document] = []
    for doc in store.list():
        sha = doc.source_sha256
        if sha:
            by_bronze.setdefault(sha, []).append(doc)
        else:
            legacy.append(doc)

    orphaned: list[str] = []
    for sha in sorted(by_bronze):
        docs = by_bronze[sha]
        if any(d.doc_id in seen_ids for d in docs):
            continue  # freshly (re-)ingested this run
        if any(d.status == "ORPHANED" for d in docs):
            continue
        if _bronze_has_on_disk_alias(store, sha, docs, root, seen_paths):
            continue
        for d in docs:
            _mark_orphaned(store, d, sha)
            orphaned.append(d.doc_id)
    for doc in legacy:
        if doc.doc_id in seen_ids:
            continue
        if doc.status == "ORPHANED":
            continue
        if not _doc_source_present(doc, root, seen_paths):
            _mark_orphaned(store, doc, None)
            orphaned.append(doc.doc_id)

    out = report.summary()
    out["orphaned"] = sorted(orphaned)
    return out
