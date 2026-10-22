"""Checks that a PDF matches the document it was made from.

Two checks, both cheap and both aimed at the failures that matter when a PDF
is going to be printed, signed or sent:

* Page count. When Microsoft Word saves a .docx it records how many pages the
  document had (docProps/app.xml). A PDF with a different count has reflowed.
* Font substitution. The fonts the document asks for are compared with the
  fonts embedded in the PDF. A font in the PDF that the document never asked
  for means the converter couldn't find one and swapped in a lookalike, which
  changes line breaks, spacing and often the page count.
"""

from __future__ import annotations

import re
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, Optional, Set

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
EP = "{http://schemas.openxmlformats.org/officeDocument/2006/extended-properties}"
STYLE = "{urn:oasis:names:tc:opendocument:xmlns:style:1.0}"
SVG = "{urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0}"

OOXML_SUFFIXES = {".docx", ".docm", ".dotx", ".dotm"}

# Parts of a .docx that can carry run fonts.
_OOXML_FONT_PARTS = re.compile(
    r"^word/(document|styles|numbering|fontTable|footnotes|endnotes|comments|header\d*|footer\d*)\.xml$"
)
_THEME_PART = re.compile(r"^word/theme/theme\d*\.xml$")
_FONT_ATTRS = ("ascii", "hAnsi", "eastAsia", "cs")
_THEME_ATTRS = ("asciiTheme", "hAnsiTheme", "eastAsiaTheme", "cstheme")


@dataclass
class SourceInfo:
    """What the source document says about itself."""

    pages: Optional[int] = None  # page count the authoring app stored at its last save
    application: Optional[str] = None  # e.g. "Microsoft Office Word"
    fonts: Set[str] = field(default_factory=set)  # font families the document asks for
    uses: Dict[str, int] = field(default_factory=dict)  # how often each font is set, to rank them
    fonts_checked: bool = False  # False when the format can't be read (e.g. binary .doc)


@dataclass
class PdfInfo:
    pages: int
    fonts: Set[str]  # embedded font names, subset prefix removed


def read_source(path: Path) -> SourceInfo:
    suffix = path.suffix.lower()
    try:
        if suffix in OOXML_SUFFIXES:
            return _read_ooxml(path)
        if suffix == ".odt":
            return _read_odt(path)
        if suffix == ".rtf":
            return _read_rtf(path)
    except (zipfile.BadZipFile, ET.ParseError, OSError, KeyError):
        pass
    return SourceInfo()


def _read_ooxml(path: Path) -> SourceInfo:
    info = SourceInfo()
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        if "docProps/app.xml" in names:
            root = ET.fromstring(z.read("docProps/app.xml"))
            pages = root.findtext(f"{EP}Pages")
            if pages and pages.strip().isdigit() and int(pages) > 0:
                info.pages = int(pages)
            app = root.findtext(f"{EP}Application")
            info.application = app.strip() if app else None

        theme = {}
        for name in names:
            if _THEME_PART.match(name):
                root = ET.fromstring(z.read(name))
                for kind in ("major", "minor"):
                    node = root.find(f".//{A}{kind}Font")
                    if node is None:
                        continue
                    for script, key in (("latin", "HAnsi"), ("ea", "EastAsia"), ("cs", "Bidi")):
                        el = node.find(f"{A}{script}")
                        face = el.get("typeface") if el is not None else None
                        if face:
                            theme[kind + key] = face
                            if key == "HAnsi":
                                theme[kind + "Ascii"] = face
                break

        for name in names:
            if not _OOXML_FONT_PARTS.match(name):
                continue
            root = ET.fromstring(z.read(name))
            if name == "word/fontTable.xml":
                for font in root.iter(f"{W}font"):
                    _add(info, font.get(f"{W}name"), weight=0)
                continue
            for rf in root.iter(f"{W}rFonts"):
                for attr in _FONT_ATTRS:
                    _add(info, rf.get(f"{W}{attr}"))
                for attr in _THEME_ATTRS:
                    _add(info, theme.get(rf.get(f"{W}{attr}") or ""))
            for sym in root.iter(f"{W}sym"):
                _add(info, sym.get(f"{W}font"))
    info.fonts_checked = bool(info.fonts)
    return info


