"""Source-evidence layer for the review UI (R19/R19a).

Consumes per-field geometry recorded at extraction (the sibling R15-P4
contract) and derives everything the evidence pane needs:

* page images rendered from the immutable bronze bytes,
* bounding-box overlays (PDF units -> rendered pixels),
* one snapshot crop PER FIELD (the cell within its row context),
* lineage views for computed fields,
* explicit "no visual evidence" states (fail-closed, never nearest-guess).

Geometry contract (recorded at extraction by the R15 sibling,
``taxprep/provenance.py``; consumed here, never re-derived)::

    # stored as field["provenance"] ("geometry" also accepted -- same shape)
    {"page": int,             # 0-based, document-relative (see doc_page_window)
     "bbox_pdf": [x0, y0, x1, y1] | None,  # PDF points, origin bottom-left
     "bbox_source": "pdfplumber" | "tesseract" | "acroform" | None,
     "char_span": {...} | None,
     "extractor": "<name>:<version>"}

If geometry is absent (or invalid, or bbox_pdf None) for a field, the
field is treated as "no visual evidence" -- fail-closed. Crops are
NEVER guessed from text matching.

Privacy: page images and snapshots are PII. They are written ONLY under
``<data_dir>/evidence/`` (dir mode 700, files 600) and served ONLY by the
loopback review server (R10). They never cross the MCP boundary and
never go on the bus -- the blind checks in verify.py see counts only.

Determinism: snapshot cache keys are sha256 over
(bronze_hash, page, bbox, render dpi, extractor version). Re-extraction
with new geometry yields a NEW key, so a crop can never silently drift
after re-extraction -- stale keys are simply never looked up again.
Rendering itself is deterministic given the same poppler build.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from pathlib import Path

from . import silver

try:
    from pdf2image import convert_from_path as _convert_from_path
except ImportError:  # pragma: no cover - exercised via monkeypatch
    _convert_from_path = None

try:
    from pypdf import PdfReader as _PdfReader
except ImportError:  # pragma: no cover - exercised via monkeypatch
    _PdfReader = None

# Page view renders at 110 dpi (matches the historical review pane);
# snapshots render at 220 dpi -- the R19a ">=2x zoom" requirement is met
# by construction (2x the page-view resolution), not by upscaling.
PAGE_DPI = 110
SNAPSHOT_DPI = 220

_BBOX_SOURCES = ("pdfplumber", "tesseract", "acroform")

# Evidence states (R19a narrowing):
#   snapshot    -- extracted field with valid geometry: crop + page box
#   lineage     -- computed field: formula + links to input snapshots
#   edited      -- operator-edited field with geometry: ORIGINAL crop +
#                  the edit record (the image never proves the new value)
#   no_evidence -- fail-closed; reason explains why (never a guess)
STATE_SNAPSHOT = "snapshot"
STATE_LINEAGE = "lineage"
STATE_EDITED = "edited"
STATE_NO_EVIDENCE = "no_evidence"

# no_evidence reasons (stable strings; the UI maps them to human text)
REASON_NO_GEOMETRY = "no_geometry"
REASON_MANUAL_ENTRY = "manual_entry"
REASON_NO_LINEAGE = "no_lineage"
REASON_OUT_OF_BOUNDS = "out_of_bounds"
REASON_SNAPSHOT_FAILED = "snapshot_failed"
REASON_NO_RENDERER = "no_renderer"
REASON_NO_BRONZE = "no_bronze"


# -- geometry consumption (the sibling contract) ---------------------

def valid_geometry(g) -> bool:
    """True when ``g`` is a well-formed geometry record.

    Fail-closed: anything malformed is treated exactly like absent
    geometry -- "no visual evidence", never a nearest guess.
    """
    if not isinstance(g, dict):
        return False
    page = g.get("page")
    if not isinstance(page, int) or isinstance(page, bool) or page < 0:
        return False
    bbox = g.get("bbox_pdf")
    if bbox is not None:
        if (not isinstance(bbox, (list, tuple)) or len(bbox) != 4
                or any(isinstance(v, bool) or not isinstance(v, (int, float))
                       or not math.isfinite(v) for v in bbox)):
            return False
        x0, y0, x1, y1 = bbox
        if not (x0 < x1 and y0 < y1):
            return False
    src = g.get("bbox_source")
    if src is not None and src not in _BBOX_SOURCES:
        return False
    extractor = g.get("extractor")
    if not isinstance(extractor, str) or not extractor.strip():
        return False
    return True


def field_geometry(field: dict) -> dict | None:
    """The field's recorded geometry, or None when absent/invalid.

    Reads the R15 record under ``"provenance"`` (the landed producer
    contract -- provenance.py names "the contract the R19 evidence pane
    consumes") with fallback to ``"geometry"`` (the key named in the R19
    task text). Both carry the identical shape; ``"provenance"`` wins
    when both are present. A record whose bbox_pdf is None carries
    geometry metadata but no locatable region -- also None here (no
    visual evidence, never a guess).
    """
    if not isinstance(field, dict):
        return None
    g = field.get("provenance")
    if g is None:
        g = field.get("geometry")
    if not valid_geometry(g):
        return None
    if g.get("bbox_pdf") is None:
        return None
    return g


def field_lineage(field: dict) -> dict | None:
    """A computed field's lineage, or None.

    Producers mark computed fields (per-lot gain/loss, totals,
    carryforward lines) with::

        {"computed": True, "formula": "1d - 1e + 1g",
         "inputs": ["proceeds", "cost", "adjustment"]}

    Both formula and a non-empty inputs list are required; a computed
    field missing either is a blind-check failure (no silent lineage).
    """
    if not isinstance(field, dict) or field.get("computed") is not True:
        return None
    formula = field.get("formula")
    inputs = field.get("inputs")
    if (not isinstance(formula, str) or not formula.strip()
            or not isinstance(inputs, list) or not inputs
            or not all(isinstance(c, str) and c for c in inputs)):
        return None
    return {"formula": formula, "inputs": list(inputs)}


def is_computed(field: dict) -> bool:
    """True when the producer marked this field computed."""
    return isinstance(field, dict) and field.get("computed") is True


def field_history(field: dict) -> list:
    """The operator edit history (append-only [{ts, old, new}, ...])."""
    if not isinstance(field, dict):
        return []
    h = field.get("history")
    return list(h) if isinstance(h, list) else []


def was_edited(field: dict) -> bool:
    """True when an operator edit replaced an extracted value.

    Operator-ADDED fields (history entry with old=None) are "manually
    added", not "edited" -- they have no original value to show.
    """
    return any(isinstance(e, dict) and e.get("old") is not None
               for e in field_history(field))


def field_evidence(field: dict) -> dict:
    """Classify one field's evidence state (R19a).

    Returns ``{"state", "reason", "geometry", "lineage", "history"}``.
    Pure function of the field dict -- no rendering, no store access.
    Geometry that fails bounds checking is still "snapshot" here; the
    bounds verdict is applied at snapshot time (fail-closed there).
    """
    hist = field_history(field)
    if is_computed(field):
        lineage = field_lineage(field)
        if lineage is None:
            return {"state": STATE_NO_EVIDENCE,
                    "reason": REASON_NO_LINEAGE,
                    "geometry": None, "lineage": None, "history": hist}
        return {"state": STATE_LINEAGE, "reason": None,
                "geometry": None, "lineage": lineage, "history": hist}
    g = field_geometry(field)
    if was_edited(field):
        if g is None:
            return {"state": STATE_NO_EVIDENCE,
                    "reason": REASON_NO_GEOMETRY,
                    "geometry": None, "lineage": None, "history": hist}
        return {"state": STATE_EDITED, "reason": None,
                "geometry": g, "lineage": None, "history": hist}
    if g is None:
        reason = REASON_NO_GEOMETRY
        if (isinstance(field, dict)
                and (field.get("confidence") == "human-corrected"
                     or any(isinstance(e, dict) and e.get("old") is None
                            for e in hist))):
            reason = REASON_MANUAL_ENTRY
        return {"state": STATE_NO_EVIDENCE, "reason": reason,
                "geometry": None, "lineage": None, "history": hist}
    return {"state": STATE_SNAPSHOT, "reason": None,
            "geometry": g, "lineage": None, "history": hist}


# -- paths & bronze ---------------------------------------------------

def page_range_pair(page_range) -> tuple[int, int] | None:
    """``(first_1based, last_1based)`` for a page range, or None.

    Accepts both shapes found in the wild: ``(2, 3)`` tuples/lists and
    ``"3-5"`` / ``"3"`` strings. None when absent or unparseable --
    callers fall back to the whole-document behavior.
    """
    if page_range is None:
        return None
    if isinstance(page_range, (tuple, list)):
        if len(page_range) != 2:
            return None
        try:
            first, last = int(page_range[0]), int(page_range[1])
        except (ValueError, TypeError):
            return None
    else:
        m = re.match(r"^\s*(\d+)\s*(?:-\s*(\d+)\s*)?$", str(page_range))
        if not m:
            return None
        first = int(m.group(1))
        last = int(m.group(2)) if m.group(2) else first
    return (first, last) if 1 <= first <= last else None


def doc_page_window(doc) -> tuple[int, int | None]:
    """The document's page window into the bronze PDF.

    Returns ``(offset_0based, count_or_None)``. ``Document.page_range``
    ("3-5" or "3", 1-based) selects the window; absent or unparseable
    means the whole bronze is the document's page sequence.

    Geometry pages are DOCUMENT-relative (0-based): the bronze page is
    ``offset + geom_page``. This is the frame the sibling R15-P4
    workstream should confirm -- split children extract from their
    section, so section-relative indexing is the only consistent
    reading; non-split docs are unaffected (offset 0).
    """
    pair = page_range_pair(getattr(doc, "page_range", None))
    if pair is not None:
        return pair[0] - 1, pair[1] - pair[0] + 1
    return 0, None


def bronze_page_for(doc, geom_page: int) -> int:
    """Map a document-relative geometry page to a bronze page index."""
    offset, _ = doc_page_window(doc)
    return offset + geom_page

def _mkdir_700(path: Path) -> None:
    """mkdir -p where EVERY created level is mode 700.

    A single chmod on the leaf is not enough: intermediate levels would
    inherit the umask default and leak directory listings.
    """
    path = Path(path)
    missing: list[Path] = []
    probe = path
    while not probe.exists():
        missing.append(probe)
        probe = probe.parent
    path.mkdir(parents=True, exist_ok=True)
    for p in missing:
        try:
            os.chmod(p, 0o700)
        except OSError:
            pass


def evidence_dir(store) -> Path:
    """``<data_dir>/evidence`` -- the ONLY home of page images/snapshots.

    Created mode 700 (PII). Mirrors the bronze dir's posture: the
    review server is the sole reader.
    """
    d = Path(store.data_dir) / "evidence"
    _mkdir_700(d)
    return d


def bronze_path_for_doc(store, doc) -> Path | None:
    """Filesystem path of the doc's immutable bronze bytes, or None."""
    sha = silver.bronze_hash_for_doc(store, doc)
    if not sha:
        return None
    p = Path(store.data_dir) / "bronze" / sha[:2] / sha
    return p if p.exists() else None


