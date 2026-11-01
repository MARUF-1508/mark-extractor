# Result Desk

A website with a **local Python backend** for extracting student rolls and marks from PDFs and images. Upload a marksheet, inspect each row beside its original source, correct or verify values, and download an Excel workbook.

The backend runs on the same computer as your browser. PDF parsing, image OCR, file storage, and Excel generation all happen locally. There are no cloud OCR calls, accounts, API keys, CDN scripts, or remote fonts. Initial dependency installation requires internet; normal use works offline.

## Run on Windows 10

1. Install **Python 3.11 x64** from [python.org](https://www.python.org/downloads/), including the Python launcher.
2. Double-click **Setup.bat** once to install the dependencies and check the bundled OCR models.
3. Double-click **Start.bat**. The backend starts and opens **http://127.0.0.1:8000** in your browser.
4. Keep the terminal open while using the website. Press **Ctrl+C** in that terminal to stop the backend. Closing the browser tab leaves the backend running.

Already set up an older desktop version? Run Setup.bat again to install the web backend dependencies, then use Start.bat.

## Run from a terminal

```sh
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m result_automation
```

The default entry point now starts the website. These equivalent launch commands are available:

```sh
result-web
python -m result_automation.web --no-browser --port 8000
python -m result_automation.web "test_sources/CSE-305-TUTORIAL-MARKS.pdf"
python -m result_automation.web --data-dir ./my-local-reviews --port 8001
```

`--no-browser` leaves browser opening to you. An optional positional PDF/image imports a copy on startup. `--port` changes the port; `--data-dir` changes persistent storage. The server binds to **127.0.0.1** for single-user local use. This project does not configure public hosting, remote user authentication, or multi-worker deployment.

## Use the website

- **Upload:** choose a PDF, PNG, JPEG, TIFF, BMP, or WebP, or drag it onto the page. Files can contain up to 50 pages and be up to 50 MB. Password-protected PDFs can be opened by entering their password in the upload dialog. Extraction runs in a background queue, with live progress and cancellation between pages.
- **Try an example:** the home page offers the example PDFs available in this checkout. Each opens as a new local document. Uploaded copies and saved reviews appear in the sidebar and document library.
- **Check the columns:** green outlines the roll column; amber outlines marks. The highest-scoring marks column is selected by default, and the Marks column menu lists the other candidates. A roll header identifies the correct column even if a serial column comes first. Rotated PDF headers, skewed scans, uneven lighting, and headerless continuation pages are supported.
- **Inspect a row:** click a result or a row in the preview to select it. See its original crop, original reading, page, method, OCR confidence, and validation issues. Fit/zoom switches between full-page and scrollable width views.
- **Edit or verify:** edit roll/marks and save, click Review in a row, or press Enter on a selected row to mark the reading verified. Corrections save automatically on the backend. The original reading remains in the review data. Missing values, duplicates, and mark-range problems still need correction after verification.
- **Select other columns:** click Roll column or Marks column, then drag around the student cells from first row to last, excluding the header. Re-extract the current page, or apply those column positions to all pages. Each continuation page retains its own vertical row area. Re-extraction replaces affected edits and verification. Discard abandons a pending selection.
- **Validate:** open Validation settings to override the maximum mark for all pages, list absent/withheld codes such as `AB` or `W`, or accept fraction marks such as `12/15`. Blank restores the maximum from the selected column's header, such as `(40)` or `(40 Marks)`. The Low confidence filter and sort make OCR readings that need a second look easy to find.
- **Choose columns & preview:** open the spreadsheet builder to select one or more detected source columns, including names, IDs, attendance, and individual test marks. Draw custom source regions when needed. Rename headings, drag columns or use left/right arrows to reorder them, and edit cell values directly in the preview. Choose Text / identifier to preserve leading zeros, or Number for numeric marks.
- **Export Excel:** opens that same preview before downloading a real `.xlsx` workbook. The Results sheet contains exactly the selected headings and column order, with all student rows (including rows hidden by the main search/filter). Page, status, issues, and original readings stay on the separate Source and review sheet. The more menu also offers CSV through the same builder, and the original uploaded file.
- **Add/delete:** add a student row when recognition missed it, remove an unwanted row from the editor, or delete a document and its saved review from the more menu. Deleting a document removes its uploaded copy; files outside the backend storage folder are untouched.

Keyboard shortcuts: **↑/↓** moves the selected row through the current filter and sort, **Home/End** jumps to the first or last visible row, **R** or **Enter** marks the selected row reviewed, **/** focuses roll search, **Ctrl/Cmd+E** exports Excel, and **Esc** cancels column-drawing mode.

### Build an export

1. Click **Choose columns & preview** or **Export Excel**. Roll and Marks are selected initially.
2. Check the source columns you want. For a column that was not detected, click **Draw a column**, drag around its student cells, and give it a name. The **Use this column on all pages** option uses each page's own student-row area; uncheck it for a page-specific column.
3. Edit headings directly in the preview. Move columns by dragging a handle onto another header or using its left/right arrows. Remove a column with its × button. You can select a single column, or up to 32.
4. Inspect and correct cell values. Blank source cells stay in their rows; they are not replaced by zero or shifted to another student. Names retain spaces, and identifier columns stay text.
5. Click **Save layout** to keep working later, or **Export Excel** to save the layout and download the workbook. Closing with unsaved changes lets you discard the draft. Preview changes are kept together until Save or Export; they do not overwrite the saved review merely by opening the builder.

Saved selections, names, order, formats, and custom cell corrections survive browser and backend restarts. Editing the built-in Roll/Marks cells in the builder also updates those values in the main review, while retaining their original source readings. Re-extracting a page replaces its source readings and clears its custom cell corrections; saved column names and order remain. Downloads check the preview's revision so another tab cannot silently change the exported layout after you inspected it.

A **Ready** row has no validation issues; it has not necessarily been checked by a person. **Reviewed** means you verified it and no issues remain. **Needs review** identifies missing/invalid values, duplicates, out-of-range marks, or OCR awaiting verification. Every image OCR result initially requires review. A blank mark remains blank, and zero remains zero; missing cells never shift subsequent marks to another student.

## Local backend and saved data

The frontend is plain HTML/CSS/JavaScript served by **FastAPI** from the same origin. No Node.js or frontend build process is required. **Uvicorn** runs the backend. A single extraction worker serializes PDFium and CPU OCR operations while the API stays responsive.

Storage defaults:

- Windows: `%LOCALAPPDATA%\ResultDesk`
- Linux/macOS: `.result-desk/` under the launch directory
- Override with `--data-dir` or the `RESULT_DESK_DATA_DIR` environment variable.

Each document has a generated ID, its uploaded source copy, page previews, job metadata, and an atomic JSON review file. Reloading the browser or restarting the server preserves completed reviews. An interrupted extraction is marked as interrupted after restart. Edits use revision numbers so a stale browser tab cannot silently overwrite a newer review. Upload names are sanitized, and loopback host/origin checks protect the local API.

The backend is intended for **one server process**. Do not run multiple processes against the same storage directory. Back up the whole directory if you need to preserve both source files and reviews. Exported spreadsheets contain student data, just like the source sheets.

### API

OpenAPI schema: **/api/openapi.json**. No external Swagger scripts are required.

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/api/health` | Backend status and limits |
| GET/POST | `/api/documents` | List documents / multipart upload (`file`, optional `force_ocr`) |
| GET/DELETE | `/api/documents/{id}` | Read a review / remove a document |
| POST | `/api/documents/{id}/cancel` | Cancel extraction |
| GET | `/api/documents/{id}/pages/{page}.png` | Source page preview |
| GET | `/api/documents/{id}/source` | Original uploaded file |
| POST | `/api/documents/{id}/rows` | Add a student row |
| PATCH/DELETE | `/api/documents/{id}/rows/{row}` | Correct / delete a row |
| PATCH | `/api/documents/{id}/settings` | Set the maximum mark |
| POST | `/api/documents/{id}/reextract` | Re-extract a page, all pages, or auto-detect |
| GET | `/api/documents/{id}/columns` | Detect available columns and open a saved spreadsheet preview |
| POST | `/api/documents/{id}/columns/preview` | Extract a column selection without saving it |
| PUT | `/api/documents/{id}/columns` | Save selected columns, names, formats, order, and cell corrections |
| GET | `/api/documents/{id}/export/xlsx` | Download Excel |
| GET | `/api/documents/{id}/export/csv` | Download CSV |

Review mutations include the current integer `version`; stale updates receive HTTP 409. Original source readings are retained when rows are edited.

Column plans contain ordered `columns` with an `id`, `name`, `kind` (`text` or `number`), `source` (`roll`, `mark`, or `region`), and page-indexed normalized `regions` (`[left, top, right, bottom]`). Optional `overrides` maps row IDs to column IDs and corrected strings. Custom regions are read within the existing student-row boundaries, preserving blank cells and row alignment. Export endpoints accept `?version=` to ensure the downloaded workbook matches the inspected preview. Older sessions without a column plan remain compatible.

## Extraction engine

1. **PDF text first:** PDFium provides character coordinates, including rotated headers. Usable embedded text avoids recognition errors and OCR startup. Scanned pages fall back to image OCR.
2. **Local CPU OCR:** RapidOCR runs its bundled PP-OCRv6 small detection/recognition models and text-orientation classifier with ONNX Runtime. Explicit model paths prevent runtime downloads; missing assets produce a repair/reinstall error. ONNX Runtime telemetry is disabled.
3. **Table geometry:** OpenCV detects ruled rows and columns. Headerless continuation pages inherit column positions. Unruled pages use text alignment as a fallback and may need manual column selection.
4. **Pair and validate:** read roll and marks within the same row, preserve decimals and blanks, then check format, duplicates, and ranges.

The supplied CSE 251 and OOAD examples have 54 and 52 rows, respectively. Tests compare every pair with independently transcribed fixtures, through PDF text and rasterized OCR. The latest CSE 305 test source has rotated headers, two roll columns, and 52 student rows; it selects Class Roll and TOTAL (40 Marks), excluding the serial and Exam Roll columns.

Use upright, flat, clearly printed tables. Automatic deskew, perspective correction, handwriting recognition, and multiple independent tables on a page are not implemented. Bengali digit characters in extracted text normalize to `0–9`; Bengali-image OCR is not validated by these samples. Inspect regions and row counts before using results.

## Tests and diagnostics

The `examples/` and `test_sources/` directories and PDF files are intentionally excluded from Git. Sample-dependent tests require your local copies of those private PDFs; keep them in the filenames referenced below and in the tests. They are not included when cloning the repository.

```sh
python -m pytest -m "not ocr" -q
python -m pytest -m ocr -q
python -m result_automation --check-offline offline-check.json
```

Tests cover PDF and image input, complete sample pairs, blank cells, leading zeros, decimal marks, duplicate/range validation, persistent reviews, multipart uploads, background jobs, cancellation, revision conflicts, page previews, actual Excel/CSV downloads, invalid files, and request guards. Column-builder tests check source-column discovery, spaced names, custom regions across pages, single/multiple-column exports, renamed/reordered headings, edited values, trailing blank rows, literal formula-like text, unsaved previews, and saved layouts after restart. OCR tests block Python socket/DNS access to verify local inference.

The web frontend is also checked in the collaborative browser for uploads, row edits, reload persistence, filters, column selection, exports, and responsive layouts. Windows-native startup and executable packaging require validation on a Windows computer; development verification runs in Linux.

Core files:

- `src/result_automation/web.py`: FastAPI routes and local web server.
- `src/result_automation/web_store.py`: job queue and durable local reviews.
- `src/result_automation/static/`: self-contained web interface.
- `document.py`, `ocr.py`, `extract.py`: shared extraction engine.
- `storage.py`: review files and Excel/CSV generation.
- `columns.py`: source-column discovery and row-aligned spreadsheet previews.

## Other entry points

The command-line extractor remains available:

```sh
result-extract "examples/CSE 251_CT_marks.pdf" -o results.xlsx --session review.json
result-extract examples/OOAD_tutorial.pdf --force-ocr -o results.csv
```

The previous native desktop interface remains accessible with **`result-desktop`** or **`python -m result_automation --desktop`**. It requires Tcl/Tk.

On Windows, **Build-Windows.bat** creates `dist/ResultDesk/ResultDesk.exe` with the local backend, website assets, Python runtime, and OCR models. Distribute the entire ResultDesk folder. The executable opens the website and keeps a server terminal available; close that terminal to stop it. The build performs an offline OCR check on the frozen executable. Windows builds must be made on Windows, and may require the Microsoft Visual C++ 2015–2022 x64 runtime. See `THIRD_PARTY_NOTICES.md` for component notices.
