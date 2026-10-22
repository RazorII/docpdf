---
name: docpdf
description: Convert Word documents (.docx, .doc, .rtf, .odt) to PDF from the command line with docpdf, which uses the most faithful converter installed and then checks the PDF's page count and fonts against the document. Use whenever the user wants a Word file as a PDF (to print, sign, send, attach or upload), asks to convert doc/docx/rtf/odt to PDF, a PDF made from a Word file looks wrong, or you need to render a Word document to check how it looks (especially on macOS).
---

# docpdf: Word documents to faithful PDFs

docpdf converts a document, then checks the result: the page count Word recorded against the PDF's, and the fonts the document asks for against the fonts embedded in the PDF. A conversion can "succeed" and still be wrong, so the checks and a look at the pages are part of the job, not extras.

This skill needs **docpdf 0.1.1 or newer**.

## 1. Find docpdf, or install it

uv and pipx put the command in `~/.local/bin`, which often isn't on the shell's PATH. So look before installing:

1. `docpdf --version`
2. If that's not found: `~/.local/bin/docpdf --version` (on Windows, `%USERPROFILE%\.local\bin\docpdf.exe --version`), or `"$(uv tool dir --bin)/docpdf" --version` when uv is installed.

Whichever works, use that exact command for everything below. If it reports a version older than 0.1.1, upgrade it with `uv tool upgrade docpdf` (or `pipx upgrade docpdf`).

Only if none of them works, install it. Prefer uv, then pipx, then pip:

```
uv tool install git+https://github.com/RazorII/docpdf
pipx install git+https://github.com/RazorII/docpdf
python3 -m pip install --user git+https://github.com/RazorII/docpdf
```

Then run `docpdf --engines`. Exit code 3 means no converter is installed. Ask the user before installing LibreOffice, since it's a large download:

- macOS: `brew install --cask libreoffice`
- Windows: `winget install TheDocumentFoundation.LibreOffice`
- Debian / Ubuntu: `sudo apt install libreoffice-writer`

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
- `pages` vs `expected_pages`: a difference means the layout reflowed, usually because of the font swap.
- `fonts_checked` false (binary `.doc`): the font check couldn't run, so say so.

## 4. Look at the pages before handing the PDF over

Render the pages to images (for example `pdftoppm -r 60 -png file.pdf page`) or open the PDF, and check what the reader will see: letterhead and logos, tables and boxes, columns, page breaks and signature lines. Mention anything that looks off, even when docpdf reported no warnings.

## Checking a Word document you made or edited

When another skill has just written or changed a `.docx` and you want to see how it looks, render it with docpdf (`docpdf -o <scratch folder> file.docx`, then `pdftoppm`). On macOS this matters: a LibreOffice helper that forces `SAL_USE_VCLPLUGIN=svp` (Anthropic's `docx` skill does, in `scripts/office/soffice.py`) can't see the Mac's fonts, so its renders show substitute fonts and shifted line and page breaks. Judging layout from such a render leads to "fixing" problems that aren't there, or missing ones that are.

## Don't

- Don't call `soffice --headless --convert-to pdf` directly on a Mac. It silently substitutes the Mac's own fonts; docpdf exists to avoid that.
- Don't use pandoc, textutil or Quick Look for this. They rebuild the layout instead of rendering it.
- Don't edit the original document to make a conversion pass.
