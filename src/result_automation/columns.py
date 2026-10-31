"""Source-column discovery and row-aligned spreadsheet previews.

The review's row geometry stays the anchor: a blank cell in an added column
cannot move values onto another student. Source words and original readings
are retained when users edit the spreadsheet preview.
"""
from __future__ import annotations

import re
from dataclasses import asdict

from .extract import detect_grid, group_lines, normalize, number
from .models import Document, ExportColumn, Page, Record


def default_columns(document: Document) -> list[ExportColumn]:
    def regions(field):
        return {str(p.number): (getattr(p.layout, field)[0], p.layout.top,
                                getattr(p.layout, field)[1], p.layout.bottom)
                for p in document.pages if p.layout}
    return [ExportColumn("roll", "Roll", "text", "roll", regions("roll")),
            ExportColumn("marks", "Marks", "number", "mark", regions("mark"))]


def region_for(column: ExportColumn, page: Page):
    return column.regions.get(str(page.number))


def read_cell(page: Page, box, kind: str) -> str:
    words = [w for w in page.words if box[0] < w.cx < box[2] and box[1] <= w.cy < box[3]]
    if kind == "number":
        compact = normalize("".join(w.text for line in group_lines(words) for w in line))
        if number(compact) is not None or re.fullmatch(r"[-–—]+", compact):
            return compact
    return " ".join(w.text for line in group_lines(words) for w in line).strip()


def cell_value(document: Document, row: Record, column: ExportColumn, *, original=False) -> str:
    if column.source == "roll":
        return row.raw_roll if original else row.roll
    if column.source == "mark":
        return row.raw_mark if original else row.mark
    if row.method == "Manual":
        return ""
    page = document.pages[row.page - 1]
    region = region_for(column, page)
    if region is None:
        return ""
    top, bottom = max(row.box[1], region[1]), min(row.box[3], region[3])
    if top >= bottom:
        return ""
    return read_cell(page, (region[0], top, region[2], bottom), column.kind)


def discover_columns(document: Document) -> list[ExportColumn]:
    defaults = default_columns(document)
    if not document.pages:
        return defaults
    grids = {p.number: detect_grid(p) for p in document.pages}
    first = next((p for p in document.pages if len(grids[p.number][0]) >= 3 and p.layout), None)
    if first is None:
        return defaults
    xs, ys = grids[first.number]
    above = [y for y in ys if y < first.layout.top - .002]
    header_top = max(above) if above else max(0, first.layout.top - .07)
    result = []
    used_names: set[str] = set()
    for index, (left, right) in enumerate(zip(xs, xs[1:])):
        center = (left + right) / 2
        builtin = next((c for c in defaults if (r := c.regions.get(str(first.number))) and r[0] <= center <= r[2]), None)
        regions = {}
        for page in document.pages:
            px, _ = grids[page.number]
            bounds = (px[index], px[index + 1]) if len(px) == len(xs) else (left, right)
            regions[str(page.number)] = (bounds[0], page.layout.top if page.layout else first.layout.top,
                                         bounds[1], page.layout.bottom if page.layout else first.layout.bottom)
        if builtin:
            column = ExportColumn(builtin.id, builtin.name, builtin.kind, builtin.source, regions)
        else:
            words = [w for w in first.words if left < w.cx < right and header_top <= w.cy < first.layout.top]
            # PDF words preserve encoded reading order, including rotated headers.
            name = re.sub(r"\s+", " ", " ".join(w.text for w in words)).strip() or f"Column {index + 1}"
            name = name[:80]
            kind = "text"
            probe = ExportColumn(f"source-{index}", name, "text", "region", regions)
            samples = [cell_value(document, row, probe) for row in document.records[:20]]
            nonblank = [value for value in samples if value]
            if not re.search(r"roll|name|\bid\b|number", name, re.I) and nonblank:
                if sum(number(value.replace(" ", "")) is not None for value in nonblank) / len(nonblank) >= .8:
                    kind = "number"
            column = ExportColumn(probe.id, name, kind, "region", regions)
        base = column.name
        suffix = 2
        while column.name.casefold() in used_names:
            column.name = f"{base[:74]} ({suffix})"
            suffix += 1
        used_names.add(column.name.casefold())
        result.append(column)
    for default in defaults:
        if not any(c.id == default.id for c in result):
            result.append(default)
    # Custom source regions remain available when a saved selection is reopened.
    for saved in document.export_columns or []:
        if not any(c.id == saved.id for c in result):
            result.append(saved)
    return result


def table_rows(document: Document, columns: list[ExportColumn], overrides: dict | None = None) -> list[dict]:
    edits = document.export_overrides if overrides is None else overrides
    result = []
    for row in document.records:
        original = {c.id: cell_value(document, row, c, original=True) for c in columns}
        values = {c.id: edits.get(row.id, {}).get(c.id, cell_value(document, row, c)) for c in columns}
        result.append({"id": row.id, "page": row.page, "values": values, "original": original,
                       "method": row.method, "status": row.status, "issues": row.issues})
    return result


def table_preview(document: Document, columns: list[ExportColumn] | None = None, overrides: dict | None = None) -> dict:
    selected = columns if columns is not None else document.export_columns or default_columns(document)
    return {"columns": [asdict(c) for c in selected], "rows": table_rows(document, selected, overrides),
            "row_count": len(document.records)}


def apply_export_plan(document: Document, columns: list[ExportColumn], overrides: dict):
    ids = {c.id for c in columns}
    rows = {r.id: r for r in document.records}
    unknown_rows = set(overrides) - rows.keys()
    if unknown_rows:
        raise ValueError("The preview contains rows that no longer exist. Reload the preview.")
    if any(set(edits) - ids for edits in overrides.values()):
        raise ValueError("The preview contains edits for an unselected column.")
    document.export_columns = columns
    retained = {}
    by_id = {c.id: c for c in columns}
    for row_id, edits in overrides.items():
        row = rows[row_id]
        for col_id, value in edits.items():
            column = by_id[col_id]
            if column.source in {"roll", "mark"}:
                value = normalize(value)
                field = "roll" if column.source == "roll" else "mark"
                if getattr(row, field) != value:
                    setattr(row, field, value)
                    row.reviewed = True
            else:
                retained.setdefault(row_id, {})[col_id] = value.strip()
    document.export_overrides = retained
