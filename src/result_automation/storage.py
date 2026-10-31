from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from .document import open_document
from .extract import number, validate
from .models import Document, ExportColumn, Layout, MarkCandidate, Record, Word

SCHEMA = "result-desk-session-v1"


def _digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def save_session(document: Document, path: str | Path, *, verify_source: bool = True) -> None:
    if verify_source or not document.source_sha256:
        source_digest = _digest(document.source)
    else:
        source_digest = document.source_sha256
    if verify_source and document.source_sha256 and source_digest != document.source_sha256:
        raise ValueError("The source document changed while you were reviewing it. Open the changed document again before saving.")
    payload = {
        "schema": SCHEMA,
        "source": str(document.source),
        "source_sha256": source_digest,
        "max_mark": document.max_mark,
        "absent_codes": document.absent_codes,
        "allow_fractions": document.allow_fractions,
        "warnings": document.warnings,
        "pages": [{"number": p.number, "method": p.method, "notes": p.notes,
                   "mark_candidates": [asdict(c) for c in p.mark_candidates],
                   "layout": asdict(p.layout) if p.layout else None,
                   "words": [asdict(w) for w in p.words]} for p in document.pages],
        "records": [asdict(r) for r in document.records],
        "export_columns": [asdict(c) for c in document.export_columns] if document.export_columns is not None else None,
        "export_overrides": document.export_overrides,
    }
    path = Path(path)
    # Write beside the destination first so a failed save leaves an older session intact.
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def load_session(path: str | Path) -> Document:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if payload.get("schema") != SCHEMA:
            raise ValueError("This is not a Result Desk session file.")
        source = Path(payload["source"])
        if not source.is_file():
            raise ValueError(f"The original source has moved: {source}. Restore it before opening this session.")
        if _digest(source) != payload["source_sha256"]:
            raise ValueError("The original document has changed since this review was saved. Open it as a new document.")
        document = open_document(source, read_words=False)
        if len(document.pages) != len(payload["pages"]):
            raise ValueError("The original document's page count has changed.")
        for page, saved in zip(document.pages, payload["pages"]):
            page.method = saved["method"]
            page.layout = Layout(**saved["layout"]) if saved["layout"] else None
            page.words = [Word(**w) for w in saved["words"]]
            page.mark_candidates = [MarkCandidate(**c) for c in saved.get("mark_candidates", [])]
            page.notes = saved.get("notes", [])
        document.records = [Record(**row) for row in payload["records"]]
        document.max_mark = payload["max_mark"]
        document.absent_codes = payload.get("absent_codes", [])
        document.allow_fractions = payload.get("allow_fractions", True)
        document.warnings = payload.get("warnings", [])
        document.export_columns = ([ExportColumn(**c) for c in payload["export_columns"]]
                                   if payload.get("export_columns") is not None else None)
        document.export_overrides = payload.get("export_overrides", {})
        validate(document)
        return document
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("This session file is incomplete or damaged.") from exc


def _safe_cell(text: str) -> str:
    # Spreadsheet programs may evaluate untrusted OCR strings as formulas.
    return "'" + text if text.startswith(("=", "+", "-", "@", "\t", "\r")) else text


def export_csv(document: Document, path: str | Path) -> None:
    validate(document)
    if document.export_columns is not None:
        from .columns import table_rows
        with Path(path).open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow([_safe_cell(c.name) for c in document.export_columns])
            for row in table_rows(document, document.export_columns):
                writer.writerow([_safe_cell(row["values"][c.id]) for c in document.export_columns])
        return
    with Path(path).open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["Roll", "Marks", "Page", "Status", "Issues"])
        for row in document.records:
            writer.writerow([_safe_cell(row.roll), _safe_cell(row.mark), row.page, row.status,
                             "; ".join(row.issues)])


def export_xlsx(document: Document, path: str | Path) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    validate(document)
    if document.export_columns is not None:
        export_table_xlsx(document, path)
        return
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Results"
    sheet.append(["Roll", "Marks", "Page", "Status", "Issues"])
    for row in document.records:
        numeric = number(row.mark)
        sheet.append([_safe_cell(row.roll), float(numeric) if numeric is not None else _safe_cell(row.mark),
                      row.page, row.status, "; ".join(row.issues)])
        sheet.cell(sheet.max_row, 1).number_format = "@"
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    for cell in sheet[1]:
        cell.font = Font(color="FFFFFF", bold=True)
        cell.fill = PatternFill("solid", fgColor="225C4B")
    for col, width in {"A": 20, "B": 16, "C": 10, "D": 20, "E": 65}.items():
        sheet.column_dimensions[col].width = width
    audit = workbook.create_sheet("Source and review")
    audit.append(["Source", document.source.name])
    audit.append(["Selected column", "; ".join(dict.fromkeys(p.layout.label for p in document.pages if p.layout))])
    for warning in document.warnings:
        audit.append(["Extraction warning", _safe_cell(warning)])
    audit.append(["Roll", "Marks", "Original roll", "Original marks", "Page", "Method", "OCR score", "Reviewed"])
    for row in document.records:
        audit.append([_safe_cell(row.roll), _safe_cell(row.mark), _safe_cell(row.raw_roll), _safe_cell(row.raw_mark),
                      row.page, row.method, row.confidence if row.method == "Local OCR" else None,
                      "Yes" if row.reviewed else "No"])
    for column in "ABCDEFGH":
        audit.column_dimensions[column].width = 23
    workbook.save(path)


def export_table_xlsx(document: Document, path: str | Path) -> None:
    """The Results sheet exactly follows the user's named, ordered preview."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter
    from .columns import table_rows
    import math

    columns = document.export_columns
    rows = table_rows(document, columns)
    book = Workbook()
    sheet = book.active
    sheet.title = "Results"
    for index, column in enumerate(columns, start=1):
        cell = sheet.cell(1, index, column.name)
        cell.data_type = "s"  # Literal text, including headings starting with '='.
        cell.font = Font(color="FFFFFF", bold=True)
        cell.fill = PatternFill("solid", fgColor="225C4B")
        max_length = min(50, max([len(column.name), 10] + [len(r["values"][column.id]) for r in rows]))
        sheet.column_dimensions[get_column_letter(index)].width = max_length + 3
    for index, row in enumerate(rows, start=2):
        for col_index, column in enumerate(columns, start=1):
            value = row["values"][column.id]
            numeric = number(value) if column.kind == "number" else None
            cell = sheet.cell(index, col_index)
            cell.number_format = "@" if column.kind == "text" else "0.###############"
            if numeric is not None and math.isfinite(float(numeric)):
                cell.value = float(numeric)
            elif value:
                cell.value = value
                cell.data_type = "s"
                cell.number_format = "@"
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    audit = book.create_sheet("Source and review")

    def append_text(values):
        audit.append(values)
        for cell in audit[audit.max_row]:
            if isinstance(cell.value, str):
                cell.data_type = "s"

    append_text(["Source", document.source.name])
    append_text(["Export columns", " | ".join(c.name for c in columns)])
    for warning in document.warnings:
        append_text(["Extraction warning", warning])
    append_text(["Page", "Status", "Issues", "Method"] + [c.name for c in columns]
                + ["Original: " + c.name for c in columns])
    for row in rows:
        append_text([row["page"], row["status"], "; ".join(row["issues"]), row["method"]]
                    + [row["values"][c.id] for c in columns] + [row["original"][c.id] for c in columns])
    for index in range(1, 5 + 2 * len(columns)):
        audit.column_dimensions[get_column_letter(index)].width = 24
    book.save(path)
