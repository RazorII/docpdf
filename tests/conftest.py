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


def png_bytes(width: int = 16, height: int = 16) -> bytes:
    """A small solid-red PNG, built in code so the repo carries no binaries."""
    import struct
    import zlib

    raw = b"".join(b"\x00" + b"\xff\x00\x00" * width for _ in range(height))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


NS = (
    'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
    'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
    'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
    'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture" '
    'xmlns:v="urn:schemas-microsoft-com:vml"'
)


def _run(text: str, extra: str = "") -> str:
    return f'<w:r><w:rPr><w:rFonts w:ascii="Liberation Serif" w:hAnsi="Liberation Serif"/>{extra}</w:rPr><w:t xml:space="preserve">{escape(text)}</w:t></w:r>'


def make_rich_docx(path: Path, image: bool = True, columns: int = 2) -> Path:
    """A one-page document with the things a converter can drop or misplace."""
    picture = (
        '<w:p><w:r><w:drawing><wp:inline><wp:extent cx="914400" cy="914400"/><wp:docPr id="1" name="Picture 1"/>'
        '<a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture"><pic:pic>'
        '<pic:nvPicPr><pic:cNvPr id="1" name="red.png"/><pic:cNvPicPr/></pic:nvPicPr>'
        '<pic:blipFill><a:blip r:embed="rIdImg"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
        '<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="914400" cy="914400"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic></a:graphicData></a:graphic>'
        "</wp:inline></w:drawing></w:r></w:p>"
        if image
        else ""
    )
    textbox = (
        '<w:p><w:r><w:pict><v:shape id="box1" type="#_x0000_t202" style="width:220pt;height:60pt">'
        "<v:textbox><w:txbxContent><w:p>" + _run("Words that live inside a text box") + "</w:p>"
        "</w:txbxContent></v:textbox></v:shape></w:pict></w:r></w:p>"
    )
    body = (
        "<w:p>" + _run("Visible body text that every converter must keep.") + _run(" secret hidden words", "<w:vanish/>") + "</w:p>"
        + picture
        + textbox
        + "<w:p>" + _run("A second paragraph in the body, long enough to be cut into several pieces for the check.") + "</w:p>"
    )
    sect = (
        '<w:sectPr><w:headerReference w:type="default" r:id="rIdHdr"/><w:footerReference w:type="default" r:id="rIdFtr"/>'
        '<w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" w:header="708" w:footer="708" w:gutter="0"/>'
        f'<w:cols w:num="{columns}" w:space="708"/></w:sectPr>'
    )
    document = f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {NS}><w:body>{body}{sect}</w:body></w:document>'
    header = f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:hdr {NS}><w:p>' + _run("Letterhead of the example law office") + "</w:p></w:hdr>"
    footer = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:ftr {NS}><w:p>'
        + _run("Page ")
        + '<w:r><w:fldChar w:fldCharType="begin"/></w:r><w:r><w:instrText xml:space="preserve"> PAGE </w:instrText></w:r>'
        + '<w:r><w:fldChar w:fldCharType="separate"/></w:r>' + _run("99") + '<w:r><w:fldChar w:fldCharType="end"/></w:r>'
        + _run(" of this example document")
        + "</w:p></w:ftr>"
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rIdImg" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/red.png"/>'
        '<Relationship Id="rIdHdr" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/header" Target="header1.xml"/>'
        '<Relationship Id="rIdFtr" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" Target="footer1.xml"/>'
        '<Relationship Id="rIdSty" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
        "</Relationships>"
    )
    types = CONTENT_TYPES.replace(
        '<Default Extension="xml" ContentType="application/xml"/>',
        '<Default Extension="xml" ContentType="application/xml"/><Default Extension="png" ContentType="image/png"/>'
        '<Override PartName="/word/header1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"/>'
        '<Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>'
        '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>',
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", types)
        z.writestr("_rels/.rels", RELS)
        z.writestr("word/document.xml", document)
        z.writestr("word/_rels/document.xml.rels", rels)
        z.writestr("word/header1.xml", header)
        z.writestr("word/footer1.xml", footer)
        # Every real Word file names its default font; without one LibreOffice assumes Calibri.
        z.writestr(
            "word/styles.xml",
            f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:styles {NS}><w:docDefaults><w:rPrDefault><w:rPr>'
            '<w:rFonts w:ascii="Liberation Serif" w:hAnsi="Liberation Serif" w:eastAsia="Liberation Serif" w:cs="Liberation Serif"/>'
            "</w:rPr></w:rPrDefault></w:docDefaults></w:styles>",
        )
        z.writestr("word/media/red.png", png_bytes())
        z.writestr("docProps/app.xml", APP.format(app="Microsoft Office Word", pages="<Pages>1</Pages>"))
    return path
