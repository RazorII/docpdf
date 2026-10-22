"""The text, picture and layout checks."""

from __future__ import annotations

from conftest import make_docx, make_rich_docx
from docpdf import cli
from docpdf.content import missing_text, normalise, read_content


def test_reads_visible_text_pictures_and_layout(tmp_path):
    info = read_content(make_rich_docx(tmp_path / "rich.docx"))
    flat = [" ".join(p) for p in info.paragraphs]
    assert any("Visible body text" in p for p in flat)
    assert any("inside a text box" in p for p in flat)
    assert any("Letterhead" in p for p in flat)
    assert not any("secret hidden" in p for p in flat)  # hidden text is left out
    assert not any("99" in p for p in flat)  # a field's stored result is left out
    footer = next(p for p in info.paragraphs if any("Page" in s for s in p))
    assert footer == ["Page ", " of this example document"]  # split at the field
    assert info.images == 1
    assert {"images", "text boxes", "columns"} <= set(info.features)


def test_missing_text_finds_dropped_paragraphs():
    paragraphs = [["Visible body text that every converter must keep."], ["Words that live inside a text box"]]
    pdf_text = normalise("Visible body text that every con- verter must keep.")  # hyphenation survives
    assert missing_text(paragraphs, pdf_text) == ["Words that live inside a text box"]


def test_rich_document_passes_every_check(tmp_path, capsys, libreoffice):
    code = cli.main(["--json", "--strict", str(make_rich_docx(tmp_path / "rich.docx"))])
    import json

    r = json.loads(capsys.readouterr().out)["results"][0]
    assert code == cli.EXIT_OK, r
    assert r["text_checked"] and r["missing_text"] == []
    assert r["images_expected"] == 1 and r["images_in_pdf"] >= 1 and r["image_pages"] == [1]
    assert r["visual_check"]["suggested"] is True
    assert {"images", "text boxes", "columns"} <= set(r["visual_check"]["reasons"])


def test_plain_document_needs_no_look(tmp_path, capsys, libreoffice):
    code = cli.main(["--json", str(make_docx(tmp_path / "plain.docx", ["one", "two"], stored_pages=2))])
    import json

    r = json.loads(capsys.readouterr().out)["results"][0]
    assert code == cli.EXIT_OK
    assert r["visual_check"] == {"suggested": False, "reasons": []}
    assert r["images_expected"] == 0 and r["missing_text"] == []
