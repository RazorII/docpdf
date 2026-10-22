"""End-to-end tests through the CLI. Converting tests need LibreOffice and skip without it."""

from __future__ import annotations

import json
import platform
import subprocess
import sys

import pytest

from conftest import make_docx, make_rtf
from docpdf import cli
from docpdf.engines import EngineError, LibreOffice


def run(args, capsys):
    code = cli.main([str(a) for a in args])
    out = capsys.readouterr()
    return code, out.out, out.err


def run_json(args, capsys):
    code, out, _ = run(["--json", *args], capsys)
    return code, json.loads(out)


def test_missing_file_fails(tmp_path, capsys, libreoffice):
    code, data = run_json([tmp_path / "nope.docx"], capsys)
    assert code == cli.EXIT_FAILED
    assert data["results"][0]["error"] == "file not found."


def test_unsupported_type_fails(tmp_path, capsys, libreoffice):
    f = tmp_path / "notes.txt"
    f.write_text("hi")
    code, data = run_json([f], capsys)
    assert code == cli.EXIT_FAILED
    assert "not a supported document type" in data["results"][0]["error"]


def test_converts_docx_and_page_count_matches(tmp_path, capsys, libreoffice):
    doc = make_docx(tmp_path / "three pages é.docx", ["one", "two", "three"], stored_pages=3)
    code, data = run_json([doc], capsys)
    r = data["results"][0]
    assert code == cli.EXIT_OK, r
    assert r["ok"] and r["pages"] == 3 and r["expected_pages"] == 3
    assert r["warnings"] == []
    assert (tmp_path / "three pages é.pdf").exists()


def test_page_count_mismatch_warns_and_strict_fails(tmp_path, capsys, libreoffice):
    doc = make_docx(tmp_path / "a.docx", ["one", "two"], stored_pages=5)
    code, data = run_json(["--strict", doc], capsys)
    assert code == cli.EXIT_CHECK
    assert "counted 5 pages" in data["results"][0]["warnings"][0]


def test_missing_font_is_flagged(tmp_path, capsys, libreoffice):
    doc = make_docx(tmp_path / "a.docx", ["hello"], font="Docpdf Nonexistent Sans", stored_pages=1)
    code, data = run_json(["--strict", doc], capsys)
    r = data["results"][0]
    assert code == cli.EXIT_CHECK, r
    assert r["unexpected_fonts"], r
    assert "Docpdf Nonexistent Sans" in r["fonts_not_in_pdf"]


@pytest.mark.skipif(platform.system() == "Linux", reason="Georgia ships with macOS and Windows, not Linux runners")
def test_system_font_is_used_not_substituted(tmp_path, capsys, libreoffice):
    # Guards the macOS headless font trap: without the macOS renderer,
    # LibreOffice can't see /System/Library/Fonts and swaps Georgia out.
    doc = make_docx(tmp_path / "g.docx", ["Georgia text"], font="Georgia", stored_pages=1)
    code, data = run_json(["--strict", doc], capsys)
    r = data["results"][0]
    assert code == cli.EXIT_OK, r
    assert r["unexpected_fonts"] == []


def test_calibri_stand_in_is_a_note_not_a_warning(tmp_path, capsys, libreoffice):
    # Without Calibri, LibreOffice uses Carlito, which has Calibri's letter
    # widths. That keeps the layout, so it's a note and --strict still passes.
    # (Windows ships Calibri, so there the original is simply used.)
    doc = make_docx(tmp_path / "c.docx", ["Calibri text"], font="Calibri", stored_pages=1)
    code, data = run_json(["--strict", doc], capsys)
    r = data["results"][0]
    assert code == cli.EXIT_OK, r
    assert r["unexpected_fonts"] == []
    assert r["stand_ins"] in ([], [{"requested": "Calibri", "used": "Carlito"}])
    assert bool(r["stand_ins"]) == bool(r["notes"])


