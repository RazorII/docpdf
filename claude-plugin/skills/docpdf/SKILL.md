---
name: docpdf
description: Convert Word documents (.docx, .doc, .rtf, .odt) to PDF from the command line with docpdf, which uses the most faithful converter installed and then checks the PDF's page count and fonts against the document. Use whenever the user wants a Word file as a PDF (to print, sign, send, attach or upload), asks to convert doc/docx/rtf/odt to PDF, or a PDF made from a Word file looks wrong.
---

# docpdf: Word documents to faithful PDFs

docpdf converts a document, then checks the result: the page count Word recorded against the PDF's, and the fonts the document asks for against the fonts embedded in the PDF. A conversion can "succeed" and still be wrong, so the checks and a look at the pages are part of the job, not extras.

## 1. Make sure docpdf is installed

Run `docpdf --version`. If the command isn't found, install it. Prefer uv, then pipx, then pip:

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

## Don't

- Don't call `soffice --headless --convert-to pdf` directly on a Mac. It silently substitutes the Mac's own fonts; docpdf exists to avoid that.
- Don't use pandoc, textutil or Quick Look for this. They rebuild the layout instead of rendering it.
- Don't edit the original document to make a conversion pass.
