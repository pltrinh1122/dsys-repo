"""Local OCR engine (tax-prep R5) behind a stable interface.

This module is the OCR engine only. A follow-up agent wires it into ``ingest.py``
(the R5 text-sufficiency gate); nothing here touches ingest, extraction, or the
store.

Interface contract (load-bearing -- import these names with exactly these
signatures and return shapes):

    available() -> bool
        True iff a usable OCR binary is on PATH (``ocrmypdf`` directly, else
        ``tesseract``). Never raises.

    engine_info() -> dict
        {"engine": "ocrmypdf" | "tesseract" | None,
         "version": str | None,
         "available": bool}
        Never raises, even when no binary is present.

    ocr_pdf(src: Path, mode: str, work_dir: Path) -> dict
        Run OCR on one PDF. ``mode`` is one of "skip-text", "redo-ocr",
        "force-ocr" and maps to the ocrmypdf flag of the same name (plus
        --deskew --rotate-pages --sidecar). Returns:
        {"ok": bool, "text": str, "mean_confidence": float | None,
         "attempts": [attempt, ...], "reason_code": str | None,
         "engine": str | None, "engine_version": str | None}
        where one attempt is
        {"mode": str, "engine": str | None, "engine_version": str | None,
         "ok": bool, "chars": int, "mean_confidence": float | None,
         "reason_code": str | None}.
        ``ocr_pdf`` itself always returns exactly one attempt record.
        Never modifies ``src``. All outputs go under ``work_dir``.

    ocr_with_escalation(src: Path, work_dir: Path,
                        candidate_modes: list[str]) -> dict
        Pure orchestration over ``ocr_pdf``: tries ``candidate_modes`` in order,
        keeps the best result by text-quality heuristic (more extracted chars
        wins; ties keep the earlier mode), and records every attempt in
        "attempts". Same return shape as ``ocr_pdf``.

Required binaries (documented per the R5 build request; assume no sudo):

    ocrmypdf      Primary driver. Python package ``ocrmypdf`` (pip extra
                  ``.[ocr]``); ships a console script of the same name. Its own
                  system prerequisites: tesseract, Ghostscript; optional
                  qpdf / unpaper / pngquant (absent on the workstation, fine).
                  Preferred when present: it bundles deskew/rotation and
                  writes both the OCR'd PDF and a text sidecar.
    tesseract     Fallback: invoked directly on rendered page images when
                  ocrmypdf is absent. Workstation has Tesseract 5.3.4 (eng).
    pdftoppm      (poppler-utils) Rasterizes PDF pages to PNG for the tesseract
                  fallback. Present on the workstation. If tesseract is
                  present but pdftoppm is not, the fallback cannot run and
                  ocr_pdf fails with reason_code "render_unavailable".
    pypdf         Python library (already a hard dependency): encryption
                  detection and per-page text checks. No binary needed.

Degradation notes:
  * With ocrmypdf, all three modes run with --deskew --rotate-pages --sidecar;
    the plain-text sidecar carries no per-word confidence, so
    mean_confidence is None on that path.
  * With the tesseract fallback, pages are rasterized at 300 dpi and each page
    is OCR'd via ``tesseract page.png out tsv txt``; mean_confidence is the
    mean of per-word TSV confidences (conf == -1 entries excluded). In this
    fallback, "redo-ocr" and "force-ocr" are equivalent (every page is OCR'd);
    only ocrmypdf distinguishes them via its handling of the existing text
    layer. For "skip-text", pages already carrying >= _SKIP_TEXT_MIN_CHARS
    non-whitespace characters are not rendered.

Failure policy:
  * reason_code is one of: "engine_missing", "encrypted", "source_missing",
    "invalid_mode", "ocr_failed", "render_unavailable", "ocr_timeout".
    It is a stable code, never exception text (R6).
  * Encrypted PDFs are detected with pypdf; the empty password is tried
    first. Owner-password-only PDFs (empty user password) proceed: the
    engine is handed an unencrypted copy in the private TMPDIR. PDFs that
    still need a USER password are refused with reason_code "encrypted"
    (BLOCKED-encrypted). The Operator decrypts those; passwords are never
    handled here.
  * A private TMPDIR is created inside ``work_dir`` (mode 0700) for every
    run; engine subprocesses inherit it. Temp files (rendered pages, TSVs)
    are removed afterwards. Files and directories this module creates use
    mode 0700/0600 (umask 077 in engine child processes). The OCR'd PDF and
    sidecar are kept under ``work_dir`` as
    ``ocr_<sha256(src)[:16]>_<mode>.pdf`` / ``.txt`` (content-derived names;
    no filename stem leaks into the data dir).

Fully local: no network, no cloud OCR, no LLM vision. Deterministic apart
from engine-internal behavior (tesseract itself is deterministic for a fixed
binary and input).
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from pypdf import PdfReader, PdfWriter

# Modes accepted by ocr_pdf / ocr_with_escalation.
MODES = ("skip-text", "redo-ocr", "force-ocr")

# ocrmypdf flag for each mode; always combined with --deskew --rotate-pages
# --sidecar (see module docstring).
MODE_FLAGS = {
    "skip-text": ("--skip-text",),
    "redo-ocr": ("--redo-ocr",),
    "force-ocr": ("--force-ocr",),
}

# Reason codes (stable strings; never exception text).
RC_ENGINE_MISSING = "engine_missing"
RC_ENCRYPTED = "encrypted"
RC_SOURCE_MISSING = "source_missing"
RC_INVALID_MODE = "invalid_mode"
RC_OCR_FAILED = "ocr_failed"
RC_RENDER_UNAVAILABLE = "render_unavailable"
RC_TIMEOUT = "ocr_timeout"

# Tesseract-fallback page selection: pages with at least this many
# non-whitespace characters are considered to already have text and are
# skipped under mode "skip-text".
_SKIP_TEXT_MIN_CHARS = 20

# Subprocess timeouts (seconds).
_OCR_TIMEOUT = 600
_RENDER_TIMEOUT = 120
_TESSERACT_PAGE_TIMEOUT = 120
_VERSION_TIMEOUT = 30

_DPI = 300


def _make_attempt(mode, engine, engine_version, ok, chars, mean_confidence,
                  reason_code):
    return {
        "mode": mode,
        "engine": engine,
        "engine_version": engine_version,
        "ok": ok,
        "chars": chars,
        "mean_confidence": mean_confidence,
        "reason_code": reason_code,
    }


def _find_engine():
    """Return (name, path) of the preferred OCR binary, or (None, None)."""
    for name in ("ocrmypdf", "tesseract"):
        path = shutil.which(name)
        if path:
            return name, path
    return None, None


def _binary_version(name):
    """Best-effort version string for an engine binary; None on any failure."""
    try:
        proc = subprocess.run(
            [name, "--version"],
            capture_output=True,
            text=True,
            timeout=_VERSION_TIMEOUT,
        )
        out = (proc.stdout or "").strip()
        if name == "tesseract":
            m = re.search(r"tesseract\s+([\w.\-]+)", out)
            return m.group(1) if m else None
        # ocrmypdf --version prints e.g. "16.12.0"; be tolerant of prefixes.
        m = re.search(r"(\d+\.\d+(?:\.\d+)?)", out)
        return m.group(1) if m else None
    except Exception:
        return None


def available() -> bool:
    """True iff a usable OCR binary (ocrmypdf or tesseract) is on PATH."""
    name, _ = _find_engine()
    return name is not None


def engine_info() -> dict:
    """Describe the OCR engine; never raises when binaries are absent."""
    name, _ = _find_engine()
    return {
        "engine": name,
        "version": _binary_version(name) if name else None,
        "available": name is not None,
    }


def _is_encrypted(src: Path):
    """True if the PDF is encrypted, False if not, None if unreadable."""
    try:
        return bool(PdfReader(str(src)).is_encrypted)
    except Exception:
        return None


def _user_password_required(src: Path) -> bool:
    """True when src is a PDF that still needs a USER password after the
    empty password is tried; False when the PDF is open or owner-password-
    only (empty password unlocks it). False on unreadable files too --
    those were never refused here and still aren't (the engine-missing /
    render gates handle them downstream)."""
    try:
        reader = PdfReader(str(src))
    except Exception:
        return False
    try:
        if not reader.is_encrypted:
            return False
    except Exception:
        return False
    try:
        return not bool(reader.decrypt(""))
    except Exception:
        return True


def _decrypted_copy(src: Path, dest: Path) -> bool:
    """Write an unencrypted copy of an owner-password-only PDF to ``dest``.

    ``src`` is never modified. Returns False when a user password is
    required or anything fails (the caller refuses with RC_ENCRYPTED).
    """
    try:
        reader = PdfReader(str(src))
        if reader.is_encrypted and not reader.decrypt(""):
            return False
        writer = PdfWriter()
        for page in reader.pages:
            writer.add_page(page)
        with open(dest, "wb") as fh:
            writer.write(fh)
        return True
    except Exception:
        return False


def _ensure_private_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    # mkdir(mode=...) is a no-op for existing dirs; tighten if we created it
    # with a wider mode due to a permissive umask.
    try:
        st = path.stat()
        if st.st_mode & 0o077:
            os.chmod(path, st.st_mode & ~0o077)
    except OSError:
        pass


def _sha_prefix(src: Path) -> str:
    h = hashlib.sha256()
    with open(src, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def _fail(mode, reason_code, attempts=()):
    return {
        "ok": False,
        "text": "",
        "mean_confidence": None,
        "attempts": list(attempts),
        "reason_code": reason_code,
        "engine": None,
        "engine_version": None,
    }


def _pages_needing_ocr(src: Path, mode: str):
    """1-based page numbers to OCR under the tesseract fallback."""
    reader = PdfReader(str(src))
    pages = list(range(1, len(reader.pages) + 1))
    if mode in ("redo-ocr", "force-ocr"):
        return pages
    selected = []
    for i, page in zip(pages, reader.pages):
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        if len("".join(text.split())) < _SKIP_TEXT_MIN_CHARS:
            selected.append(i)
    return selected


def _mean_confidence_from_tsv(tsv_path: Path):
    """Mean per-word confidence from a tesseract TSV file; None if no words."""
    confs = []
    try:
        with open(tsv_path, "r", encoding="utf-8", errors="replace") as f:
            header = f.readline()  # skip header row
            if not header:
                return None
            for line in f:
                parts = line.rstrip("\n").split("\t")
                if len(parts) < 11:
                    continue
                try:
                    conf = float(parts[10])
                except ValueError:
                    continue
                if conf >= 0:
                    confs.append(conf)
    except OSError:
        return None
    if not confs:
        return None
    return sum(confs) / len(confs)


def _run_ocrmypdf(src, mode, work_dir, tmp, engine_version):
    """Run ocrmypdf with --deskew --rotate-pages --sidecar; return result."""
    digest = _sha_prefix(src)
    out_pdf = work_dir / f"ocr_{digest}_{mode}.pdf"
    sidecar = work_dir / f"ocr_{digest}_{mode}.txt"
    cmd = [
        "ocrmypdf",
        *MODE_FLAGS[mode],
        "--deskew",
        "--rotate-pages",
        "--sidecar", str(sidecar),
        str(src),
        str(out_pdf),
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=_OCR_TIMEOUT,
            cwd=str(tmp),
            env={**os.environ, "TMPDIR": str(tmp)},
            preexec_fn=lambda: os.umask(0o077),
        )
    except subprocess.TimeoutExpired:
        reason = RC_TIMEOUT
        ok, text, conf = False, "", None
    except Exception:
        reason = RC_OCR_FAILED
        ok, text, conf = False, "", None
    else:
        if proc.returncode != 0 or not sidecar.exists():
            reason = RC_OCR_FAILED
            ok, text, conf = False, "", None
        else:
            try:
                text = sidecar.read_text(encoding="utf-8", errors="replace")
            except OSError:
                text = ""
            # Plain-text sidecar carries no per-word confidence.
            ok, conf, reason = True, None, None
    attempt = _make_attempt(mode, "ocrmypdf", engine_version, ok, len(text),
                            conf, reason)
    return {
        "ok": ok,
        "text": text,
        "mean_confidence": conf,
        "attempts": [attempt],
        "reason_code": reason,
        "engine": "ocrmypdf",
        "engine_version": engine_version,
    }


def _run_tesseract(src, mode, work_dir, tmp, engine_version):
    """Fallback: pdftoppm renders pages, tesseract OCRs them directly."""
    if shutil.which("pdftoppm") is None:
        return _fail(mode, RC_RENDER_UNAVAILABLE, [
            _make_attempt(mode, "tesseract", engine_version, False, 0, None,
                          RC_RENDER_UNAVAILABLE)])
    try:
        pages = _pages_needing_ocr(src, mode)
    except Exception:
        return _fail(mode, RC_OCR_FAILED, [
            _make_attempt(mode, "tesseract", engine_version, False, 0, None,
                          RC_OCR_FAILED)])

    def fail(reason):
        return _fail(mode, reason, [
            _make_attempt(mode, "tesseract", engine_version, False, 0, None,
                          reason)])

    if not pages:
        # skip-text on a page set that already has text: nothing to OCR.
        attempt = _make_attempt(mode, "tesseract", engine_version, True, 0,
                                None, None)
        return {
            "ok": True, "text": "", "mean_confidence": None,
            "attempts": [attempt], "reason_code": None,
            "engine": "tesseract", "engine_version": engine_version,
        }

    def render_page(n):
        prefix = tmp / f"page-{n}"
        proc = subprocess.run(
            ["pdftoppm", "-png", "-r", str(_DPI), "-f", str(n), "-l", str(n),
             str(src), str(prefix)],
            capture_output=True, text=True, timeout=_RENDER_TIMEOUT,
            cwd=str(tmp), env={**os.environ, "TMPDIR": str(tmp)},
            preexec_fn=lambda: os.umask(0o077),
        )
        if proc.returncode != 0:
            return None
        png = tmp / f"page-{n}-{n}.png"
        return png if png.exists() else None

    def ocr_page(png, n):
        out = tmp / f"ocr-{n}"
        proc = subprocess.run(
            ["tesseract", str(png), str(out), "tsv", "txt"],
            capture_output=True, text=True, timeout=_TESSERACT_PAGE_TIMEOUT,
            cwd=str(tmp), env={**os.environ, "TMPDIR": str(tmp)},
            preexec_fn=lambda: os.umask(0o077),
        )
        if proc.returncode != 0:
            return "", None
        txt = out.with_suffix(".txt")
        tsv = out.with_suffix(".tsv")
        text = txt.read_text(encoding="utf-8",
                             errors="replace") if txt.exists() else ""
        return text, _mean_confidence_from_tsv(tsv)

    texts, confs = [], []
    try:
        for n in pages:
            png = render_page(n)
            if png is None:
                return fail(RC_OCR_FAILED)
            text, conf = ocr_page(png, n)
            texts.append(text)
            if conf is not None:
                confs.append(conf)
    except subprocess.TimeoutExpired:
        return fail(RC_TIMEOUT)
    except Exception:
        return fail(RC_OCR_FAILED)

    text = "\n\n".join(t.strip() for t in texts).strip()
    mean_conf = sum(confs) / len(confs) if confs else None
    attempt = _make_attempt(mode, "tesseract", engine_version, True, len(text),
                            mean_conf, None)
    return {
        "ok": True,
        "text": text,
        "mean_confidence": mean_conf,
        "attempts": [attempt],
        "reason_code": None,
        "engine": "tesseract",
        "engine_version": engine_version,
    }


def ocr_pdf(src: Path, mode: str, work_dir: Path) -> dict:
    """OCR one PDF; see module docstring for the contract.

    Never modifies ``src``. All outputs go under ``work_dir``. Uses a private
    TMPDIR inside ``work_dir`` and removes it afterwards. Failures return a
    stable reason_code, never exception text.
    """
    src = Path(src)
    work_dir = Path(work_dir)

    if mode not in MODES:
        return _fail(mode, RC_INVALID_MODE)
    if not src.is_file():
        return _fail(mode, RC_SOURCE_MISSING)

    encrypted = _user_password_required(src)
    if encrypted:
        # BLOCKED-encrypted: the Operator decrypts; passwords are never
        # handled here. Owner-password-only files pass this gate: the
        # empty password already unlocked them, and the engine below is
        # handed a decrypted copy.
        return _fail(mode, RC_ENCRYPTED, [
            _make_attempt(mode, None, None, False, 0, None, RC_ENCRYPTED)])

    engine, _path = _find_engine()
    if engine is None:
        return _fail(mode, RC_ENGINE_MISSING, [
            _make_attempt(mode, None, None, False, 0, None,
                          RC_ENGINE_MISSING)])
    engine_version = _binary_version(engine)

    _ensure_private_dir(work_dir)
    tmp = Path(tempfile.mkdtemp(prefix="ocr-", dir=str(work_dir)))
    try:
        effective = src
        if _is_encrypted(src):
            # Owner-password-only: hand the engine an unencrypted copy in
            # the private tmp dir (engines take no passwords here). The
            # copy is removed with tmp in the finally below.
            dec = tmp / f"decrypted_{_sha_prefix(src)}.pdf"
            if not _decrypted_copy(src, dec):
                return _fail(mode, RC_ENCRYPTED, [
                    _make_attempt(mode, None, None, False, 0, None,
                                  RC_ENCRYPTED)])
            effective = dec
        if engine == "ocrmypdf":
            return _run_ocrmypdf(effective, mode, work_dir, tmp,
                                 engine_version)
        return _run_tesseract(effective, mode, work_dir, tmp, engine_version)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def ocr_with_escalation(src: Path, work_dir: Path,
                        candidate_modes: list[str]) -> dict:
    """Try ``candidate_modes`` in order; keep the best by chars extracted.

    Pure orchestration over :func:`ocr_pdf`. Ties keep the earlier mode. Every
    attempt is recorded in "attempts" in try order. If every mode fails, the
    returned dict carries the last attempt's failure info with all attempts.
    """
    modes = list(candidate_modes or [])
    if not modes or any(m not in MODES for m in modes):
        return _fail(None, RC_INVALID_MODE)

    attempts = []
    best = None
    last = None
    for mode in modes:
        result = ocr_pdf(src, mode, work_dir)
        last = result
        attempts.extend(result.get("attempts", []))
        if result.get("ok") and (best is None or
                                 len(result.get("text", "")) >
                                 len(best.get("text", ""))):
            best = result

    final = dict(best) if best is not None else dict(last)
    final["attempts"] = attempts
    return final