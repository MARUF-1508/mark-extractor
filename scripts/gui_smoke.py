"""Exercise real Tk widgets. On Linux: xvfb-run -a python scripts/gui_smoke.py."""
from __future__ import annotations

import os
import time
import tkinter as tk
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import ImageGrab
from openpyxl import load_workbook

from result_automation.document import open_document
from result_automation.extract import detect_grid, extract_document
from result_automation.gui import App

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "tmp" / "gui-smoke"


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


def wait(root, condition, seconds=20):
    deadline = time.monotonic() + seconds
    while not condition():
        root.update()
        if time.monotonic() > deadline:
            raise AssertionError("GUI operation timed out")
        time.sleep(0.02)
    root.update()


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    root = tk.Tk()
    app = App(root)
    root.update()
    try:
        app.open_path(ROOT / "examples" / "CSE 251_CT_marks.pdf")
        wait(root, lambda: app.document is not None and not app.busy)
        assert len(app.tree.get_children()) == 54
        assert app.column_label.get() == "Total (40)"

        app.search.set("205")
        root.update()
        assert len(app.tree.get_children()) == 2
        app.search.set("")
        app.tree.selection_set("p1-r1")
        root.update()
        app.edit_row()
        root.update()
        dialog = next(w for w in root.winfo_children() if isinstance(w, tk.Toplevel))
        entries = [w for w in descendants(dialog) if w.winfo_class() == "TEntry"]
        for entry, value in zip(entries, ("00328", "38.5")):
            entry.delete(0, "end")
            entry.insert(0, value)
        next(w for w in descendants(dialog) if w.winfo_class() == "TButton").invoke()
        root.update()
        row = app.document.records[0]
        assert (row.roll, row.mark, row.raw_mark, row.reviewed) == ("00328", "38.5", "39", True)

        app.maximum.set("35")
        app.apply_maximum()
        app.only_issues.set(True)
        app.refresh_table()
        assert 0 < len(app.tree.get_children()) < 54
        app.maximum.set("")
        app.apply_maximum()
        app.only_issues.set(False)
        app.refresh_table()
        session = OUTPUT / "test.review.json"
        with patch("result_automation.gui.filedialog.asksaveasfilename", return_value=str(session)):
            assert app.save()
        assert not app.dirty
        with patch("result_automation.gui.filedialog.askopenfilename", return_value=str(session)):
            app.choose_session()
        wait(root, lambda: not app.busy)
        assert app.document.records[0].mark == "38.5"
        xlsx = OUTPUT / "gui-export.xlsx"
        # Exercise the visible export controls and verify a real Excel workbook,
        # including corrected values, roll text, and rows hidden by the search.
        app.search.set("205")
        root.update()
        assert len(app.tree.get_children()) == 2
        with patch("result_automation.gui.filedialog.asksaveasfilename", return_value=str(xlsx)) as dialog:
            next(button for button in app.buttons if button.cget("text") == "Export Excel (.xlsx)").invoke()
        assert dialog.call_args.kwargs["defaultextension"] == ".xlsx"
        assert dialog.call_args.kwargs["filetypes"] == [("Excel workbook", "*.xlsx")]
        workbook = load_workbook(xlsx)
        assert workbook["Results"].max_row == 55
        assert workbook["Results"]["A2"].value == "00328"
        assert workbook["Results"]["B2"].value == 38.5
        assert "Source and review" in workbook.sheetnames
        workbook.close()
        csv = OUTPUT / "gui-export.csv"
        with patch("result_automation.gui.filedialog.asksaveasfilename", return_value=str(csv)) as dialog:
            next(button for button in app.buttons if button.cget("text") == "Export CSV").invoke()
        assert dialog.call_args.kwargs["defaultextension"] == ".csv"
        assert len(csv.read_text(encoding="utf-8-sig").splitlines()) == 55
        app.search.set("")

        # Drag a new marks region around the penultimate (Avg) column.
        app.page_index = 0
        app.draw_page()
        root.update()
        page = app.current_page()
        xs, _ = detect_grid(page)
        x, y, width, height = app.display_box
        app.start_selection("mark")
        app.drag_begin(SimpleNamespace(x=x + (xs[-3] + .001) * width,
                                       y=y + (page.layout.top + .001) * height))
        app.drag_end(SimpleNamespace(x=x + (xs[-2] - .001) * width,
                                     y=y + (page.layout.bottom - .001) * height))
        assert app.pending_pages == {1}
        with patch("result_automation.gui.messagebox.showinfo") as prompt:
            assert not app._check_pending()
            prompt.assert_called_once()
        with patch("result_automation.gui.messagebox.askokcancel", return_value=True):
            app.reextract_page()
            assert app.document.records[0].mark == "29"
            app.copy_columns()
            assert len(app.document.records) == 54
            app.reset_auto()
        assert app.document.records[0].mark == "39"
        assert not app.pending_pages

        app.show_document(extract_document(open_document(ROOT / "examples" / "OOAD_tutorial.pdf")))
        app.tree.selection_set("p2-r25")
        root.update()
        assert app.page_index == 1 and app.selected_record().roll == "2052"
        assert app.column_label.get() == "Project(20)"
        # Force the current X server, avoiding a host-display screenshot on Linux.
        if os.name != "nt":
            ImageGrab.grab(xdisplay=os.environ.get("DISPLAY")).save(OUTPUT / "review-screen.png")
        else:
            ImageGrab.grab().save(OUTPUT / "review-screen.png")
        print("GUI passed: async import, search, edit, range/filter, save/restore, Excel/CSV buttons, "
              "column drag, page/all-page re-extraction, automatic reset, and continuation-page selection.")
    finally:
        root.destroy()


if __name__ == "__main__":
    main()
