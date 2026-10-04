"""Tests for taxprep.ocr (R5 local OCR engine).

Engine-invoking tests are skipped when no OCR binary is on PATH (the build
machine has neither tesseract nor ocrmypdf). Pure-logic tests -- mode mapping,
reason codes, escalation bookkeeping -- run everywhere, using a stubbed
ocr_pdf or a fake engine subprocess.
"""

import hashlib
import random
import shutil
import subprocess
from pathlib import Path

import pytest
from PIL import Image, ImageDraw
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject,
    DecodedStreamObject,
    DictionaryObject,
    NameObject,
)
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from taxprep import ocr


# ---------------------------------------------------------------------------
# Synthetic fixtures (reportlab + pypdf + PIL; no real PII, no engine needed)
# ---------------------------------------------------------------------------

def _text_image(lines, size=(1700, 2200)):
    img = Image.new("RGB", size, "white")
    d = ImageDraw.Draw(img)
    y = 120
    for line in lines:
        d.text((120, y), line, fill="black")
        y += 90
    return img


def _save_image_pdf(path, img, page_size=letter):
    c = canvas.Canvas(str(path), pagesize=page_size)
    img_path = str(path) + ".png"
    img.save(img_path)
    c.drawImage(img_path, 0, 0, width=page_size[0], height=page_size[1])
    c.showPage()
    c.save()
    Path(img_path).unlink()


def image_only_pdf(path):
    """Scanned-page lookalike: raster image, no embedded text."""
    _save_image_pdf(path, _text_image(["FORM 1099-B", "Proceeds 1d", "Cost 1e"]))


def mixed_text_image_pdf(path):
    """Digital page: real text plus an embedded image."""
    c = canvas.Canvas(str(path), pagesize=letter)
    c.drawString(72, 720, "Form W-2 Wage and Tax Statement")
    c.drawString(72, 700, "1 Wages, tips, other compensation")
    img = Image.new("RGB", (400, 200), "gray")
    img_path = str(path) + ".png"
    img.save(img_path)
    c.drawImage(img_path, 72, 400, width=200, height=100)
    c.showPage()
    c.save()
    Path(img_path).unlink()


def stray_stamp_pdf(path):
    """Image-only page with a stray text stamp (R5 gate concern)."""
    c = canvas.Canvas(str(path), pagesize=letter)
    img_path = str(path) + ".png"
    _text_image(["FORM 1099-INT", "1 Interest income"]).save(img_path)
    c.drawImage(img_path, 0, 0, width=letter[0], height=letter[1])
    c.setFont("Helvetica", 10)
    c.drawString(500, 770, "DRAFT")  # stray stamp: whole-doc text != ""
    c.showPage()
    c.save()
    Path(img_path).unlink()


def bad_ocr_layer_pdf(path):
    """Image with a bad embedded 'OCR' layer: invisible (white) text."""
    c = canvas.Canvas(str(path), pagesize=letter)
    img_path = str(path) + ".png"
    _text_image(["FORM 1099-DIV", "1a Total ordinary dividends"]).save(img_path)
    c.drawImage(img_path, 0, 0, width=letter[0], height=letter[1])
    c.setFillColorRGB(1, 1, 1)  # white on white: extractable but invisible
    c.setFont("Helvetica", 12)
    c.drawString(72, 720, "garbled ocr text layer here")
    c.showPage()
    c.save()
    Path(img_path).unlink()


def no_tounicode_pdf(path):
    """Font dictionary with no /ToUnicode map (hand-built via pypdf)."""
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject()
    font[NameObject("/Type")] = NameObject("/Font")
    font[NameObject("/Subtype")] = NameObject("/TrueType")
    font[NameObject("/BaseFont")] = NameObject("/ABCDEF+SyntheticSans")
    font[NameObject("/FirstChar")] = ArrayObject()
    # NOTE: deliberately no /ToUnicode entry.
    font_ref = writer._add_object(font)
    resources = DictionaryObject()
    fonts = DictionaryObject()
    fonts[NameObject("/F1")] = font_ref
    resources[NameObject("/Font")] = fonts
    page[NameObject("/Resources")] = resources
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 24 Tf 72 700 Td (Synthetic text) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(stream)
    with open(path, "wb") as f:
        writer.write(f)


def fillable_form_pdf(path):
    """Fillable AcroForm with two text fields holding values."""
    c = canvas.Canvas(str(path), pagesize=letter)
    c.drawString(72, 740, "Fillable form")
    c.acroForm.textfield(name="payer1.name", x=72, y=700, width=200, height=20,
                         value="Acme Broker")
    c.acroForm.textfield(name="payer1.box1d", x=72, y=670, width=200, height=20,
                         value="1234")
    c.showPage()
    c.save()