def _is_pdf(path: Path) -> bool:
    try:
        with open(path, "rb") as fh:
            return fh.read(5) == b"%PDF-"
    except OSError:
        return False


def bronze_mime(bronze_path: Path) -> tuple[str, str]:
    """(content-type, filename suffix) for bronze bytes, by magic bytes.

    Bronze objects are stored extensionless (content-addressed), so the
    type is sniffed -- never guessed from a name.
    """
    if _is_pdf(bronze_path):
        return "application/pdf", ".pdf"
    return "application/octet-stream", ".bin"


# -- page geometry (vector; no rendering needed) -----------------------

def page_size_pt(bronze_path: Path, page_0based: int) -> tuple | None:
    """(width, height) in PDF points for a 0-based page, or None.

    Pure vector read via pypdf -- no rasterization, so the blind
    bbox-bounds check works even where no renderer is installed.
    """
    if _PdfReader is None:
        return None
    try:
        reader = _PdfReader(str(bronze_path))
        if page_0based >= len(reader.pages):
            return None
        box = reader.pages[page_0based].mediabox
        return (float(box.width), float(box.height))
    except Exception:
        return None


def page_count(bronze_path: Path) -> int | None:
    """Number of pages in the bronze PDF, or None when unreadable."""
    if _PdfReader is None:
        return None
    try:
        return len(_PdfReader(str(bronze_path)).pages)
    except Exception:
        return None


