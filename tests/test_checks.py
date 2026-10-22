"""Unit tests for the checks: no converter needed."""

from __future__ import annotations

import zipfile

from conftest import make_docx, make_rtf
from docpdf.checks import fonts_not_in_pdf, font_was_requested, read_source, unexpected_fonts


def test_reads_word_page_count_and_fonts(tmp_path):
    doc = make_docx(tmp_path / "a.docx", ["one", "two"], font="Tahoma", stored_pages=2)
    info = read_source(doc)
    assert info.pages == 2
    assert info.application == "Microsoft Office Word"
    assert "Tahoma" in info.fonts
    assert info.fonts_checked


def test_missing_page_count_is_none(tmp_path):
    doc = make_docx(tmp_path / "a.docx", ["one"], stored_pages=None)
    assert read_source(doc).pages is None


def test_theme_fonts_resolve(tmp_path):
    doc = tmp_path / "theme.docx"
    make_docx(doc, ["x"])
    w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    a = "http://schemas.openxmlformats.org/drawingml/2006/main"
    with zipfile.ZipFile(doc, "a") as z:
        z.writestr(
            "word/theme/theme1.xml",
            f'<a:theme xmlns:a="{a}"><a:themeElements><a:fontScheme>'
            '<a:majorFont><a:latin typeface="Calibri Light"/><a:ea typeface=""/><a:cs typeface=""/></a:majorFont>'
            '<a:minorFont><a:latin typeface="Calibri"/><a:ea typeface=""/><a:cs typeface="Angsana New"/></a:minorFont>'
            "</a:fontScheme></a:themeElements></a:theme>",
        )
        z.writestr(
            "word/styles.xml",
            f'<w:styles xmlns:w="{w}"><w:docDefaults><w:rPrDefault><w:rPr>'
            '<w:rFonts w:asciiTheme="minorHAnsi" w:hAnsiTheme="minorHAnsi" w:cstheme="minorBidi"/>'
            "</w:rPr></w:rPrDefault></w:docDefaults></w:styles>",
        )
    fonts = read_source(doc).fonts
    assert {"Calibri", "Angsana New"} <= fonts


def test_rtf_font_table(tmp_path):
    rtf = make_rtf(tmp_path / "a.rtf", "hello", font="Georgia")
    info = read_source(rtf)
    assert "Georgia" in info.fonts
    assert info.pages is None


def test_binary_doc_is_not_font_checked(tmp_path):
    doc = tmp_path / "old.doc"
    doc.write_bytes(b"\xd0\xcf\x11\xe0not really a doc")
    info = read_source(doc)
    assert not info.fonts_checked and info.pages is None


def test_pdf_font_names_match_requested_families():
    keys = {"timesnewroman", "arial", "tahoma", "calibrilight", "wingdings", "symbol"}
    for embedded in [
        "TimesNewRomanPSMT",
        "TimesNewRomanPS-BoldMT",
        "ArialMT",
        "Arial,Bold",
        "Tahoma-Bold",
        "Calibri-Light",
        "Wingdings-Regular",
        "SymbolMT",
    ]:
        assert font_was_requested(embedded, keys), embedded


def test_substitutes_are_reported():
    requested = {"Tahoma", "Arial", "Calibri"}
    pdf = {"LinuxLibertineG", "LiberationSans", "Tahoma-Bold"}
    assert unexpected_fonts(pdf, requested) == ["LiberationSans", "LinuxLibertineG"]
    assert unexpected_fonts({"Tahoma", "ArialMT"}, requested) == []


def test_missing_fonts_ranked_by_use():
    missing = fonts_not_in_pdf({"LinuxLibertineG"}, {"Calibri", "Tahoma", "Arial"}, {"Tahoma": 900, "Arial": 3})
    assert missing == ["Tahoma", "Arial", "Calibri"]


def test_metric_compatible_stand_ins_are_split_from_real_swaps():
    from docpdf.checks import stand_ins

    pdf = {"Carlito", "Carlito-Bold", "LinuxLibertineG"}
    requested = {"Calibri", "Tahoma"}
    pairs, swaps = stand_ins(unexpected_fonts(pdf, requested), requested, pdf)
    assert pairs == [("Calibri", "Carlito")]
    assert swaps == ["LinuxLibertineG"]


def test_stand_in_only_counts_when_the_original_is_missing():
    from docpdf.checks import stand_ins

    # Arial made it into the PDF, so Liberation Sans replaced something else.
    pdf = {"ArialMT", "LiberationSans"}
    requested = {"Arial", "Tahoma"}
    pairs, swaps = stand_ins(unexpected_fonts(pdf, requested), requested, pdf)
    assert pairs == [] and swaps == ["LiberationSans"]