def encrypted_pdf(path):
    """Password-encrypted PDF (synthetic password)."""
    tmp = Path(str(path) + ".tmp.pdf")
    c = canvas.Canvas(str(tmp), pagesize=letter)
    c.drawString(72, 720, "secret content")
    c.showPage()
    c.save()
    reader = PdfReader(str(tmp))
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    writer.encrypt("synthetic-password")
    with open(path, "wb") as f:
        writer.write(f)
    tmp.unlink()


def owner_only_pdf(path):
    """Owner-password-only PDF: the empty user password unlocks it."""
    tmp = Path(str(path) + ".tmp.pdf")
    c = canvas.Canvas(str(tmp), pagesize=letter)
    c.drawString(72, 720, "Form W-2 Wage and Tax Statement Tax Year 2024")
    c.showPage()
    c.save()
    reader = PdfReader(str(tmp))
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    writer.encrypt(user_password="", owner_password="synthetic-owner",
                   algorithm="AES-128")
    with open(path, "wb") as f:
        writer.write(f)
    tmp.unlink()


def photo_pdf(path):
    """Photo-like page: full-page noise raster, no text."""
    rng = random.Random(7)
    w, h = 1200, 1600
    img = Image.effect_noise((w, h), 128).convert("RGB")
    # deterministic "photo" tint variation
    px = img.load()
    for x in range(0, w, 40):
        for y in range(0, h, 40):
            px[x, y] = (rng.randrange(256), rng.randrange(256), rng.randrange(256))
    _save_image_pdf(path, img)


@pytest.fixture
def fixtures(tmp_path):
    out = {}
    builders = {
        "image_only": image_only_pdf,
        "mixed": mixed_text_image_pdf,
        "stray_stamp": stray_stamp_pdf,
        "bad_layer": bad_ocr_layer_pdf,
        "no_tounicode": no_tounicode_pdf,
        "form": fillable_form_pdf,
        "encrypted": encrypted_pdf,
        "owner_only": owner_only_pdf,
        "photo": photo_pdf,
    }
    for name, build in builders.items():
        p = tmp_path / f"{name}.pdf"
        build(p)
        out[name] = p
    return out


# ---------------------------------------------------------------------------
# Fixture-structure tests (no engine)
# ---------------------------------------------------------------------------

def test_fixtures_build(fixtures):
    assert set(fixtures) == {"image_only", "mixed", "stray_stamp", "bad_layer",
                             "no_tounicode", "form", "encrypted", "owner_only",
                             "photo"}
    for p in fixtures.values():
        assert p.exists() and p.stat().st_size > 0


def test_image_only_has_image_no_text(fixtures):
    reader = PdfReader(str(fixtures["image_only"]))
    page = reader.pages[0]
    images = list(page.images)
    assert len(images) >= 1
    assert (page.extract_text() or "").strip() == ""


def test_mixed_has_text_and_image(fixtures):
    reader = PdfReader(str(fixtures["mixed"]))
    page = reader.pages[0]
    assert "W-2" in (page.extract_text() or "")
    assert len(list(page.images)) >= 1


def test_stray_stamp_text_present_but_image_dominant(fixtures):
    reader = PdfReader(str(fixtures["stray_stamp"]))
    page = reader.pages[0]
    assert "DRAFT" in (page.extract_text() or "")
    assert len(list(page.images)) >= 1


def test_bad_layer_text_extractable_but_invisible(fixtures):
    text = PdfReader(str(fixtures["bad_layer"])).pages[0].extract_text() or ""
    assert "garbled ocr text layer" in text


def test_no_tounicode_font_lacks_map(fixtures):
    reader = PdfReader(str(fixtures["no_tounicode"]))
    fonts = reader.pages[0].get("/Resources", {}).get("/Font", {})
    assert fonts, "fixture must declare a font"
    for font in fonts.values():
        assert "/ToUnicode" not in font.get_object()


def test_fillable_form_has_fields_with_values(fixtures):
    fields = PdfReader(str(fixtures["form"])).get_fields() or {}
    assert "payer1.name" in fields
    assert fields["payer1.name"].get("/V") == "Acme Broker"


def test_encrypted_fixture_is_encrypted(fixtures):
    assert PdfReader(str(fixtures["encrypted"])).is_encrypted


