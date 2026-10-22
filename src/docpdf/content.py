"""What a document contains, and whether the PDF still has it.

Three things the page-count and font checks can't see:

* Text. Every paragraph of visible text should be findable in the PDF's text.
  A converter that drops a text box, a header or a footer passes the other
  checks and loses words.
* Images. The PDF should hold at least as many pictures as the document
  places. A missing logo or signature image doesn't change the page count.
* Layout. Images, text boxes, shapes, floating objects, columns and charts are
  where a converter is most likely to draw something in the wrong place. Their
  presence decides whether the pages are worth looking at.
"""

from __future__ import annotations

import posixpath
import re
import unicodedata
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
MC = "{http://schemas.openxmlformats.org/markup-compatibility/2006}"
WP = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}"
WPS = "{http://schemas.microsoft.com/office/word/2010/wordprocessingShape}"
V = "{urn:schemas-microsoft-com:vml}"
ASVG = "{http://schemas.microsoft.com/office/drawing/2016/SVG/main}"
PKG_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"
CHART_URI = "http://schemas.openxmlformats.org/drawingml/2006/chart"

TEXT_NS = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"
DRAW = "{urn:oasis:names:tc:opendocument:xmlns:drawing:1.0}"
XLINK = "{http://www.w3.org/1999/xlink}"

_TEXT_PARTS = re.compile(r"^word/(document|header\d*|footer\d*|footnotes|endnotes)\.xml$")
RASTER = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".webp"}
_VML_SHAPES = {f"{V}{t}" for t in ("shape", "rect", "roundrect", "oval", "line", "polyline", "arc", "curve")}

# Features that make a look at the pages worthwhile. Tables are reported but
# don't count: converters render them reliably.
VISUAL_TRIGGERS = ("images", "text boxes", "drawn shapes", "floating objects", "columns", "charts")


@dataclass
class ContentInfo:
    paragraphs: List[List[str]] = field(default_factory=list)  # visible text, split at fields
    images: int = 0  # distinct raster pictures the document places
    features: List[str] = field(default_factory=list)  # layout features found
    text_checked: bool = False
    images_checked: bool = False


@dataclass
class PdfContent:
    text: str  # normalised: letters and digits only
    images: int  # distinct image objects drawn
    image_pages: List[int]  # 1-based pages that draw an image


def read_content(path: Path) -> ContentInfo:
    suffix = path.suffix.lower()
    try:
        if suffix in (".docx", ".docm", ".dotx", ".dotm"):
            return _read_docx(path)
        if suffix == ".odt":
            return _read_odt(path)
    except (zipfile.BadZipFile, ET.ParseError, OSError, KeyError):
        pass
    return ContentInfo()


def _read_docx(path: Path) -> ContentInfo:
    info = ContentInfo(text_checked=True, images_checked=True)
    features = set()
    targets = set()
    seen = set()
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        for part in sorted(n for n in names if _TEXT_PARTS.match(n)):
            root = ET.fromstring(z.read(part))
            rels = _rels(z, part)
            for el in _walk(root):
                tag = el.tag
                if tag == f"{W}p":
                    segments = _paragraph_segments(el)
                    key = tuple(segments)
                    if segments and key not in seen:
                        seen.add(key)
                        info.paragraphs.append(segments)
                elif tag == f"{A}blip" or tag == f"{V}imagedata":
                    rid = el.get(f"{R}embed") if tag == f"{A}blip" else el.get(f"{R}id")
                    target = rels.get(rid or "")
                    if not target:
                        continue
                    features.add("images")
                    svg = tag == f"{A}blip" and el.find(f".//{ASVG}svgBlip") is not None
                    # SVG, EMF and WMF pictures become vector drawing, not image objects.
                    if not svg and posixpath.splitext(target)[1].lower() in RASTER:
                        targets.add(target)
                elif tag == f"{W}txbxContent":
                    features.add("text boxes")
                elif tag == f"{WPS}wsp" and el.find(f".//{W}txbxContent") is None:
                    features.add("drawn shapes")
                elif tag in _VML_SHAPES and el.find(f".//{V}imagedata") is None and el.find(f".//{W}txbxContent") is None:
                    features.add("drawn shapes")
                elif tag == f"{WP}anchor":
                    features.add("floating objects")
                elif tag == f"{A}graphicData" and el.get("uri") == CHART_URI:
                    features.add("charts")
                elif tag == f"{W}cols":
                    num = el.get(f"{W}num") or "1"
                    if num.isdigit() and int(num) > 1:
                        features.add("columns")
                elif tag == f"{W}tbl":
                    features.add("tables")
    info.images = len(targets)
    info.features = sorted(features)
    return info


def _read_odt(path: Path) -> ContentInfo:
    info = ContentInfo(text_checked=True, images_checked=True)
    features = set()
    targets = set()
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("content.xml"))
    for el in root.iter():
        if el.tag in (f"{TEXT_NS}p", f"{TEXT_NS}h"):
            text = "".join(_odt_text(el))
            if text.strip():
                info.paragraphs.append([text])
        elif el.tag == f"{DRAW}image":
            href = el.get(f"{XLINK}href") or ""
            features.add("images")
            if posixpath.splitext(href)[1].lower() in RASTER:
                targets.add(href)
        elif el.tag == f"{DRAW}text-box":
            features.add("text boxes")
        elif el.tag == f"{TEXT_NS}table" or el.tag.endswith("}table"):
            features.add("tables")
    info.images = len(targets)
    info.features = sorted(features)
    return info