def bbox_within_bounds(bbox_pdf: list, page_size: tuple | None) -> bool | None:
    """True/False when the page size is known; None when it is not.

    None is informational (environmental), never a failure -- the blind
    check reports it separately from out-of-bounds.
    """
    if page_size is None:
        return None
    w, h = page_size
    x0, y0, x1, y1 = bbox_pdf
    return 0 <= x0 and 0 <= y0 and x1 <= w and y1 <= h


def pdf_to_px(bbox_pdf: list, page_h_pt: float, dpi: int) -> tuple[int, int, int, int]:
    """Map a PDF-points bbox (origin bottom-left) to image pixels.

    Returns integer (x0, y0, x1, y1) with the image origin top-left.
    """
    s = dpi / 72.0
    x0, y0, x1, y1 = bbox_pdf
    return (int(round(x0 * s)), int(round((page_h_pt - y1) * s)),
            int(round(x1 * s)), int(round((page_h_pt - y0) * s)))


# -- rendering (raster; cached under the evidence dir) ------------------

def _rendered_page_path(store, bronze_hash: str, page: int, dpi: int) -> Path:
    return (evidence_dir(store) / bronze_hash
            / "pages" / f"page_{page}_{dpi}.jpg")


def render_page(store, doc, page_0based: int,
                dpi: int = PAGE_DPI) -> tuple[Path | None, str | None]:
    """Render one bronze page to a cached JPEG. Returns (path, error).

    Deterministic: the same (bronze bytes, page, dpi) always yields the
    same bytes, so the cache is keyed by content hash, not by time.
    Never synthesizes a page -- every failure mode returns (None, reason)
    and the UI degrades to the no-evidence state.
    """
    bronze_path = bronze_path_for_doc(store, doc)
    if bronze_path is None:
        return None, REASON_NO_BRONZE
    if not _is_pdf(bronze_path):
        return None, "not a PDF source"
    sha = silver.bronze_hash_for_doc(store, doc)
    out = _rendered_page_path(store, sha, page_0based, dpi)
    if out.exists():
        return out, None
    if _convert_from_path is None:
        return None, REASON_NO_RENDERER
    try:
        images = _convert_from_path(str(bronze_path), dpi=dpi,
                                    first_page=page_0based + 1,
                                    last_page=page_0based + 1)
        if not images:
            return None, "page render produced no image"
        img = images[0]
    except Exception:
        return None, REASON_SNAPSHOT_FAILED
    _mkdir_700(out.parent)
    img.save(out, format="JPEG", quality=80)
    os.chmod(out, 0o600)
    return out, None