def test_photo_has_image_no_text(fixtures):
    reader = PdfReader(str(fixtures["photo"]))
    page = reader.pages[0]
    assert len(list(page.images)) >= 1
    assert (page.extract_text() or "").strip() == ""


# ---------------------------------------------------------------------------
# Pure-logic tests (run with or without an engine)
# ---------------------------------------------------------------------------

def test_engine_info_shape():
    info = ocr.engine_info()
    assert set(info) == {"engine", "version", "available"}
    assert info["available"] == ocr.available()
    assert info["engine"] in (None, "ocrmypdf", "tesseract")


def test_no_engine_here():
    if ocr.available():
        pytest.skip("an OCR engine is installed; absence assertions N/A")
    assert not ocr.available()
    assert ocr.engine_info() == {"engine": None, "version": None,
                                 "available": False}


def test_engine_info_never_crashes_without_binaries(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    assert ocr.engine_info() == {"engine": None, "version": None,
                                 "available": False}
    assert not ocr.available()


def test_ocr_pdf_invalid_mode(tmp_path, fixtures):
    res = ocr.ocr_pdf(fixtures["image_only"], "turbo-ocr", tmp_path / "work")
    assert res["ok"] is False
    assert res["reason_code"] == "invalid_mode"
    assert res["attempts"] == []
    assert res["engine"] is None


def test_ocr_pdf_missing_source(tmp_path):
    res = ocr.ocr_pdf(tmp_path / "nope.pdf", "skip-text", tmp_path / "work")
    assert res["ok"] is False
    assert res["reason_code"] == "source_missing"
    assert not (tmp_path / "work").exists()  # no dirs created for bad input


def test_ocr_pdf_encrypted_blocked(tmp_path, fixtures):
    res = ocr.ocr_pdf(fixtures["encrypted"], "skip-text", tmp_path / "work")
    assert res["ok"] is False
    assert res["reason_code"] == "encrypted"
    assert res["text"] == ""
    # never handles passwords: returns immediately, no exception text
    assert res["engine"] is None


def test_user_password_required_pure_logic(fixtures):
    # X1: the empty password is tried first -- only a genuine user
    # password counts as requiring one.
    assert ocr._user_password_required(fixtures["image_only"]) is False
    assert ocr._user_password_required(fixtures["owner_only"]) is False
    assert ocr._user_password_required(fixtures["encrypted"]) is True


def test_ocr_pdf_owner_only_not_refused(tmp_path, fixtures, monkeypatch):
    # X1: owner-only PDF is NOT refused with "encrypted"; the next gate
    # (engine absence here) is what fails, and src is never modified.
    monkeypatch.setattr(shutil, "which", lambda name: None)
    before = fixtures["owner_only"].stat().st_size
    res = ocr.ocr_pdf(fixtures["owner_only"], "skip-text",
                      tmp_path / "work")
    assert res["ok"] is False
    assert res["reason_code"] == "engine_missing"  # not "encrypted"
    assert fixtures["owner_only"].stat().st_size == before


def test_ocr_pdf_engine_missing_without_engine(tmp_path, fixtures, monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    res = ocr.ocr_pdf(fixtures["image_only"], "skip-text", tmp_path / "work")
    assert res["ok"] is False
    assert res["reason_code"] == "engine_missing"
    assert len(res["attempts"]) == 1
    assert res["attempts"][0]["mode"] == "skip-text"


def _fake_engine(monkeypatch, sidecar_text):
    """Fake ocrmypdf on PATH; capture argv, write sidecar + output PDF."""
    captured = {}

    def fake_which(name):
        return "/fake/bin/ocrmypdf" if name == "ocrmypdf" else None

    def fake_run(cmd, **kwargs):
        cmd = list(cmd)
        if cmd[1] == "--version":
            return subprocess.CompletedProcess(cmd, 0, stdout="ocrmypdf 16.0.0\n",
                                               stderr="")
        captured["argv"] = cmd
        captured["env_tmpdir"] = (kwargs.get("env") or {}).get("TMPDIR")
        sidecar = Path(cmd[cmd.index("--sidecar") + 1])
        sidecar.write_text(sidecar_text, encoding="utf-8")
        Path(cmd[-1]).write_bytes(b"%PDF-1.7 fake\n")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(shutil, "which", fake_which)
    monkeypatch.setattr(subprocess, "run", fake_run)
    return captured


def test_mode_flags_map_to_ocrmypdf_argv(tmp_path, fixtures, monkeypatch):
    captured = _fake_engine(monkeypatch, "hello ocr\n")
    src = fixtures["image_only"]
    before = hashlib.sha256(src.read_bytes()).hexdigest()
    work = tmp_path / "work"
    for mode, flag in [("skip-text", "--skip-text"), ("redo-ocr", "--redo-ocr"),
                       ("force-ocr", "--force-ocr")]:
        res = ocr.ocr_pdf(src, mode, work)
        argv = captured["argv"]
        assert flag in argv
        assert "--deskew" in argv and "--rotate-pages" in argv
        assert "--sidecar" in argv
        assert str(src) in argv
        assert res["ok"] is True
        assert res["text"] == "hello ocr\n"
        assert res["engine"] == "ocrmypdf"
        assert res["engine_version"] == "16.0.0"
        assert res["reason_code"] is None
        assert res["mean_confidence"] is None  # plain-text sidecar: no conf
        assert len(res["attempts"]) == 1
        assert res["attempts"][0]["mode"] == mode
    # src never modified
    assert hashlib.sha256(src.read_bytes()).hexdigest() == before
    # outputs live under work_dir, named without the filename stem
    assert src.stem not in " ".join(p.name for p in work.iterdir())


def test_private_tmpdir_used_and_cleaned(tmp_path, fixtures, monkeypatch):
    captured = _fake_engine(monkeypatch, "x\n")
    work = tmp_path / "work"
    ocr.ocr_pdf(fixtures["image_only"], "skip-text", work)
    assert captured["env_tmpdir"] is not None
    assert captured["env_tmpdir"].startswith(str(work))
    assert not Path(captured["env_tmpdir"]).exists()  # cleaned up
    assert work.exists()


def test_ocrmypdf_failure_reason_code(tmp_path, fixtures, monkeypatch):
    monkeypatch.setattr(shutil, "which",
                        lambda name: "/fake/bin/ocrmypdf" if name == "ocrmypdf" else None)

    def bad_run(cmd, **kwargs):
        return subprocess.CompletedProcess(list(cmd), 2, stdout="", stderr="boom")

    monkeypatch.setattr(subprocess, "run", bad_run)
    res = ocr.ocr_pdf(fixtures["image_only"], "force-ocr", tmp_path / "work")
    assert res["ok"] is False
    assert res["reason_code"] == "ocr_failed"
    assert "boom" not in str(res)  # never exception/engine text


# ---------------------------------------------------------------------------
# Escalation bookkeeping with a stubbed ocr_pdf
# ---------------------------------------------------------------------------

def _stub_result(mode, text, ok=True, reason=None, conf=None):
    return {
        "ok": ok,
        "text": text,
        "mean_confidence": conf,
        "attempts": [ocr._make_attempt(mode, "stub", "0", ok, len(text), conf,
                                       reason)],
        "reason_code": reason,
        "engine": "stub",
        "engine_version": "0",
    }


def _stub_ocr_pdf(monkeypatch, per_mode):
    def fake(src, mode, work_dir):
        text, ok = per_mode[mode]
        return _stub_result(mode, text, ok=ok,
                            reason=None if ok else "ocr_failed")
    monkeypatch.setattr(ocr, "ocr_pdf", fake)


def test_escalation_keeps_best_by_chars(tmp_path, fixtures, monkeypatch):
    _stub_ocr_pdf(monkeypatch, {
        "skip-text": ("short", True),
        "redo-ocr": ("a much longer extraction result", True),
        "force-ocr": ("mid", True),
    })
    res = ocr.ocr_with_escalation(fixtures["image_only"], tmp_path / "w",
                                  ["skip-text", "redo-ocr", "force-ocr"])
    assert res["ok"] is True
    assert res["text"] == "a much longer extraction result"
    assert res["reason_code"] is None
    assert [a["mode"] for a in res["attempts"]] == ["skip-text", "redo-ocr",
                                                   "force-ocr"]
    assert [a["chars"] for a in res["attempts"]] == [5, 31, 3]


def test_escalation_tie_keeps_earlier_mode(tmp_path, fixtures, monkeypatch):
    _stub_ocr_pdf(monkeypatch, {
        "skip-text": ("same", True),
        "redo-ocr": ("same", True),
    })
    res = ocr.ocr_with_escalation(fixtures["image_only"], tmp_path / "w",
                                  ["skip-text", "redo-ocr"])
    assert res["text"] == "same"
    assert res["attempts"][0]["mode"] == "skip-text"
    assert len(res["attempts"]) == 2


def test_escalation_skips_failed_modes(tmp_path, fixtures, monkeypatch):
    _stub_ocr_pdf(monkeypatch, {
        "skip-text": ("", False),
        "redo-ocr": ("recovered text", True),
    })
    res = ocr.ocr_with_escalation(fixtures["image_only"], tmp_path / "w",
                                  ["skip-text", "redo-ocr"])
    assert res["ok"] is True
    assert res["text"] == "recovered text"
    assert res["attempts"][0]["ok"] is False
    assert res["attempts"][1]["ok"] is True


def test_escalation_all_fail_returns_last_failure(tmp_path, fixtures,
                                                  monkeypatch):
    _stub_ocr_pdf(monkeypatch, {
        "skip-text": ("", False),
        "redo-ocr": ("", False),
    })
    res = ocr.ocr_with_escalation(fixtures["image_only"], tmp_path / "w",
                                  ["skip-text", "redo-ocr"])
    assert res["ok"] is False
    assert res["reason_code"] == "ocr_failed"
    assert len(res["attempts"]) == 2


def test_escalation_invalid_modes_rejected(tmp_path, fixtures, monkeypatch):
    calls = []
    monkeypatch.setattr(ocr, "ocr_pdf",
                        lambda s, m, w: calls.append(m) or _stub_result(m, "x"))
    for bad in ([], ["bogus"], ["skip-text", "bogus"]):
        res = ocr.ocr_with_escalation(fixtures["image_only"], tmp_path / "w",
                                      bad)
        assert res["ok"] is False
        assert res["reason_code"] == "invalid_mode"
        assert res["attempts"] == []
    assert calls == []  # engine never invoked


def test_escalation_return_shape(tmp_path, fixtures, monkeypatch):
    _stub_ocr_pdf(monkeypatch, {"skip-text": ("abc", True)})
    res = ocr.ocr_with_escalation(fixtures["image_only"], tmp_path / "w",
                                  ["skip-text"])
    assert set(res) == {"ok", "text", "mean_confidence", "attempts",
                        "reason_code", "engine", "engine_version"}
    assert set(res["attempts"][0]) == {"mode", "engine", "engine_version",
                                       "ok", "chars", "mean_confidence",
                                       "reason_code"}


def test_ocr_pdf_return_shape_with_fake_engine(tmp_path, fixtures, monkeypatch):
    _fake_engine(monkeypatch, "abc\n")
    res = ocr.ocr_pdf(fixtures["image_only"], "skip-text", tmp_path / "w")
    # R15: the tesseract fallback also returns TSV-parsed "words"
    # ([{text, bbox, conf, page}]) for field-geometry resolution
    assert set(res) == {"ok", "text", "mean_confidence", "attempts",
                        "reason_code", "engine", "engine_version", "words"}


# ---------------------------------------------------------------------------
# Engine-invoking tests: skipped when no OCR binary is on PATH
# ---------------------------------------------------------------------------

needs_engine = pytest.mark.skipif(not ocr.available(),
                                  reason="no OCR engine on PATH")


@needs_engine
def test_engine_info_reports_version():
    info = ocr.engine_info()
    assert info["engine"] in ("ocrmypdf", "tesseract")
    assert isinstance(info["version"], str) and info["version"]


@needs_engine
def test_engine_ocr_image_only(tmp_path, fixtures):
    res = ocr.ocr_pdf(fixtures["image_only"], "skip-text", tmp_path / "work")
    assert res["ok"] is True, res
    assert res["reason_code"] is None
    assert len(res["text"].strip()) > 0
    assert res["engine"] in ("ocrmypdf", "tesseract")
    assert len(res["attempts"]) == 1
    assert res["attempts"][0]["chars"] == len(res["text"])


@needs_engine
def test_engine_ocr_bad_layer_redo(tmp_path, fixtures):
    res = ocr.ocr_pdf(fixtures["bad_layer"], "redo-ocr", tmp_path / "work")
    assert res["ok"] is True, res
    assert len(res["text"].strip()) > 0


@needs_engine
def test_engine_escalation_on_photo(tmp_path, fixtures):
    res = ocr.ocr_with_escalation(fixtures["photo"], tmp_path / "work",
                                  ["skip-text", "redo-ocr", "force-ocr"])
    assert len(res["attempts"]) == 3
    # photo has no real text; the point is the orchestration ran end to end
    assert res["ok"] is True


@needs_engine
def test_engine_never_modifies_src(tmp_path, fixtures):
    src = fixtures["mixed"]
    before = hashlib.sha256(src.read_bytes()).hexdigest()
    ocr.ocr_pdf(src, "force-ocr", tmp_path / "work")
    assert hashlib.sha256(src.read_bytes()).hexdigest() == before
