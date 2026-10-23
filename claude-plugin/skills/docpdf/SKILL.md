---
name: docpdf
description: Convert Word documents (.docx, .doc, .rtf, .odt) to PDF from the command line with docpdf, which converts with LibreOffice and then checks the PDF's page count, fonts, text and pictures against the document. Use whenever the user wants a Word file as a PDF (to print, sign, send, attach or upload), asks to convert doc/docx/rtf/odt to PDF, a PDF made from a Word file looks wrong, or you need to render a Word document to check how it looks (especially on macOS).
---

# docpdf: Word documents to faithful PDFs

docpdf converts a document, then checks the result: the page count Word recorded against the PDF's, the fonts the document asks for against the fonts in the PDF, that every paragraph of text made it in, and that no picture went missing. A conversion can "succeed" and still be wrong, so the checks, and a look at the pages when it's worth it, are part of the job.

This skill needs **docpdf 0.1.5 or newer**, and **LibreOffice, which is required**: docpdf can't convert anything without it. It works wherever you can run shell commands: Claude Code on macOS, Windows or Linux, and claude.ai's own sandbox (tested 2026-10-23: Ubuntu 24.04, LibreOffice 24.2 already installed, uv available).

## 1. Find docpdf, or install it

uv and pipx put the command in `~/.local/bin`, which often isn't on the shell's PATH. So look before installing:

1. `docpdf --version`
2. If that's not found: `~/.local/bin/docpdf --version` (on Windows, `%USERPROFILE%\.local\bin\docpdf.exe --version`), or `"$(uv tool dir --bin)/docpdf" --version` when uv is installed.

Whichever works, use that exact command for everything below. If it reports a version older than 0.1.5, reinstall this release over it: `uv tool install --force git+https://github.com/RazorII/docpdf@v0.1.5` (or the same with `pipx install --force`). A plain `uv tool upgrade` keeps the old pin, so it won't move it.

Only if none of them works, install this release. Prefer uv, then pipx, then pip:

```
uv tool install git+https://github.com/RazorII/docpdf@v0.1.5
pipx install git+https://github.com/RazorII/docpdf@v0.1.5
python3 -m pip install --user git+https://github.com/RazorII/docpdf@v0.1.5
```

In a sandbox whose Python refuses pip with "externally-managed-environment" (claude.ai's does), use uv.

Then run `docpdf --engines`. Exit code 3 means LibreOffice isn't installed, and nothing can be converted until it is. Tell the user that plainly, then ask before installing it, since it's a large download:

- macOS: `brew install --cask libreoffice`
- Windows: `winget install TheDocumentFoundation.LibreOffice`
- Debian / Ubuntu: `sudo apt install libreoffice-writer` (as root in a sandbox, without `sudo`)

In a sandbox (claude.ai and the like), write PDFs where that environment hands files to the user, not just into its working folder.

## 2. Convert

```
docpdf --json FILE [FILE ...] [-o OUTDIR]
```

- Without `-o`, each PDF is written next to its document.
- docpdf refuses to replace an existing PDF. Only add `--overwrite` once the user has said the old PDF can go.
- Add `--strict` in scripts that must stop on a mismatch (exit code 4).

Exit codes: 0 converted (read the warnings anyway), 1 a document failed, 2 bad arguments, 3 no converter, 4 a strict check failed.

## 3. Read the result

For each entry in `results`:

- `ok` false: report `error` in plain words. Don't retry with other tools without saying so.
- `warnings`: every warning goes to the user, in plain words. Never call a PDF faithful while it has warnings.
- `unexpected_fonts` not empty: the converter swapped fonts. `fonts_not_in_pdf` lists the fonts the document asked for that didn't make it in, most used first, so the first one or two are usually the ones missing from this computer. Offer to install them (or ask the user where they come from), then convert again.
- `stand_ins` / `notes`: a font the document asks for is missing, and a free font with exactly the same letter widths stood in (Carlito for Calibri, Caladea for Cambria, Liberation for Arial, Times New Roman and Courier New). Lines and pages break as in Word; only the letter shapes differ slightly. Mention it in one line. It isn't a failure, unless the user needs the exact typeface (a brand font, say), in which case the original font has to be installed.
- `pages` vs `expected_pages`: a difference means the layout reflowed, usually because of the font swap.
- `missing_text` not empty: those passages aren't in the PDF. Usually a text box, header or footer was dropped. Name the first one or two.
- `images_in_pdf` lower than `images_expected`: a picture (often a logo or a signature) is missing.
- `fonts_checked` or `text_checked` false (binary `.doc`, `.rtf`): those checks couldn't run, so say so.

## 4. Decide whether to look at the pages

`visual_check.suggested` is true when a check found a problem (`problems` names which), when the document has pictures, text boxes, drawn shapes, floating objects, columns or charts (where a converter is most likely to put something in the wrong place), or when docpdf couldn't look inside the file. `visual_check.reasons` says which.

Look at the pages when `visual_check.suggested` is true, or when the PDF is going to be printed, signed, or sent to a court, an authority or a client, whatever docpdf says. Skip the look when it's false and nothing says the PDF is headed somewhere that matters: plain text and tables, every check passed.

To look, render the pages (`pdftoppm -r 60 -png file.pdf page`) and read the images. Check what a reader would notice: letterhead and logos, text boxes, tables, columns, page breaks, signature lines. For a long document (more than about 10 pages), look at the first page, the last page and the pages in `image_pages`, not every page.

## 5. Tell the user what you looked at

Always end with one short line about the pages, so the user knows what they're relying on:

- Looked at every page: "I looked at both pages: the letterhead and the signature lines are in place."
- Looked at some: name them and why, and offer the rest: "I looked at pages 1, 7 and 30 (first, last, and the ones with pictures). Want me to check the other 27?"
- Didn't look: give the reason in a few words, say when it would still be worth it, and offer: "I didn't look at the pages: plain text and every check passed. Worth a look if it's going to print. Want me to?"

## Checking a Word document you made or edited

When another skill has just written or changed a `.docx` and you want to see how it looks, render it with docpdf (`docpdf -o <scratch folder> file.docx`, then `pdftoppm`). On macOS this matters: a LibreOffice helper that forces `SAL_USE_VCLPLUGIN=svp` (Anthropic's `docx` skill does, in `scripts/office/soffice.py`) can't see the Mac's fonts, so its renders show substitute fonts and shifted line and page breaks. Judging layout from such a render leads to "fixing" problems that aren't there, or missing ones that are.

## Don't

- Don't call `soffice --headless --convert-to pdf` directly on a Mac. It silently substitutes the Mac's own fonts; docpdf exists to avoid that.
- Don't use pandoc, textutil or Quick Look for this. They rebuild the layout instead of rendering it.
- Don't edit the original document to make a conversion pass.