def snapshot_cache_key(*, bronze_hash: str, page: int, bbox_pdf: list,
                       dpi: int, extractor: str) -> str:
    """Deterministic snapshot key (R19a narrowing (2)).

    Keyed by the CURRENT geometry: re-extraction that moves a box
    produces a different key, so a crop can never drift out from under
    its field. Bbox coordinates round to 3dp for key stability.
    """
    canon = json.dumps({
        "bronze_hash": bronze_hash,
        "page": page,
        "bbox": [round(float(v), 3) for v in bbox_pdf],
        "dpi": dpi,
        "extractor": extractor,
    }, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canon.encode("ascii")).hexdigest()[:16]


def padded_crop_pt(bbox_pdf: list, page_size: tuple) -> tuple[float, float, float, float]:
    """The snapshot crop region in PDF points: the cell in its row context.

    Rule (documented, deterministic): x pads 10% of the page width each
    side; y expands to max(3x the cell height, 36pt) centered on the cell
    -- the row the cell sits in stays visible (R19a narrowing (5)).
    Clamped to the page.
    """
    w, h = page_size
    x0, y0, x1, y1 = (float(v) for v in bbox_pdf)
    xpad = 0.10 * w
    x0p = max(0.0, x0 - xpad)
    x1p = min(float(w), x1 + xpad)
    cy = (y0 + y1) / 2.0
    half = max(1.5 * (y1 - y0), 18.0)
    y0p = max(0.0, cy - half)
    y1p = min(float(h), cy + half)
    return (x0p, y0p, x1p, y1p)