def test_refuses_to_overwrite_then_overwrites(tmp_path, capsys, libreoffice):
    doc = make_docx(tmp_path / "a.docx", ["one"], stored_pages=1)
    existing = tmp_path / "a.pdf"
    existing.write_bytes(b"keep me")
    code, data = run_json([doc], capsys)
    assert code == cli.EXIT_FAILED and "already exists" in data["results"][0]["error"]
    assert existing.read_bytes() == b"keep me"
    code, data = run_json(["--overwrite", doc], capsys)
    assert code == cli.EXIT_OK
    assert existing.read_bytes().startswith(b"%PDF")


def test_outdir(tmp_path, capsys, libreoffice):
    doc = make_docx(tmp_path / "a.docx", ["one"], stored_pages=1)
    out = tmp_path / "pdfs" / "nested"
    code, _ = run_json(["-o", out, doc], capsys)
    assert code == cli.EXIT_OK
    assert (out / "a.pdf").exists() and not (tmp_path / "a.pdf").exists()


def test_rtf_odt_and_doc(tmp_path, capsys, libreoffice):
    rtf = make_rtf(tmp_path / "r.rtf", "hello")
    made = []
    for fmt in ("odt", "doc"):
        src = make_docx(tmp_path / f"as-{fmt}.docx", ["one", "two"], stored_pages=2)
        profile = tmp_path / f"profile-{fmt}"
        subprocess.run(
            libreoffice._command(profile, ["--convert-to", fmt, "--outdir", str(tmp_path / fmt), str(src)]),
            check=True,
            capture_output=True,
            timeout=180,
        )
        made.append(tmp_path / fmt / f"as-{fmt}.{fmt}")
    code, data = run_json(["-o", tmp_path / "out", rtf, *made], capsys)
    assert code == cli.EXIT_OK, data
    pages = {r["source"].rsplit(".", 1)[1]: r["pages"] for r in data["results"]}
    assert pages == {"rtf": 1, "odt": 2, "doc": 2}


def test_several_files_one_bad(tmp_path, capsys, libreoffice):
    good = make_docx(tmp_path / "good.docx", ["one"], stored_pages=1)
    code, data = run_json([good, tmp_path / "missing.docx"], capsys)
    assert code == cli.EXIT_FAILED
    assert [r["ok"] for r in data["results"]] == [True, False]


def test_human_output(tmp_path, capsys, libreoffice):
    doc = make_docx(tmp_path / "a.docx", ["one", "two"], stored_pages=4)
    code, out, _ = run([doc], capsys)
    assert code == cli.EXIT_OK
    assert out.startswith("WARN  a.docx") and "counted 4 pages" in out


def test_engines_listing(capsys, libreoffice):
    code, out, _ = run(["--engines"], capsys)
    assert code == cli.EXIT_OK and "LibreOffice" in out


def test_no_engine(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli, "_pick_engine", lambda name: None)
    code, data = run_json([tmp_path / "a.docx"], capsys)
    assert code == cli.EXIT_NO_ENGINE and "No converter found" in data["error"]


def test_macos_falls_back_when_renderer_cannot_start(monkeypatch, tmp_path):
    monkeypatch.setattr("docpdf.engines.platform.system", lambda: "Darwin")
    engine = LibreOffice()
    engine._soffice = "soffice"
    calls = []

    def fake_convert(src, workdir, timeout, env):
        calls.append(env.get("SAL_USE_VCLPLUGIN"))
        if len(calls) == 1:
            raise EngineError("LibreOffice didn't produce a PDF (exit code 134).")
        return workdir / "document.pdf"

    monkeypatch.setattr(engine, "_convert", fake_convert)
    engine.convert(tmp_path / "document.docx", tmp_path, 10)
    assert calls == ["osx", "svp"]
    assert "plain headless renderer" in engine.note


def test_module_entry_point():
    out = subprocess.run([sys.executable, "-m", "docpdf", "--version"], capture_output=True, text=True)
    assert out.returncode == 0 and out.stdout.startswith("docpdf ")
