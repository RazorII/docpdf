"""docpdf: convert Word documents to PDF, then check the PDF matches."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional

from . import __version__
from .checks import fonts_not_in_pdf, read_pdf, read_source, stand_ins, unexpected_fonts
from .content import VISUAL_TRIGGERS, missing_text, read_content, read_pdf_content
from .engines import Engine, EngineError, all_engines, get_engine

SUPPORTED = (".docx", ".doc", ".rtf", ".odt")

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2
EXIT_NO_ENGINE = 3
EXIT_CHECK = 4


@dataclass
class Result:
    source: str
    pdf: Optional[str] = None
    engine: Optional[str] = None
    ok: bool = False
    pages: Optional[int] = None
    expected_pages: Optional[int] = None
    counted_by: Optional[str] = None
    unexpected_fonts: List[str] = field(default_factory=list)
    stand_ins: List[dict] = field(default_factory=list)
    fonts_not_in_pdf: List[str] = field(default_factory=list)
    fonts_checked: bool = False
    missing_text: List[str] = field(default_factory=list)
    text_checked: bool = False
    images_expected: Optional[int] = None
    images_in_pdf: Optional[int] = None
    image_pages: List[int] = field(default_factory=list)
    layout: List[str] = field(default_factory=list)
    visual_check: dict = field(default_factory=lambda: {"suggested": False, "reasons": []})
    problems: List[str] = field(default_factory=list)  # one short name per warning, e.g. "fonts were swapped"
    warnings: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    error: Optional[str] = None
    seconds: float = 0.0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="docpdf",
        description="Convert Word documents (.docx, .doc, .rtf, .odt) to PDF with the most faithful "
        "converter installed, then check the PDF's page count, fonts, text and pictures against the document.",
    )
    parser.add_argument("files", nargs="*", type=Path, help="documents to convert")
    parser.add_argument("-o", "--outdir", type=Path, help="write PDFs here (default: next to each document)")
    parser.add_argument(
        "-e", "--engine", default="auto", choices=["auto"] + [e.name for e in all_engines()],
        help="converter to use (default: the best one installed)",
    )
    parser.add_argument("--overwrite", action="store_true", help="replace a PDF that already exists")
    parser.add_argument("--strict", action="store_true", help="fail (exit 4) when a check finds a mismatch")
    parser.add_argument("--timeout", type=float, default=180, help="seconds allowed per document (default 180)")
    parser.add_argument("--json", action="store_true", help="print results as JSON")
    parser.add_argument("--engines", action="store_true", help="list the converters found on this computer")
    parser.add_argument("--version", action="version", version=f"docpdf {__version__}")
    args = parser.parse_args(argv)

    if args.engines:
        return _list_engines(args.json)
    if not args.files:
        parser.error("give at least one document to convert")

    engine = _pick_engine(args.engine)
    if engine is None:
        msg = (
            "No converter found. Install LibreOffice (https://www.libreoffice.org/download/) "
            "and run docpdf again."
        )
        if args.json:
            print(json.dumps({"error": msg, "results": []}, indent=2))
        else:
            print(f"docpdf: {msg}", file=sys.stderr)
        return EXIT_NO_ENGINE

    if args.outdir:
        args.outdir.mkdir(parents=True, exist_ok=True)

    results = [convert_one(path, engine, args.outdir, args.overwrite, args.timeout) for path in args.files]

    if args.json:
        print(json.dumps({"engine": engine.name, "results": [asdict(r) for r in results]}, indent=2))
    else:
        for result in results:
            _print_human(result)

    if any(not r.ok for r in results):
        return EXIT_FAILED
    if args.strict and any(r.warnings for r in results):
        return EXIT_CHECK
    return EXIT_OK


def convert_one(src: Path, engine: Engine, outdir: Optional[Path], overwrite: bool, timeout: float) -> Result:
    started = time.monotonic()
    result = Result(source=str(src), engine=engine.name)
    try:
        if not src.is_file():
            raise EngineError("file not found.")
        if src.suffix.lower() not in SUPPORTED:
            raise EngineError(f"not a supported document type (use {', '.join(SUPPORTED)}).")
        dest = (outdir or src.parent) / (src.stem + ".pdf")
        result.pdf = str(dest)
        if dest.exists() and not overwrite:
            raise EngineError(f"{dest.name} already exists. Use --overwrite to replace it, or -o to write elsewhere.")

        with tempfile.TemporaryDirectory(prefix="docpdf-") as tmp:
            tmp = Path(tmp)
            # Convert a copy under a plain name: odd characters in the real name
            # can't trip the converter, and no lock files land next to the original.
            (tmp / "in").mkdir()
            (tmp / "out").mkdir()
            staged = tmp / "in" / ("document" + src.suffix.lower())
            shutil.copyfile(src, staged)
            produced = engine.convert(staged, tmp / "out", timeout)
            if engine.note:
                result.warnings.append(engine.note)
                result.problems.append("the plain renderer was used")
            _check(result, src, produced)
            partial = dest.with_name(dest.name + ".docpdf-partial")
            shutil.copyfile(produced, partial)
            os.replace(partial, dest)
        result.ok = True
    except EngineError as exc:
        result.error = str(exc)
        if result.pdf and not Path(result.pdf).exists():
            result.pdf = None
    result.seconds = round(time.monotonic() - started, 2)
    return result


def _check(result: Result, src: Path, pdf: Path) -> None:
    if pdf.stat().st_size == 0:
        raise EngineError("the converter wrote an empty PDF.")
    try:
        info = read_pdf(pdf)
    except Exception as exc:  # pypdf raises many types for a broken file
        raise EngineError(f"the converter wrote a PDF that can't be read ({exc}).") from exc
    if info.pages == 0:
        raise EngineError("the converter wrote a PDF with no pages.")
    result.pages = info.pages

    source = read_source(src)
    if source.pages_note:
        result.notes.append(source.pages_note)
    if source.pages:
        result.expected_pages = source.pages
        result.counted_by = source.application
        if source.pages != info.pages:
            who = source.application or "The app that last saved it"
            result.warnings.append(
                f"{who} counted {source.pages} page{'s' if source.pages != 1 else ''} when it last saved "
                f"this file, but the PDF has {info.pages}. The layout has probably shifted."
            )
            result.problems.append("the page count differs")

    result.fonts_checked = source.fonts_checked
    if source.fonts_checked:
        substitutes = unexpected_fonts(info.fonts, source.fonts)
        pairs, result.unexpected_fonts = stand_ins(substitutes, source.fonts, info.fonts)
        result.stand_ins = [{"requested": original, "used": used} for original, used in pairs]
        result.fonts_not_in_pdf = fonts_not_in_pdf(info.fonts, source.fonts, source.uses)
        for original, used in pairs:
            result.notes.append(
                f"{original} isn't on this computer, so {used} stood in. It has the same letter widths, "
                "so lines and pages break exactly as in Word; only the letter shapes differ slightly."
            )
        if result.unexpected_fonts:
            covered = {original for original, _ in pairs}
            missing = [f for f in result.fonts_not_in_pdf if f not in covered]
            likely = [f for f in missing if source.uses.get(f)][:4] or missing[:4]
            hint = (
                f" Most likely missing from this computer: {', '.join(likely)}. Install those fonts and convert again."
                if likely
                else " The document doesn't name the font it expected there, so it was probably a default font."
            )
            result.warnings.append(
                f"Fonts were swapped: the PDF uses {', '.join(result.unexpected_fonts)}, which the document "
                f"doesn't ask for.{hint}"
            )
            result.problems.append("fonts were swapped")

    _check_content(result, src, pdf)


def _check_content(result: Result, src: Path, pdf: Path) -> None:
    content = read_content(src)
    try:
        in_pdf = read_pdf_content(pdf)
    except Exception as exc:  # pypdf raises many types for odd files
        result.notes.append(f"The text and image checks couldn't read the PDF ({exc}).")
        content.text_checked = content.images_checked = False
        in_pdf = None
    result.layout = content.features

    if in_pdf is not None:
        result.image_pages = in_pdf.image_pages
    if in_pdf is not None and content.text_checked:
        result.text_checked = True
        if content.paragraphs and not in_pdf.text:
            result.warnings.append("The PDF has no readable text, so it can't be searched or copied from.")
            result.problems.append("the PDF has no readable text")
        else:
            result.missing_text = missing_text(content.paragraphs, in_pdf.text)
            if result.missing_text:
                more = len(result.missing_text) - 2
                shown = "; ".join(f'"{s}"' for s in result.missing_text[:2])
                result.warnings.append(
                    f"Some of the document's text isn't in the PDF: {shown}"
                    + (f" and {more} more passage{'s' if more != 1 else ''}" if more > 0 else "")
                    + ". A text box, header or footer may have been dropped."
                )
                result.problems.append("text is missing")
    if in_pdf is not None and content.images_checked:
        result.images_expected = content.images
        result.images_in_pdf = in_pdf.images
        if in_pdf.images < content.images:
            result.warnings.append(
                f"The document has {content.images} picture{'s' if content.images != 1 else ''} "
                f"but the PDF has {in_pdf.images}. A picture may be missing."
            )
            result.problems.append("a picture is missing")

    reasons = list(result.problems)
    reasons += [f for f in content.features if f in VISUAL_TRIGGERS]
    if not content.text_checked:
        reasons.append(f"docpdf can't look inside {src.suffix.lower()} files")
    result.visual_check = {"suggested": bool(reasons), "reasons": reasons}


def _pick_engine(name: str) -> Optional[Engine]:
    if name != "auto":
        engine = get_engine(name)
        return engine if engine.available() else None
    for engine in all_engines():
        if engine.available():
            return engine
    return None


def _list_engines(as_json: bool) -> int:
    rows = []
    for engine in all_engines():
        rows.append(
            {
                "name": engine.name,
                "label": engine.label,
                "available": engine.available(),
                "location": engine.location(),
                "version": engine.version() if engine.available() else None,
            }
        )
    if as_json:
        print(json.dumps({"engines": rows}, indent=2))
    else:
        print("Converters, best first (auto uses the first one available):")
        for row in rows:
            if row["available"]:
                version = f" {row['version']}" if row["version"] else ""
                print(f"  {row['label']}{version}: {row['location']}")
            else:
                print(f"  {row['label']}: not installed")
    return EXIT_OK if any(r["available"] for r in rows) else EXIT_NO_ENGINE


def _print_human(r: Result) -> None:
    name = Path(r.source).name
    if not r.ok:
        print(f"FAIL  {name}: {r.error}", file=sys.stderr)
        return
    status = "WARN" if r.warnings else "OK  "
    pages = f"{r.pages} page{'s' if r.pages != 1 else ''}"
    print(f"{status}  {name} -> {r.pdf}  ({pages}, {r.seconds:.1f} s)")
    for warning in r.warnings:
        print(f"      {warning}")
    for note in r.notes:
        print(f"      Note: {note}")
    if not r.fonts_checked:
        print("      Fonts not checked: docpdf can't read the font list of this file type.")
    if r.visual_check.get("suggested"):
        print(f"      Worth a look at the pages: {', '.join(r.visual_check['reasons'])}.")


if __name__ == "__main__":
    sys.exit(main())
