# docpdf plugin for Claude

Turns Word documents (.docx, .doc, .rtf, .odt) into PDFs and checks that each PDF actually matches its document: the page count, the fonts, every paragraph of text and every picture. When a check fails, Claude tells you what went wrong. It also tells you whether it looked at the pages itself, and offers to when it didn't.

## Requirements

- **LibreOffice is required.** docpdf converts with LibreOffice and can't convert anything without it. If it's missing, Claude says so and asks before installing it, because it's a large download.
- **A place where Claude can run commands:** Claude Code on macOS, Windows or Linux, or claude.ai's own sandbox (tested 2026-10-23: LibreOffice is already installed there).
- Python 3.9 or newer, to install the `docpdf` command.

## What the plugin runs and downloads

- The plugin itself is one skill: instructions that tell Claude how to use the `docpdf` command. It has no hooks, no MCP servers and no background processes.
- If `docpdf` isn't installed, Claude installs the release this plugin belongs to from [github.com/RazorII/docpdf](https://github.com/RazorII/docpdf), pinned to its version tag, with uv, pipx or pip. Its only dependency is [pypdf](https://pypi.org/project/pypdf/), from PyPI.
- If LibreOffice is missing, Claude offers to install it with your system's package manager (Homebrew, winget or apt), and only does so with your OK.
- Conversion runs entirely on your machine. docpdf sends nothing anywhere and has no telemetry ([privacy policy](https://github.com/RazorII/docpdf/blob/main/PRIVACY.md)).
- To check how a PDF looks, Claude may render its pages to images on your machine and look at them.

## Install

```
claude plugin marketplace add RazorII/claude-plugins
claude plugin install docpdf@razorii
```

Source, issues and the full documentation: [github.com/RazorII/docpdf](https://github.com/RazorII/docpdf). MIT licensed.
