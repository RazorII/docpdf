# docpdf

[![test](https://github.com/RazorII/docpdf/actions/workflows/test.yml/badge.svg)](https://github.com/RazorII/docpdf/actions/workflows/test.yml)

Convert Word documents to PDF from the command line, then check that the PDF actually matches the document.

```
$ docpdf contract.docx
OK    contract.docx -> contract.pdf  (2 pages, 1.4 s)
```

Most headless converters stop at "a PDF came out". docpdf also checks the two things that go wrong quietly:

- **Page count.** Word records how many pages a .docx had when it was last saved. If the PDF has a different count, the layout shifted.
- **Fonts.** If the PDF contains a font the document never asked for, the converter couldn't find the right one and swapped in a lookalike. That changes line breaks, spacing and often the page count.

Either problem prints a warning. With `--strict` it fails instead, so a script can stop before a bad PDF goes to print.

```
$ docpdf letter.docx
WARN  letter.docx -> letter.pdf  (3 pages, 1.5 s)
      Microsoft Office Word counted 2 pages when it last saved this file, but the PDF has 3. The layout has probably shifted.
      Fonts were swapped: the PDF uses LinuxLibertineG, which the document doesn't ask for. Most likely missing from this computer: Tahoma. Install those fonts and convert again.
```

## Why

I needed a few Word contracts as print-ready PDFs on a Mac. `soffice --headless --convert-to pdf` reported success every time. The PDFs looked plausible, but every page was set in the wrong font.

The cause is a macOS trap. With `--headless`, LibreOffice switches to a renderer that can't see the Mac's own fonts in `/System/Library/Fonts`, so it substitutes without saying so. In my case Tahoma came out as Linux Libertine G. docpdf runs LibreOffice's macOS renderer instead (`SAL_USE_VCLPLUGIN=osx`). It still runs headless, with no window, no Dock icon and no change of focus, and it sees every font the Mac has. If that renderer can't start (it needs a logged-in session), docpdf falls back to the plain one and the font check tells you what was swapped.

## Install

You need Python 3.9 or newer and LibreOffice.

```
uv tool install git+https://github.com/RazorII/docpdf
```

or with pipx:

```
pipx install git+https://github.com/RazorII/docpdf
```

LibreOffice:

- macOS: `brew install --cask libreoffice`
- Windows: `winget install TheDocumentFoundation.LibreOffice`
- Debian / Ubuntu: `sudo apt install libreoffice-writer`

Run `docpdf --engines` to see what it found. If LibreOffice lives somewhere unusual, point `DOCPDF_SOFFICE` at its `soffice` binary.

## Use

```
docpdf report.docx                 # writes report.pdf next to it
docpdf *.docx -o pdfs/             # several at once, into another folder
docpdf letter.doc --strict         # exit 4 if a check finds a mismatch
docpdf contract.docx --json        # machine-readable results
docpdf --engines                   # list the converters installed
```

An existing PDF is never replaced unless you pass `--overwrite`. The original document is never touched: docpdf converts a copy in a temporary folder.

Formats: `.docx`, `.doc`, `.rtf` and `.odt`. The font check covers `.docx`, `.rtf` and `.odt`. The page-count check needs a `.docx` whose saving app recorded a page count, which Word always does.

| Exit code | Meaning |
|---|---|
| 0 | Every document converted (warnings may have been printed) |
| 1 | At least one document failed to convert |
| 2 | Bad command-line arguments |
| 3 | No converter installed |
| 4 | `--strict` and at least one check found a mismatch |

## Converters

docpdf uses the most faithful converter installed, best first.

| Converter | macOS | Windows | Linux |
|---|---|---|---|
| LibreOffice | yes | yes | yes |
| Microsoft Word | planned | planned | n/a |

Word is the reference renderer for Word files, so it will go first once its automation has been tested against a licensed copy. Without a Microsoft 365 subscription, Word for Mac runs read-only and refuses to save, PDF included (tested with Word 16.114 on macOS 27). If you have a licensed Word on a Mac or on Windows and would like to help test, please open an issue.

## Use it from Claude Code

docpdf comes with a Claude Code plugin. Its skill tells Claude when to use docpdf, how to read the warnings and to look at every page before handing a PDF over.

```
claude plugin marketplace add RazorII/claude-plugins
claude plugin install docpdf@razorii
```

The plugin installs docpdf for you on first use if it isn't there yet.

## Development

```
uv venv && uv pip install -e ".[test]"
pytest
```

The tests build their own small Word documents, so the repo carries no binaries. Tests that convert skip themselves when LibreOffice isn't installed. CI runs the suite on macOS, Windows and Linux on every push (first green run: LibreOffice 26.8.1 on macOS, 26.2.6 on Windows, 24.2.7 on Ubuntu).

## License

MIT
