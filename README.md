# Rexel & Würth Datasheet Downloader

Python browser automation for collecting electrical product datasheets from **Rexel** and **Würth** based on article numbers listed in an Excel workbook.

> **Portfolio project / source release.** The source was extracted from a larger working directory and has **not** been end-to-end tested against the live supplier websites in this release. Supplier page structure, availability, and access rules may change.

## Problem

Engineering procurement and documentation workflows often require manually looking up dozens of product identifiers and saving the corresponding technical PDFs. This script automates much of the repetitive lookup, download, naming, and reporting process.

## Features

- Reads Excel workbooks and extracts article numbers under engineering position codes.
- Supports Rexel numeric article identifiers and Würth identifiers beginning with `W`.
- Filters a configurable range of positions.
- Uses Playwright to navigate product pages and locate PDF datasheets.
- Checks downloaded documents and organizes output into position-group folders.
- Handles duplicate files and produces an Excel run log with **Summary**, **Details**, and **Failed** worksheets.
- Includes error classification to help with manual follow-up.

## Technology

Python · Playwright · pandas · openpyxl

## Setup

Requires Python 3.10+ and a supported Chromium installation through Playwright.

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS / Linux:
# source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
```

Place your **own authorized** Excel workbook at `input/artikli.xlsx`. The original workbook is intentionally excluded from this repository.

## Configure and run

Edit the constants near the top of `app.py`:

```python
EXCEL_FILE = "input/artikli.xlsx"
COLUMN = "A"
OUTPUT_DIR = "output"
START_POSITION = "1.16.001"
END_POSITION = "1.16.090"
HEADLESS = True
```

The workbook must follow the original parser's layout: a position code such as `1.16.001` followed by rows containing article identifiers in the selected column. The program uses the active worksheet by default. Review `excel_parser.py` before preparing a workbook; this is not a generic arbitrary-column Excel importer.

Run from the repository directory:

```bash
python app.py
```

The script writes PDFs under `output/<position-group>/` and an Excel download log in the output directory. The output folder is intentionally not committed.

## Source layout

| File | Purpose |
| --- | --- |
| `app.py` | Batch orchestration, configuration, reporting |
| `excel_parser.py` | Excel parsing and article/position extraction |
| `rexel_downloader.py` | Playwright-based supplier lookup and downloads |
| `file_utils.py` | Safe filenames and unique file paths |
| `requirements.txt` | Python dependencies |

## Limitations and responsible use

- Supplier websites can change; selectors and URL patterns may require maintenance.
- Automated browsing is subject to supplier terms, rate limits, and applicable permissions. Use only where authorized; do not bypass access controls or anti-bot measures.
- Product PDFs remain the intellectual property of their respective owners and are **not** redistributed here.
- Some products may have no accessible datasheet; failed items are recorded for manual review.
- This is a command-line script with configuration constants, **not** a packaged GUI or an official Rexel/Würth integration.

## Privacy and publication

No original company workbook, downloaded PDFs, internal product lists, or execution logs are included. Before publishing screenshots or sample input, use synthetic data and confirm you have permission to share them.

## Suggested portfolio description

*Built a Python automation tool to process engineering Excel material lists, locate electrical-product technical datasheets, organize downloaded documents by project position, and generate structured Excel reports for successful and failed lookups.*