def _read_odt(path: Path) -> SourceInfo:
    info = SourceInfo()
    with zipfile.ZipFile(path) as z:
        for part in ("content.xml", "styles.xml"):
            if part not in z.namelist():
                continue
            root = ET.fromstring(z.read(part))
            for face in root.iter(f"{STYLE}font-face"):
                _add(info, (face.get(f"{SVG}font-family") or "").strip("'\""))
                _add(info, face.get(f"{STYLE}name"))
    info.fonts_checked = bool(info.fonts)
    return info


_RTF_CONTROL = re.compile(r"\\[a-zA-Z]+-?\d* ?|\\'[0-9a-fA-F]{2}|\\.")


def _read_rtf(path: Path) -> SourceInfo:
    info = SourceInfo()
    text = path.read_bytes().decode("latin-1")
    start = text.find("{\\fonttbl")
    if start == -1:
        return info
    # Walk the font table: each depth-2 group is one font entry. Nested groups
    # (panose, alternate names) are skipped; control words are stripped; what
    # is left before the ';' is the font's name.
    depth, entry = 0, []
    for ch in text[start:]:
        if ch == "{":
            depth += 1
            continue
        if ch == "}":
            if depth == 2:
                name = _RTF_CONTROL.sub("", "".join(entry)).split(";")[0].strip()
                _add(info, name)
                entry = []
            depth -= 1
            if depth == 0:
                break
            continue
        if depth == 2:
            entry.append(ch)
    info.fonts_checked = bool(info.fonts)
    return info


def _add(info: SourceInfo, name: Optional[str], weight: int = 1) -> None:
    if name and name.strip():
        name = name.strip()
        info.fonts.add(name)
        info.uses[name] = info.uses.get(name, 0) + weight


def read_pdf(path: Path) -> PdfInfo:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    fonts: Set[str] = set()
    seen: Set[int] = set()

    def walk(resources) -> None:
        if resources is None:
            return
        resources = resources.get_object()
        font_dict = resources.get("/Font")
        if font_dict is not None:
            for ref in font_dict.get_object().values():
                font = ref.get_object()
                base = font.get("/BaseFont")
                if base:
                    fonts.add(_SUBSET.sub("", str(base).lstrip("/")))
        xobjects = resources.get("/XObject")
        if xobjects is not None:
            for ref in xobjects.get_object().values():
                key = getattr(ref, "idnum", None) or id(ref)
                if key in seen:
                    continue
                seen.add(key)
                xobj = ref.get_object()
                if xobj.get("/Subtype") == "/Form":
                    walk(xobj.get("/Resources"))

    for page in reader.pages:
        walk(page.get("/Resources"))
    return PdfInfo(pages=len(reader.pages), fonts=fonts)


_SUBSET = re.compile(r"^[A-Z]{6}\+")
_PS_SUFFIX = re.compile(r"(psmt|mt|ps)$")


def _key(name: str) -> str:
    return re.sub(r"[^0-9a-z]", "", name.lower())


def font_was_requested(embedded: str, requested_keys: Iterable[str]) -> bool:
    """True if a font embedded in the PDF is one the document asked for.

    PDF font names carry style and vendor suffixes ("TimesNewRomanPS-BoldMT",
    "Arial,Bold", "Calibri-Light"), so this compares normalised family keys
    rather than exact names.
    """
    full = _key(embedded)
    family = _key(re.split(r"[-,]", embedded, maxsplit=1)[0])
    candidates = {full, family, _PS_SUFFIX.sub("", family)}
    for req in requested_keys:
        if not req:
            continue
        if req in candidates or full.startswith(req):
            return True
        if len(family) >= 4 and req.startswith(family):
            return True
    return False


def unexpected_fonts(pdf_fonts: Iterable[str], requested: Iterable[str]) -> list:
    """Fonts in the PDF that the document never asked for: the substitutes."""
    keys = {_key(name) for name in requested}
    return sorted({f for f in pdf_fonts if not font_was_requested(f, keys)})


def fonts_not_in_pdf(pdf_fonts: Iterable[str], requested: Iterable[str], uses: Optional[Dict[str, int]] = None) -> list:
    """Requested fonts that never made it into the PDF, most used first.

    A document's styles often name fonts no text actually uses, so this list
    can include fonts that were never needed; the ranking puts the ones that
    matter at the front.
    """
    pdf_fonts = list(pdf_fonts)
    uses = uses or {}
    missing = [
        req for req in set(requested) if not any(font_was_requested(f, {_key(req)}) for f in pdf_fonts)
    ]
    return sorted(missing, key=lambda name: (-uses.get(name, 0), name.lower()))
