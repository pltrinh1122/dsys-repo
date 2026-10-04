"""R15 field provenance: geometry + source-span records (Arc C, W2).

Every extracted field carries a ``provenance`` dict in exactly this shape::

    {"page": int,             # 0-based page into the source's per-page text
     "bbox_pdf": [x0, y0, x1, y1] | None,  # PDF points, bottom-left origin
     "bbox_source": "pdfplumber" | "tesseract" | "acroform" | None,
     "char_span": {"page": int, "start": int, "end": int} | None,
     "extractor": "<name>:<version>"}

It is recorded at extraction time, stored on the silver artifact
(``silver_artifact.offsets_json``) and mirrored in ``Document.fields``
metadata -- the contract the R19 evidence pane consumes.

Geometry is PII-adjacent (positions, not values): it is stripped from
every MCP/bus (blind-orchestrator) output.

Geometry sources, tried in this order by :class:`GeometryResolver`:

- ``acroform`` -- an AcroForm widget rect, used only when the field's
  raw_text is exactly the appended ``"name: value"`` form line
  (fillable forms).
- ``pdfplumber`` -- word boxes from the native PDF's text layer,
  aligned to the field's character span by word-subsequence matching.
- ``tesseract`` -- TSV word boxes from the OCR engine, same alignment.

Anything that cannot be aligned records ``(None, None)``: positions are
never guessed. In particular the regex extractors over .txt / sidecar
text cannot produce bboxes at all (no layout source exists), and record
``bbox_pdf=None, bbox_source=None`` with only the char_span.
"""

from __future__ import annotations

from pathlib import Path

# bbox_source vocabulary (mirrors the contract shape).
BBOX_PDFPLUMBER = "pdfplumber"
BBOX_TESSERACT = "tesseract"
BBOX_ACROFORM = "acroform"


def make_provenance(*, page: int, bbox_pdf, bbox_source,
                    char_span, extractor: str) -> dict:
    """Build one provenance dict in exactly the R15 contract shape."""
    return {
        "page": page,
        "bbox_pdf": bbox_pdf,
        "bbox_source": bbox_source,
        "char_span": char_span,
        "extractor": extractor,
    }


# -- page maps -----------------------------------------------------------

def page_spans_for_joined(pages: list[str]) -> list[tuple[int, int, int]]:
    """``(page_1based, start, end)`` spans for ``"\\n".join(pages)``.

    Lets offsets in joined text translate back to per-page offsets
    without losing page boundaries.
    """
    spans: list[tuple[int, int, int]] = []
    pos = 0
    for i, page in enumerate(pages):
        spans.append((i + 1, pos, pos + len(page)))
        pos += len(page) + 1  # the "\n" join separator
    return spans


def offset_to_page(page_spans: list[tuple[int, int, int]],
                   offset: int) -> tuple[int, int] | None:
    """``(page_0based, page_offset)`` for an offset, or None.

    ``page_spans`` entries are ``(page_1based, start, end)`` over the
    extraction text (see extractors.FormSection.page_spans).
    """
    for pageno, start, end in page_spans or []:
        if start <= offset < end:
            return (pageno - 1, offset - start)
    return None


# -- word-box geometry ----------------------------------------------------

def _union(bboxes: list[list[float]]) -> list[float]:
    return [
        round(min(b[0] for b in bboxes), 2),
        round(min(b[1] for b in bboxes), 2),
        round(max(b[2] for b in bboxes), 2),
        round(max(b[3] for b in bboxes), 2),
    ]


def bbox_for_word_subsequence(words: list[dict],
                              span_text: str) -> list[float] | None:
    """Union bbox of the word subsequence matching ``span_text``.

    ``words`` are ``{"text": str, "bbox": [x0,y0,x1,y1]}`` in reading
    order. The span's words must appear as a contiguous subsequence
    (case-insensitive); otherwise None -- never guessed.
    """
    targets = [t for t in span_text.split() if t]
    if not targets:
        return None
    texts = [w.get("text", "") for w in words]
    n, m = len(texts), len(targets)
    lowered = [t.lower() for t in targets]
    for i in range(n - m + 1):
        if all(texts[i + k].lower() == lowered[k] for k in range(m)):
            return _union([words[i + k]["bbox"] for k in range(m)])
    return None


def pdfplumber_page_words(pdf_path: str | Path,
                          page_0: int) -> list[dict] | None:
    """Word boxes for one PDF page via pdfplumber, or None.

    Each word is ``{"text": str, "bbox": [x0,y0,x1,y1]}`` with the bbox
    in PDF points, bottom-left origin. None when pdfplumber is
    unavailable or the page cannot be read (e.g. user-encrypted).
    """
    try:
        import pdfplumber  # type: ignore
    except ImportError:
        return None
    try:
        with pdfplumber.open(str(pdf_path), password="") as pdf:
            page = pdf.pages[page_0]
            height = float(page.height)
            out = []
            for w in page.extract_words():
                out.append({
                    "text": w["text"],
                    "bbox": [
                        round(float(w["x0"]), 2),
                        round(height - float(w["bottom"]), 2),
                        round(float(w["x1"]), 2),
                        round(height - float(w["top"]), 2),
                    ],
                })
            return out
    except Exception:
        return None


