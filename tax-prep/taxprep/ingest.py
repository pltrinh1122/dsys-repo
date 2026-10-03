"""Ingest: walk an input directory, extract text, classify, extract fields.

For each input file:
  - .pdf  -> text via pypdf (fallback: pdfplumber if installed and pypdf
             yields nothing). A same-basename .txt sidecar, when present,
             wins as the OCR text (it is the pre-existing OCR).
  - .txt  -> read directly (a sidecar already claimed by a PDF is skipped).
  - other -> skipped.

Classification and year detection come from extractors.classify_form /
extractors.detect_tax_year. Field extraction routes:
  - transcript form types -> transcript.parse_*_transcript
  - known box forms       -> extractors.extract_fields
  - everything else       -> empty fields, status needs_review.
"""

from __future__ import annotations

import hashlib
import re
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


def _slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s or "doc"


def make_doc_id(source_name: str, text: str) -> str:
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]
    return f"{_slug(Path(source_name).stem)}-{digest}"


def extract_pdf_text(path: Path) -> str:
    """Extract text from a PDF with pypdf; fall back to pdfplumber."""
    text = ""
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception:
        text = ""
    if not text.strip():
        try:
            import pdfplumber  # type: ignore

            with pdfplumber.open(str(path)) as pdf:
                text = "\n".join((page.extract_text() or "") for page in pdf.pages)
        except Exception:
            pass
    return text


def _fields_from_transcript(form_type: str, text: str, year: int | None) -> tuple[dict, str]:
    """Adapt transcript parser output to the Document fields shape."""
    if form_type == "WAGE_INCOME_TRANSCRIPT":
        parsed = transcript.parse_wage_income_transcript(text, tax_year=year)
        fields: dict = {}
        for i, payer in enumerate(parsed.get("payers", [])):
            for box, val in payer.get("boxes", {}).items():
                code = f"payer{i + 1}.{payer.get('payer', 'unknown')}.{box}"
                fields[code] = {
                    "value": val,
                    "confidence": "high",
                    "raw_text": f"{payer.get('form_type', '')} {payer.get('payer', '')} box {box}",
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


def ingest_file(path: Path, store: DocumentStore) -> Document:
    if path.suffix.lower() == ".pdf":
        sidecar = path.with_suffix(".txt")
        if sidecar.exists():
            text = sidecar.read_text(encoding="utf-8", errors="replace")
        else:
            text = extract_pdf_text(path)
        source_path = str(path)
    else:  # .txt
        text = path.read_text(encoding="utf-8", errors="replace")
        source_path = str(path)

    form_type = extractors.classify_form(text)
    year = extractors.detect_tax_year(text)
    doc_id = make_doc_id(path.name, text)

    if form_type in TRANSCRIPT_FORMS:
        fields, status = _fields_from_transcript(form_type, text, year)
    elif form_type in BOX_FORMS:
        fields, status = extractors.extract_fields(form_type, text)
    else:
        fields, status = {}, "needs_review"

    ocr_ref = store.save_ocr(doc_id, text)
    doc = Document(
        doc_id=doc_id,
        tax_year=year,
        form_type=form_type,
        source_path=source_path,
        ocr_text_ref=ocr_ref,
        fields=fields,
        status=status,
    )
    store.upsert(doc)
    return doc


def ingest_dir(input_dir: str | Path, store: DocumentStore) -> list[Document]:
    """Walk input_dir; ingest .pdf and .txt files. Returns ingested Documents."""
    root = Path(input_dir)
    if not root.is_dir():
        raise ValueError(f"not a directory: {input_dir}")

    pdfs = sorted(root.rglob("*.pdf")) + sorted(root.rglob("*.PDF"))
    claimed_sidecars = {p.with_suffix(".txt") for p in pdfs} | {
        p.with_suffix(".TXT") for p in pdfs
    }
    txts = sorted(
        p
        for p in list(root.rglob("*.txt")) + list(root.rglob("*.TXT"))
        if p not in claimed_sidecars
    )

    docs: list[Document] = []
    for path in pdfs + txts:
        try:
            docs.append(ingest_file(path, store))
        except Exception as exc:  # never let one bad file stop the batch
            doc_id = make_doc_id(path.name, str(path))
            ocr_ref = store.save_ocr(doc_id, f"<ingest error: {exc}>")
            doc = Document(
                doc_id=doc_id,
                tax_year=None,
                form_type="UNKNOWN",
                source_path=str(path),
                ocr_text_ref=ocr_ref,
                fields={},
                status="needs_review",
            )
            store.upsert(doc)
            docs.append(doc)
    return docs