def field_snapshot(store, doc, field_code: str,
                   dpi: int = SNAPSHOT_DPI) -> tuple[Path | None, str | None]:
    """Derive (or fetch from cache) one field's snapshot crop.

    Returns (path, error). Fail-closed at every step: no geometry, no
    bronze, no renderer, out-of-bounds bbox, or a render failure all
    return (None, reason) -- never a guessed or placeholder image.
    """
    fields = getattr(doc, "fields", None) or {}
    field = fields.get(field_code)
    ev = field_evidence(field if isinstance(field, dict) else {})
    g = ev["geometry"]
    if g is None:
        return None, ev["reason"] or REASON_NO_GEOMETRY
    bronze_path = bronze_path_for_doc(store, doc)
    if bronze_path is None:
        return None, REASON_NO_BRONZE
    page = bronze_page_for(doc, g["page"])
    size = page_size_pt(bronze_path, page)
    bounds = bbox_within_bounds(g["bbox_pdf"], size)
    if bounds is False:
        return None, REASON_OUT_OF_BOUNDS
    if _convert_from_path is None:
        return None, REASON_NO_RENDERER
    page_path, err = render_page(store, doc, page, dpi=dpi)
    if page_path is None:
        return None, err or REASON_SNAPSHOT_FAILED
    sha = silver.bronze_hash_for_doc(store, doc)
    key = snapshot_cache_key(bronze_hash=sha, page=page,
                             bbox_pdf=g["bbox_pdf"], dpi=dpi,
                             extractor=g["extractor"])
    out = evidence_dir(store) / sha / "snaps" / f"{key}.jpg"
    if out.exists():
        return out, None
    try:
        from PIL import Image
        img = Image.open(page_path)
        if size is None:
            # Bounds were unknown; fall back to the rendered pixel size
            # for the y-flip (the crop is still exactly the padded bbox).
            w_px, h_px = img.size
            page_size = (w_px * 72.0 / dpi, h_px * 72.0 / dpi)
        else:
            page_size = size
        crop_pt = padded_crop_pt(g["bbox_pdf"], page_size)
        x0, y0, x1, y1 = pdf_to_px(crop_pt, page_size[1], dpi)
        w_px, h_px = img.size
        x0, y0 = max(0, x0), max(0, y0)
        x1, y1 = min(w_px, x1), min(h_px, y1)
        if x1 <= x0 or y1 <= y0:
            return None, REASON_SNAPSHOT_FAILED
        crop = img.crop((x0, y0, x1, y1))
    except Exception:
        return None, REASON_SNAPSHOT_FAILED
    _mkdir_700(out.parent)
    crop.save(out, format="JPEG", quality=82)
    os.chmod(out, 0o600)
    return out, None


# -- "verified against original" (fail-closed escape hatch) -------------

_VERIFY_ORIGINAL_KIND = "verify_original"


def verify_original_recorded(store, doc_id: str, field_code: str) -> bool:
    """True when the Operator recorded "verified against original".

    Scans the append-only decision log for a matching verify_original
    entry (kind added to mstore._DECISION_KINDS by this workstream).
    """
    try:
        rows = store.decisions_for(doc_id=doc_id, kind=_VERIFY_ORIGINAL_KIND)
    except Exception:
        return False
    for r in rows or []:
        payload = r.get("payload")
        if payload is None:
            try:
                payload = json.loads(r.get("payload_json") or "{}")
            except (ValueError, TypeError, AttributeError):
                continue
        if isinstance(payload, dict) and payload.get("field") == field_code:
            return True
    return False


def record_verify_original(store, doc_id: str, field_code: str) -> int:
    """Log the Operator's explicit "verified against original" verdict.

    Returns the decision seq. This is the ONLY way to confirm a field
    that has no visual evidence -- and the record is permanent.
    """
    return store.log_decision(
        actor="operator", kind=_VERIFY_ORIGINAL_KIND, doc_id=doc_id,
        payload={"field": field_code, "verdict": "verified_against_original"})