def words_from_tsv(tsv_text: str, page_width_px: int,
                   page_height_px: int, dpi: int = 300) -> list[dict]:
    """Parse tesseract TSV word rows into word boxes.

    Each word is ``{"text": str, "bbox": [x0,y0,x1,y1], "conf": float}``
    with the bbox in PDF points, bottom-left origin. Only word-level
    rows (level 5) with non-blank text are kept. Pure function -- no
    binary needed, unit-testable with synthetic TSV.
    """
    words: list[dict] = []
    lines = (tsv_text or "").splitlines()
    if not lines:
        return words
    k = 72.0 / dpi  # px -> PDF points
    for line in lines[1:]:  # skip the header row
        parts = line.rstrip("\n").split("\t")
        if len(parts) < 12:
            continue
        try:
            level = int(parts[0])
        except ValueError:
            continue
        if level != 5:
            continue
        try:
            left, top = int(parts[6]), int(parts[7])
            width, height = int(parts[8]), int(parts[9])
            conf = float(parts[10])
        except ValueError:
            continue
        text = parts[11]
        if not text.strip():
            continue
        x0, x1 = left * k, (left + width) * k
        y1 = (page_height_px - top) * k
        y0 = (page_height_px - (top + height)) * k
        words.append({
            "text": text,
            "bbox": [round(x0, 2), round(y0, 2), round(x1, 2),
                     round(y1, 2)],
            "conf": conf,
        })
    return words


class GeometryResolver:
    """Resolves ``(bbox_pdf, bbox_source)`` for a field span.

    Configured per ingest bundle: ``pdf_path`` enables the pdfplumber
    source (native text), ``ocr_words`` (``{page_0: [word, ...]}``) the
    tesseract source (OCR text), ``acroform_rects``
    (``{name: {"page": p0, "bbox": [...], "line": "name: value"}}``) the
    acroform source (fillable forms). Sources are tried in contract
    order; the first hit wins, else ``(None, None)``.
    """

    def __init__(self, *, pdf_path: str | Path | None = None,
                 ocr_words: dict | None = None,
                 acroform_rects: dict | None = None) -> None:
        self._pdf_path = Path(pdf_path) if pdf_path else None
        self._ocr_words = ocr_words or {}
        self._acroform_rects = acroform_rects or {}
        self._word_cache: dict[int, list[dict] | None] = {}

    def _plumber_words(self, page_0: int) -> list[dict] | None:
        if page_0 not in self._word_cache:
            self._word_cache[page_0] = (
                pdfplumber_page_words(self._pdf_path, page_0)
                if self._pdf_path is not None else None
            )
        return self._word_cache[page_0]

    def resolve(self, page_0: int, page_text: str,
                start: int, end: int,
                raw_text: str | None) -> tuple[list | None, str | None]:
        """``(bbox_pdf, bbox_source)`` for a char span, else ``(None, None)``."""
        # acroform: the field's raw_text is exactly an appended form line.
        stripped = (raw_text or "").strip()
        if stripped and self._acroform_rects:
            for _name, rect in self._acroform_rects.items():
                if rect.get("page") == page_0 and stripped == rect.get("line"):
                    return list(rect["bbox"]), BBOX_ACROFORM
        # word-box sources align the span's words to engine word boxes.
        span_text = ""
        if page_text and 0 <= start <= end <= len(page_text):
            span_text = page_text[start:end]
        if span_text.strip():
            words = self._plumber_words(page_0)
            if words:
                bbox = bbox_for_word_subsequence(words, span_text)
                if bbox is not None:
                    return bbox, BBOX_PDFPLUMBER
            words = self._ocr_words.get(page_0)
            if words:
                bbox = bbox_for_word_subsequence(words, span_text)
                if bbox is not None:
                    return bbox, BBOX_TESSERACT
        return None, None


# -- extraction-time attachment --------------------------------------------

def _provenance_for_span(span, page_spans, extractor: str,
                         geometry: GeometryResolver,
                         page_texts: list[str],
                         raw_text: str | None) -> dict:
    """One provenance dict for an extraction-text span (or lack of one)."""
    char_span = None
    page_0 = 0
    bbox, source = None, None
    if span is not None:
        start, end = span
        first = offset_to_page(page_spans, start)
        last = offset_to_page(page_spans, end - 1) if end > start else first
        if (first is not None and last is not None
                and first[0] == last[0]):
            page_0 = first[0]
            page_start, page_end = first[1], last[1] + 1
            char_span = {"page": page_0, "start": page_start,
                         "end": page_end}
            page_text = (page_texts[page_0]
                         if 0 <= page_0 < len(page_texts) else "")
            bbox, source = geometry.resolve(page_0, page_text, page_start,
                                            page_end, raw_text)
    return make_provenance(page=page_0, bbox_pdf=bbox, bbox_source=source,
                           char_span=char_span, extractor=extractor)


def attach_field_provenance(fields: dict, page_spans,
                            extractor: str, geometry: GeometryResolver,
                            page_texts: list[str]) -> dict:
    """Replace transient extraction spans with R15 provenance dicts.

    Each field entry carrying ``_extract_span`` (an ``(start, end)`` span
    in extraction-text coordinates, recorded by the extractor) gets a
    ``provenance`` dict in the contract shape; the transient keys are
    removed so they never persist. Entries without a span still get a
    provenance record (char_span/bbox None) naming the extractor.
    1099-B ``lots`` entries additionally map ``_lot_spans`` to
    ``lot_provenance`` (one provenance dict per lot, in lot order) for
    the per-lot silver artifacts.
    """
    for _key, entry in (fields or {}).items():
        if not isinstance(entry, dict):
            continue
        span = entry.pop("_extract_span", None)
        lot_spans = entry.pop("_lot_spans", None)
        entry["provenance"] = _provenance_for_span(
            span, page_spans, extractor, geometry, page_texts,
            entry.get("raw_text"))
        if lot_spans:
            entry["lot_provenance"] = [
                _provenance_for_span(s, page_spans, extractor, geometry,
                                     page_texts, None)
                for s in lot_spans
            ]
    return fields
