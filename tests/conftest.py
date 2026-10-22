"""Test fixtures: small Word documents built from scratch, so the repo carries no binaries."""

from __future__ import annotations

import zipfile
from pathlib import Path
from typing import List, Optional
from xml.sax.saxutils import escape

import pytest

from docpdf.engines import LibreOffice

CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>"""

RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>"""

APP = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">
<Application>{app}</Application>{pages}
</Properties>"""

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def make_docx(
    path: Path,
    pages: List[str],
    font: str = "Liberation Serif",
    stored_pages: Optional[int] = None,
    application: str = "Microsoft Office Word",
) -> Path:
    """Write a .docx with one paragraph per page, separated by page breaks.

    stored_pages is what docProps/app.xml claims, as Word would record it.
    """
    body = []
    for i, text in enumerate(pages):
        brk = '<w:r><w:br w:type="page"/></w:r>' if i < len(pages) - 1 else ""
        body.append(
            f'<w:p><w:r><w:rPr><w:rFonts w:ascii="{font}" w:hAnsi="{font}" w:cs="{font}"/>'
            f'<w:sz w:val="24"/></w:rPr><w:t xml:space="preserve">{escape(text)}</w:t></w:r>{brk}</w:p>'
        )
    document = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="{W_NS}"><w:body>'
        + "".join(body)
        + '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
        '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" w:header="708" w:footer="708" w:gutter="0"/>'
        "</w:sectPr></w:body></w:document>"
    )
    stored = f"<Pages>{stored_pages}</Pages>" if stored_pages is not None else ""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", CONTENT_TYPES)
        z.writestr("_rels/.rels", RELS)
        z.writestr("word/document.xml", document)
        z.writestr("docProps/app.xml", APP.format(app=application, pages=stored))
    return path


def make_rtf(path: Path, text: str, font: str = "Liberation Serif") -> Path:
    path.write_text(
        "{\\rtf1\\ansi\\deff0{\\fonttbl{\\f0\\froman " + font + ";}}\\f0\\fs24 " + text + "\\par}",
        encoding="ascii",
    )
    return path


@pytest.fixture
def libreoffice():
    engine = LibreOffice()
    if not engine.available():
        pytest.skip("LibreOffice isn't installed")
    return engine