def _odt_text(el):
    if el.text:
        yield el.text
    for child in el:
        if child.tag != f"{DRAW}frame":  # a frame's paragraphs are listed on their own
            yield from _odt_text(child)
        if child.tail:
            yield child.tail


def _walk(el):
    """Every element below el, skipping mc:Fallback (a duplicate of mc:Choice)."""
    for child in el:
        if child.tag == f"{MC}Fallback":
            continue
        yield child
        yield from _walk(child)


def _rels(z: zipfile.ZipFile, part: str) -> Dict[str, str]:
    folder, name = posixpath.split(part)
    rels_name = posixpath.join(folder, "_rels", name + ".rels")
    if rels_name not in z.namelist():
        return {}
    out = {}
    for rel in ET.fromstring(z.read(rels_name)).iter(f"{PKG_REL}Relationship"):
        if rel.get("TargetMode") == "External":
            continue
        out[rel.get("Id")] = posixpath.normpath(posixpath.join(folder, rel.get("Target", "")))
    return out


def _on(el) -> bool:
    return el is not None and el.get(f"{W}val", "true") not in ("0", "false", "off")


def _paragraph_segments(p) -> List[str]:
    """Visible text of one paragraph, split wherever a field or hidden text sits.

    Field results (page numbers, dates) are left out because the converter
    recomputes them, and splitting there keeps "Page 1 of 2" checkable as
    "Page" and "of". Text boxes inside the paragraph are their own paragraphs.
    """
    segments: List[str] = []
    current: List[str] = []
    fields: List[str] = []

    def flush() -> None:
        if current:
            segments.append("".join(current))
            current.clear()

    def walk(el) -> None:
        for child in el:
            tag = child.tag
            if tag in (f"{W}p", f"{MC}Fallback", f"{W}del", f"{W}moveFrom", f"{W}drawing", f"{W}pict"):
                continue
            if tag == f"{W}fldSimple":
                flush()
                continue
            if tag == f"{W}r":
                rpr = child.find(f"{W}rPr")
                hidden = rpr is not None and (_on(rpr.find(f"{W}vanish")) or _on(rpr.find(f"{W}webHidden")))
                for rc in child:
                    if rc.tag == f"{W}fldChar":
                        kind = rc.get(f"{W}fldCharType")
                        if kind == "begin":
                            flush()
                            fields.append("code")
                        elif kind == "separate" and fields:
                            fields[-1] = "result"
                        elif kind == "end" and fields:
                            fields.pop()
                            flush()
                    elif rc.tag == f"{W}t":
                        if hidden or fields:
                            flush()
                        else:
                            current.append(rc.text or "")
                    elif rc.tag in (f"{W}tab", f"{W}br", f"{W}cr"):
                        current.append(" ")
                continue
            walk(child)

    walk(p)
    flush()
    return [s for s in segments if len(normalise(s)) >= 3]


def normalise(text: str) -> str:
    """Letters and digits only, case-folded: survives hyphenation, ligatures, quotes and spacing."""
    return "".join(ch for ch in unicodedata.normalize("NFKC", text).casefold() if ch.isalnum())


def _chunks(norm: str, size: int = 30) -> List[str]:
    if len(norm) <= size:
        return [norm]
    parts = [norm[i : i + size] for i in range(0, len(norm), size)]
    if len(parts[-1]) < 10:
        last = parts.pop()
        parts[-1] += last
    return parts


def missing_text(paragraphs: List[List[str]], pdf_text: str) -> List[str]:
    """Paragraphs whose text is mostly absent from the PDF, as short snippets.

    Each paragraph is cut into 30-character pieces; it counts as missing when
    fewer than half of them are found. That tolerates a stray extraction glitch
    and still catches a dropped text box, header or footer.
    """
    missing = []
    for segments in paragraphs:
        chunks = [c for s in segments for c in _chunks(normalise(s))]
        if not chunks:
            continue
        found = sum(1 for c in chunks if c in pdf_text)
        if found * 2 < len(chunks):
            snippet = re.sub(r"\s+", " ", " … ".join(segments)).strip()
            missing.append(snippet if len(snippet) <= 60 else snippet[:57].rstrip() + "...")
    return missing


def read_pdf_content(path: Path) -> PdfContent:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    texts: List[str] = []
    images = set()
    image_pages: List[int] = []

    def walk(resources, seen) -> bool:
        if resources is None:
            return False
        resources = resources.get_object()
        drew = False
        xobjects = resources.get("/XObject")
        if xobjects is None:
            return False
        for ref in xobjects.get_object().values():
            key = getattr(ref, "idnum", None) or id(ref)
            xobj = ref.get_object()
            subtype = xobj.get("/Subtype")
            if subtype == "/Image":
                images.add(key)
                drew = True
            elif subtype == "/Form" and key not in seen:
                seen.add(key)
                drew = walk(xobj.get("/Resources"), seen) or drew
        return drew

    for number, page in enumerate(reader.pages, start=1):
        try:
            texts.append(page.extract_text() or "")
        except Exception:  # a page pypdf can't read shouldn't stop the other checks
            texts.append("")
        if walk(page.get("/Resources"), set()):
            image_pages.append(number)
    return PdfContent(text=normalise(" ".join(texts)), images=len(images), image_pages=image_pages)
