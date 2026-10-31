from __future__ import annotations

import math
import queue
import threading
import tkinter as tk
import uuid
from copy import deepcopy
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

from .document import open_document
from .extract import extract_document, extract_page, normalize, validate
from .models import Cancelled, Document, Layout, Record
from .storage import export_csv, export_xlsx, load_session, save_session

BG = "#f5f7f5"
INK = "#203c32"
MUTED = "#697b73"
GREEN = "#23634e"
LINE = "#dce4de"
ORANGE = "#a3681c"


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.document: Document | None = None
        self.session_path: Path | None = None
        self.page_index = 0
        self.dirty = False
        self.busy = False
        self.cancel_event = threading.Event()
        self.events = queue.Queue()
        self.buttons: list[ttk.Button] = []
        self.selection_mode: str | None = None
        self.drag_start = None
        self.photo = None
        self.crop_photo = None
        self.display_box = (0, 0, 1, 1)
        self.fit_width = False
        self.pending_pages: set[int] = set()
        self.search = tk.StringVar()
        self.only_issues = tk.BooleanVar()
        self.force_ocr = tk.BooleanVar()
        self.maximum = tk.StringVar()
        self.status = tk.StringVar(value="Choose a document to begin. Files stay on this computer.")
        self.row_count = tk.StringVar(value="—")
        self.issue_count = tk.StringVar(value="—")
        self.column_label = tk.StringVar(value="Auto-detect")
        self._style()
        self._build()
        self.search.trace_add("write", lambda *_: self.refresh_table())
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.bind("<Control-o>", lambda _: self.choose_document())
        root.bind("<Control-s>", lambda _: self.save())
        root.bind("<Control-e>", lambda _: self.export())
        root.after(100, self._poll)

    def _style(self):
        self.root.title("Result Desk · Offline marks extraction")
        self.root.geometry("1320x860")
        self.root.minsize(1080, 740)
        self.root.configure(bg=BG)
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(".", font=("Segoe UI", 10), background=BG, foreground=INK)
        style.configure("TFrame", background=BG)
        style.configure("Card.TFrame", background="white")
        style.configure("TLabel", background=BG, foreground=INK)
        style.configure("Card.TLabel", background="white")
        style.configure("Muted.TLabel", foreground=MUTED)
        style.configure("Title.TLabel", font=("Segoe UI", 22, "bold"))
        style.configure("Section.TLabel", font=("Segoe UI", 12, "bold"), background="white")
        style.configure("Number.TLabel", font=("Segoe UI", 24, "bold"), background="white")
        style.configure("TButton", padding=(13, 9), background="white", bordercolor=LINE,
                        lightcolor="white", darkcolor="white", focusthickness=1, focuscolor=GREEN)
        style.map("TButton", background=[("active", "#e8efea"), ("disabled", BG)],
                  foreground=[("disabled", "#9ba69f")])
        style.configure("Primary.TButton", background=GREEN, foreground="white", bordercolor=GREEN,
                        lightcolor=GREEN, darkcolor=GREEN)
        style.map("Primary.TButton", background=[("active", "#194f3c"), ("disabled", "#9bb5a8")],
                  foreground=[("disabled", "white")])
        style.configure("Small.TButton", padding=(8, 5))
        style.configure("TEntry", fieldbackground="white", bordercolor=LINE, padding=7)
        style.configure("Treeview", background="white", fieldbackground="white", rowheight=34,
                        borderwidth=0, font=("Segoe UI", 10))
        style.configure("Treeview.Heading", background="#eef3ef", foreground=MUTED,
                        font=("Segoe UI", 9, "bold"), padding=(8, 10), borderwidth=0)
        style.map("Treeview", background=[("selected", "#d9eadf")], foreground=[("selected", INK)])
        style.configure("TPanedwindow", background=BG)

    def button(self, parent, text, command, *, primary=False, small=False, **pack):
        button = ttk.Button(parent, text=text, command=command,
                            style="Primary.TButton" if primary else "Small.TButton" if small else "TButton")
        button.pack(**pack)
        self.buttons.append(button)
        return button

    def _build(self):
        header = ttk.Frame(self.root, padding=(24, 20, 24, 14))
        header.pack(fill="x")
        branding = ttk.Frame(header)
        branding.pack(side="left")
        ttk.Label(branding, text="Result Desk", style="Title.TLabel").pack(anchor="w")
        ttk.Label(branding, text="FROM MARKSHEET TO RESULTS", style="Muted.TLabel",
                  font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(2, 0))
        actions = ttk.Frame(header)
        actions.pack(side="right")
        self.button(actions, "Open document", self.choose_document, side="left", padx=4)
        self.button(actions, "Open session", self.choose_session, side="left", padx=4)
        self.button(actions, "Save session", self.save, side="left", padx=4)
        self.button(actions, "Export CSV", lambda: self.export("csv"), side="left", padx=4)
        self.button(actions, "Export Excel (.xlsx)", self.export, primary=True, side="left", padx=(8, 0))

        strip = ttk.Frame(self.root, padding=(24, 0, 24, 14))
        strip.pack(fill="x")
        self.file_label = ttk.Label(strip, text="No document open", font=("Segoe UI", 11, "bold"))
        self.file_label.pack(side="left")
        ttk.Label(strip, text="●  ON THIS DEVICE", foreground=GREEN,
                  font=("Segoe UI", 9, "bold")).pack(side="right")

        stats = ttk.Frame(self.root, padding=(24, 0, 24, 16))
        stats.pack(fill="x")
        for index, (label, variable) in enumerate((("STUDENT ROWS", self.row_count),
                                                 ("NEED REVIEW", self.issue_count),
                                                 ("SELECTED MARKS COLUMN", self.column_label))):
            card = ttk.Frame(stats, style="Card.TFrame", padding=(18, 12))
            card.grid(row=0, column=index, sticky="nsew", padx=(0, 10 if index < 2 else 0))
            stats.columnconfigure(index, weight=2 if index == 2 else 1)
            ttk.Label(card, text=label, background="white", foreground=MUTED,
                      font=("Segoe UI", 8, "bold")).pack(anchor="w")
            ttk.Label(card, textvariable=variable, style="Number.TLabel" if index < 2 else "Section.TLabel").pack(
                anchor="w", pady=(4, 0))

        pane = ttk.Panedwindow(self.root, orient="horizontal")
        pane.pack(fill="both", expand=True, padx=24)
        left = ttk.Frame(pane, style="Card.TFrame", padding=14)
        right = ttk.Frame(pane, style="Card.TFrame", padding=16)
        pane.add(left, weight=3)
        pane.add(right, weight=2)
        self.root.after(200, lambda: pane.sashpos(0, 730))

        preview_header = ttk.Frame(left, style="Card.TFrame")
        preview_header.pack(fill="x")
        ttk.Label(preview_header, text="Source document", style="Section.TLabel").pack(side="left")
        self.button(preview_header, "Next ›", lambda: self.turn_page(1), small=True, side="right")
        self.page_label = ttk.Label(preview_header, text="Page — / —", style="Card.TLabel")
        self.page_label.pack(side="right", padx=10)
        self.button(preview_header, "‹ Prev", lambda: self.turn_page(-1), small=True, side="right")

        tools = ttk.Frame(left, style="Card.TFrame")
        tools.pack(fill="x", pady=(12, 8))
        self.button(tools, "Select roll column", lambda: self.start_selection("roll"), small=True,
                    side="left", padx=(0, 5))
        self.button(tools, "Select marks column", lambda: self.start_selection("mark"), small=True,
                    side="left", padx=(0, 5))
        self.button(tools, "Fit / zoom", self.toggle_zoom, small=True, side="right")
        self.selection_hint = ttk.Label(left, text="Roll column: green   ·   Marks column: amber   ·   Click a row to inspect",
                                        background="white", foreground=MUTED, font=("Segoe UI", 9))
        self.selection_hint.pack(anchor="w", pady=(0, 8))
        canvas_frame = ttk.Frame(left, style="Card.TFrame")
        canvas_frame.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(canvas_frame, background="#e9eeea", highlightthickness=0)
        yscroll = ttk.Scrollbar(canvas_frame, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=yscroll.set)
        yscroll.pack(side="right", fill="y")
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda _: self.draw_page())
        self.canvas.bind("<ButtonPress-1>", self.drag_begin)
        self.canvas.bind("<B1-Motion>", self.drag_move)
        self.canvas.bind("<ButtonRelease-1>", self.drag_end)
        self.canvas.bind("<MouseWheel>", lambda e: self.canvas.yview_scroll(-int(e.delta / 120), "units"))
        self.canvas.bind("<Button-4>", lambda _: self.canvas.yview_scroll(-2, "units"))
        self.canvas.bind("<Button-5>", lambda _: self.canvas.yview_scroll(2, "units"))
        self.canvas.bind("<Escape>", lambda _: self.cancel_selection())

        settings = ttk.Frame(left, style="Card.TFrame")
        settings.pack(fill="x", pady=(10, 0))
        self.button(settings, "Re-extract page", self.reextract_page, small=True, side="left", padx=(0, 6))
        self.button(settings, "Use columns on all pages", self.copy_columns, small=True, side="left")
        self.button(settings, "Reset auto", self.reset_auto, small=True, side="right")

        ttk.Label(right, text="Extracted results", style="Section.TLabel").pack(anchor="w")
        ttk.Label(right, text="Check the source, correct a value, then export.", background="white",
                  foreground=MUTED).pack(anchor="w", pady=(4, 12))
        filters = ttk.Frame(right, style="Card.TFrame")
        filters.pack(fill="x")
        ttk.Entry(filters, textvariable=self.search, width=16).pack(side="left", fill="x", expand=True)
        ttk.Checkbutton(filters, text="Needs review", variable=self.only_issues,
                        command=self.refresh_table).pack(side="right", padx=(10, 0))
        ttk.Label(right, text="Search by roll number", background="white", foreground=MUTED,
                  font=("Segoe UI", 8)).pack(anchor="w", pady=(3, 8))
        table_frame = ttk.Frame(right, style="Card.TFrame")
        table_frame.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(table_frame, columns=("roll", "mark", "page", "status"),
                                 show="headings", selectmode="browse", height=7)
        for name, title, width in (("roll", "ROLL", 80), ("mark", "MARKS", 75),
                                   ("page", "PAGE", 45), ("status", "STATUS", 110)):
            self.tree.heading(name, text=title)
            self.tree.column(name, width=width, minwidth=40, stretch=name in ("roll", "status"), anchor="w")
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.tree.pack(fill="both", expand=True)
        self.tree.tag_configure("issue", foreground=ORANGE)
        self.tree.tag_configure("even", background="#f7faf7")
        self.tree.bind("<<TreeviewSelect>>", self.select_row)
        self.tree.bind("<Double-1>", lambda _: self.edit_row())
        self.tree.bind("<F2>", lambda _: self.edit_row())

        row_actions = ttk.Frame(right, style="Card.TFrame")
        row_actions.pack(fill="x", pady=(10, 8))
        self.button(row_actions, "Edit row", self.edit_row, small=True, side="left", padx=(0, 5))
        self.button(row_actions, "Verify", self.verify_row, small=True, side="left", padx=(0, 5))
        self.button(row_actions, "+ Row", self.add_row, small=True, side="left")
        self.button(row_actions, "Delete", self.delete_row, small=True, side="right")
        self.detail = tk.StringVar(value="Select a student to see the original row.")
        ttk.Label(right, textvariable=self.detail, background="white", foreground=MUTED,
                  wraplength=390, font=("Segoe UI", 9)).pack(anchor="w", fill="x", pady=(0, 5))
        self.crop = tk.Canvas(right, background="#f3f5f2", height=65, highlightthickness=0)
        self.crop.pack(fill="x")
        validation = ttk.Frame(right, style="Card.TFrame")
        validation.pack(fill="x", pady=(12, 0))
        ttk.Label(validation, text="Maximum mark", style="Card.TLabel").pack(side="left")
        ttk.Entry(validation, textvariable=self.maximum, width=7).pack(side="left", padx=6)
        self.button(validation, "Apply", self.apply_maximum, small=True, side="left")
        ttk.Label(right, text="Leave blank to use the selected column’s header.", background="white",
                  foreground=MUTED, font=("Segoe UI", 8)).pack(anchor="w", pady=(3, 0))

        footer = ttk.Frame(self.root, padding=(24, 12))
        footer.pack(fill="x")
        ttk.Label(footer, textvariable=self.status, style="Muted.TLabel", wraplength=780).pack(side="left")
        self.cancel_button = ttk.Button(footer, text="Cancel", command=self.cancel_event.set, style="Small.TButton")
        self.cancel_button.pack(side="right", padx=(10, 0))
        self.cancel_button.state(["disabled"])
        ttk.Checkbutton(footer, text="Force image OCR on next open", variable=self.force_ocr).pack(side="right")
        self.draw_page()

    def _set_busy(self, busy: bool):
        self.busy = busy
        for button in self.buttons:
            button.state(["disabled"] if busy else ["!disabled"])
        self.cancel_button.state(["!disabled"] if busy else ["disabled"])

    def _job(self, function, done):
        if self.busy:
            return
        self.cancel_event.clear()
        self._set_busy(True)

        def run():
            try:
                self.events.put(("done", function(), done))
            except Cancelled:
                self.events.put(("cancelled", None, None))
            except Exception as exc:
                self.events.put(("error", str(exc), None))

        threading.Thread(target=run, daemon=True).start()

    def _poll(self):
        try:
            while True:
                kind, value, callback = self.events.get_nowait()
                if kind == "progress":
                    self.status.set(value)
                else:
                    self._set_busy(False)
                    if kind == "done":
                        callback(value)
                    elif kind == "cancelled":
                        self.status.set("Import cancelled. The previous document is unchanged.")
                    else:
                        self.status.set("The operation could not be completed.")
                        messagebox.showerror("Result Desk", value, parent=self.root)
        except queue.Empty:
            pass
        self.root.after(100, self._poll)

    def _confirm_replace(self) -> bool:
        if self.busy:
            return False
        if not self.dirty:
            return True
        answer = messagebox.askyesnocancel("Unsaved review", "Save this review session before continuing?", parent=self.root)
        if answer is None:
            return False
        return self.save() if answer else True

    def choose_document(self):
        if not self._confirm_replace():
            return
        path = filedialog.askopenfilename(title="Open a marksheet", filetypes=[
            ("Documents and images", "*.pdf *.png *.jpg *.jpeg *.tif *.tiff *.bmp *.webp"),
            ("PDF", "*.pdf"), ("All files", "*.*")])
        if path:
            self.open_path(path)

    def open_path(self, path):
        force = self.force_ocr.get()
        self.status.set("Opening document…")

        def work():
            document = open_document(path, force_ocr=force, cancel=self.cancel_event,
                                     progress=lambda text: self.events.put(("progress", text, None)))
            return extract_document(document)

        self._job(work, lambda doc: self.show_document(doc, None))

    def choose_session(self):
        if not self._confirm_replace():
            return
        path = filedialog.askopenfilename(title="Open a review session", filetypes=[("Result Desk session", "*.json")])
        if path:
            self._job(lambda: load_session(path), lambda doc: self.show_document(doc, Path(path)))

    def show_document(self, document, session_path=None):
        self.document, self.session_path = document, session_path
        self.page_index, self.dirty = 0, False
        self.pending_pages.clear()
        self.maximum.set("" if document.max_mark is None else f"{document.max_mark:g}")
        self.search.set("")
        self.only_issues.set(False)
        self.file_label.configure(text=document.source.name)
        self.refresh_table()
        self.draw_page()
        methods = " + ".join(sorted({p.method for p in document.pages}))
        self.status.set(f"{len(document.records)} rows · {len(document.pages)} pages · {methods}. "
                        "Review the selected column before exporting.")
        if document.warnings:
            messagebox.showwarning("Check extraction", "\n".join(document.warnings), parent=self.root)

    def current_page(self):
        return self.document.pages[self.page_index] if self.document and self.document.pages else None

    def selected_record(self):
        if not self.document or not self.tree.selection():
            return None
        selected = self.tree.selection()[0]
        return next((r for r in self.document.records if r.id == selected), None)

    def refresh_table(self):
        if not hasattr(self, "tree"):
            return
        selected = self.tree.selection()
        self.tree.delete(*self.tree.get_children())
        if not self.document:
            return
        validate(self.document)
        query = self.search.get().strip()
        visible = 0
        for row in self.document.records:
            if query and query not in row.roll:
                continue
            if self.only_issues.get() and not row.issues:
                continue
            tags = (["even"] if visible % 2 == 0 else []) + (["issue"] if row.issues else [])
            self.tree.insert("", "end", iid=row.id,
                             values=(row.roll or "—", row.mark or "—", row.page, row.status), tags=tags)
            visible += 1
        if selected and self.tree.exists(selected[0]):
            self.tree.selection_set(selected[0])
            self.tree.see(selected[0])
        self.row_count.set(str(len(self.document.records)))
        self.issue_count.set(str(sum(bool(r.issues) for r in self.document.records)))
        self.update_title()
        if not self.tree.selection():
            self.detail.set(f"{visible} rows shown. Select a student to inspect the source.")
            self.crop.delete("all")
        self.draw_page()

    def update_title(self):
        name = self.document.source.name if self.document else "Offline marks extraction"
        self.root.title(f"{'• ' if self.dirty else ''}Result Desk · {name}")

    def changed(self):
        self.dirty = True
        self.refresh_table()

    def turn_page(self, delta):
        if self.busy or not self.document:
            return
        self.cancel_selection()
        self.page_index = max(0, min(len(self.document.pages) - 1, self.page_index + delta))
        self.canvas.yview_moveto(0)
        self.draw_page()

    def toggle_zoom(self):
        self.fit_width = not self.fit_width
        self.draw_page()

    def draw_page(self):
        if not hasattr(self, "canvas"):
            return
        canvas = self.canvas
        canvas.delete("all")
        width, height = max(canvas.winfo_width(), 100), max(canvas.winfo_height(), 100)
        page = self.current_page()
        if not page:
            canvas.create_text(width / 2, height / 2 - 25, text="Your marksheet, made useful.",
                               font=("Segoe UI", 18, "bold"), fill=INK)
            canvas.create_text(width / 2, height / 2 + 15,
                               text="Open a PDF or image to extract rolls and marks.\nAll processing happens on this computer.",
                               font=("Segoe UI", 11), fill=MUTED, justify="center")
            return
        self.page_label.configure(text=f"Page {page.number} / {len(self.document.pages)}")
        self.column_label.set(page.layout.label if page.layout else "Select columns")
        scale = (width - 36) / page.image.width
        if not self.fit_width:
            scale = min(scale, (height - 32) / page.image.height)
        w, h = max(1, int(page.image.width * scale)), max(1, int(page.image.height * scale))
        x, y = (width - w) // 2, 16
        self.display_box = (x, y, w, h)
        self.photo = ImageTk.PhotoImage(page.image.resize((w, h), Image.Resampling.LANCZOS))
        canvas.create_image(x, y, image=self.photo, anchor="nw")
        canvas.configure(scrollregion=(0, 0, width, h + 32))
        if page.layout:
            for bounds, color in ((page.layout.roll, GREEN), (page.layout.mark, "#d39935")):
                canvas.create_rectangle(x + bounds[0] * w, y + page.layout.top * h,
                                        x + bounds[1] * w, y + page.layout.bottom * h,
                                        outline=color, width=2)
        record = self.selected_record()
        if record and record.page == page.number:
            a, b, c, d = record.box
            canvas.create_rectangle(x + a * w, y + b * h, x + c * w, y + d * h,
                                    outline="#3576ba", width=2)

    def select_row(self, _event=None):
        record = self.selected_record()
        if not record or self.busy:
            return
        self.page_index = record.page - 1
        self.draw_page()
        note = "; ".join(record.issues) or "No validation issues"
        self.detail.set(f"Roll {record.roll or '—'} · {record.method} · {note}\n"
                        f"Original: {record.raw_roll or '(blank)'} → {record.raw_mark or '(blank)'}")
        page = self.current_page()
        a, b, c, d = record.box
        image = page.image.crop((max(0, int(a * page.image.width) - 4), max(0, int(b * page.image.height) - 4),
                                 min(page.image.width, int(c * page.image.width) + 4),
                                 min(page.image.height, int(d * page.image.height) + 4)))
        image.thumbnail((max(300, self.crop.winfo_width()) - 12, 62), Image.Resampling.LANCZOS)
        self.crop_photo = ImageTk.PhotoImage(image)
        self.crop.delete("all")
        self.crop.create_image(6, 32, image=self.crop_photo, anchor="w")

    def start_selection(self, mode):
        if self.busy or not self.document:
            return
        self.selection_mode = mode
        self.canvas.configure(cursor="crosshair")
        self.canvas.focus_set()
        name = "roll" if mode == "roll" else "marks"
        self.selection_hint.configure(text=f"Drag around the {name} cells, from first student to last. Exclude the header. Esc cancels.")

    def cancel_selection(self):
        self.selection_mode, self.drag_start = None, None
        self.canvas.configure(cursor="")
        self.canvas.delete("selection")
        self.selection_hint.configure(text="Roll column: green   ·   Marks column: amber   ·   Click a row to inspect")

    def drag_begin(self, event):
        if self.busy or not self.selection_mode:
            return
        self.drag_start = (self.canvas.canvasx(event.x), self.canvas.canvasy(event.y))

    def drag_move(self, event):
        if not self.drag_start:
            return
        self.canvas.delete("selection")
        self.canvas.create_rectangle(*self.drag_start, self.canvas.canvasx(event.x), self.canvas.canvasy(event.y),
                                     outline=GREEN, width=3, dash=(5, 3), tags="selection")

    def drag_end(self, event):
        if not self.drag_start or not self.selection_mode:
            return
        x, y, width, height = self.display_box
        end = (self.canvas.canvasx(event.x), self.canvas.canvasy(event.y))
        xa, xb = sorted((max(0, min(1, (point[0] - x) / width)) for point in (self.drag_start, end)))
        ya, yb = sorted((max(0, min(1, (point[1] - y) / height)) for point in (self.drag_start, end)))
        if xb - xa > 0.008 and yb - ya > 0.01:
            page = self.current_page()
            if page.layout is None:
                page.layout = Layout((0.05, 0.2), (0.8, 0.98))
            setattr(page.layout, self.selection_mode, (xa, xb))
            page.layout.top, page.layout.bottom = ya, yb
            if self.selection_mode == "mark":
                page.layout.label, page.layout.max_mark = "Custom marks column", None
            page.layout.automatic = False
            self.pending_pages.add(page.number)
            self.dirty = True
            self.status.set("Column selection changed. Select the other column if needed, then click Re-extract page.")
        self.cancel_selection()
        self.draw_page()
        self.update_title()

    def _confirm_reextract(self):
        return messagebox.askokcancel("Re-extract", "Re-extraction replaces edits and verification for the affected pages. Continue?",
                                      parent=self.root)

    def reextract_page(self):
        if self.busy or not self.document or not self._confirm_reextract():
            return
        page = self.current_page()
        if page.layout is None:
            messagebox.showinfo("Select columns", "Select the roll and marks columns first.", parent=self.root)
            return
        self.document.records = [r for r in self.document.records if r.page != page.number] + extract_page(page)
        self.document.records.sort(key=lambda r: (r.page, r.box[1]))
        self.pending_pages.discard(page.number)
        self.changed()
        self.status.set("Page re-extracted. Check the results before exporting.")

    def copy_columns(self):
        page = self.current_page()
        if self.busy or not page or not page.layout or not self._confirm_reextract():
            return
        for other in self.document.pages:
            if other is page:
                continue
            if other.layout is None:
                other.layout = deepcopy(page.layout)
                other.layout.top = 0
            other.layout.roll, other.layout.mark = page.layout.roll, page.layout.mark
            other.layout.label, other.layout.max_mark = page.layout.label, page.layout.max_mark
            other.layout.automatic = False
        extract_document(self.document, autodetect=False)
        self.pending_pages.clear()
        self.changed()
        self.status.set("Column positions applied to all pages; each page keeps its own row area.")

    def reset_auto(self):
        if self.busy or not self.document or not self._confirm_reextract():
            return
        extract_document(self.document)
        self.pending_pages.clear()
        self.changed()
        self.draw_page()
        self.status.set("Automatic column detection restored for all pages.")

    def edit_row(self, row=None):
        if self.busy or not self.document:
            return
        row = row or self.selected_record()
        if row is None:
            return
        dialog = tk.Toplevel(self.root)
        dialog.title(f"Edit roll {row.roll or '—'}")
        dialog.configure(bg=BG)
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        body = ttk.Frame(dialog, padding=24)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Check against the original row", font=("Segoe UI", 13, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))
        roll, mark = tk.StringVar(value=row.roll), tk.StringVar(value=row.mark)
        first = None
        for index, (label, variable) in enumerate((("Roll number", roll), ("Marks", mark)), start=1):
            ttk.Label(body, text=label).grid(row=index, column=0, sticky="w", padx=(0, 16), pady=6)
            entry = ttk.Entry(body, textvariable=variable, width=24)
            entry.grid(row=index, column=1, pady=6)
            first = first or entry

        def commit():
            row.roll, row.mark = normalize(roll.get()), normalize(mark.get())
            row.reviewed = True
            if row not in self.document.records:
                self.document.records.append(row)
            self.changed()
            if self.tree.exists(row.id):
                self.tree.selection_set(row.id)
            dialog.destroy()
            self.select_row()

        ttk.Button(body, text="Save and verify", command=commit, style="Primary.TButton").grid(
            row=3, column=1, sticky="e", pady=(16, 0))
        dialog.bind("<Return>", lambda _: commit())
        dialog.bind("<Escape>", lambda _: dialog.destroy())
        first.focus_set()
        first.selection_range(0, "end")

    def verify_row(self):
        row = self.selected_record()
        if not row or self.busy:
            return
        row.reviewed = True
        self.changed()
        self.select_row()
        self.status.set("Row verified. Missing values, duplicate rolls, and range errors still need correction.")

    def add_row(self):
        page = self.current_page()
        if not page or self.busy:
            return
        record = Record(f"manual-{uuid.uuid4().hex}", page.number, "", "", "", "",
                        (0, 0, 1, 1), "Manual", 1.0, page.layout.max_mark if page.layout else None)
        self.edit_row(record)

    def delete_row(self):
        row = self.selected_record()
        if row and not self.busy and messagebox.askokcancel("Delete row", f"Remove roll {row.roll or '(blank)'} from these results?",
                                                           parent=self.root):
            self.document.records.remove(row)
            self.changed()

    def apply_maximum(self):
        if self.busy or not self.document:
            return
        try:
            maximum = float(self.maximum.get()) if self.maximum.get().strip() else None
            if maximum is not None and (maximum <= 0 or not math.isfinite(maximum)):
                raise ValueError
        except ValueError:
            messagebox.showerror("Maximum mark", "Enter a finite positive number, or leave the field blank.", parent=self.root)
            return
        self.document.max_mark = maximum
        self.changed()
        self.select_row()
        self.status.set("Mark range checked across all pages.")

    def save(self):
        if self.busy or not self.document:
            return False
        if not self._check_pending():
            return False
        path = self.session_path or filedialog.asksaveasfilename(title="Save review session", defaultextension=".json",
                                                                 initialfile=self.document.source.stem + ".review.json",
                                                                 filetypes=[("Result Desk session", "*.json")])
        if not path:
            return False
        try:
            save_session(self.document, path)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Cannot save session", str(exc), parent=self.root)
            return False
        self.session_path = Path(path)
        self.dirty = False
        self.update_title()
        self.status.set(f"Review saved to {Path(path).name}. Keep the original document in its current location.")
        return True

    def export(self, file_format="xlsx"):
        if self.busy or not self.document or not self.document.records:
            return
        if not self._check_pending():
            return
        validate(self.document)
        flagged = sum(bool(r.issues) for r in self.document.records)
        if flagged and not messagebox.askokcancel("Rows need review",
                f"{flagged} rows still need review. Export them with their status and issues included?", parent=self.root):
            return
        label, suffix, exporter = {
            "xlsx": ("Excel workbook", ".xlsx", export_xlsx),
            "csv": ("CSV", ".csv", export_csv),
        }[file_format]
        path = filedialog.asksaveasfilename(title=f"Export {label}", defaultextension=suffix,
                                            initialfile=self.document.source.stem + ".results" + suffix,
                                            filetypes=[(label, "*" + suffix)])
        if not path:
            return
        try:
            if Path(path).suffix.lower() != suffix:
                raise ValueError(f"Choose a filename ending in {suffix} for {label} export.")
            exporter(self.document, path)
            self.status.set(f"Exported all {len(self.document.records)} rows to {Path(path).name} ({label}).")
        except (OSError, ValueError) as exc:
            messagebox.showerror("Cannot export", str(exc), parent=self.root)

    def _check_pending(self):
        if self.pending_pages:
            pages = ", ".join(str(p) for p in sorted(self.pending_pages))
            messagebox.showinfo("Apply column selection", f"Re-extract pages {pages} before saving or exporting, "
                                "or use the columns on all pages.", parent=self.root)
            return False
        return True

    def close(self):
        if self.busy:
            if messagebox.askokcancel("Import in progress", "Cancel the import and close Result Desk?", parent=self.root):
                self.cancel_event.set()
                self.root.destroy()
            return
        if self._confirm_replace():
            self.root.destroy()


def main():
    root = tk.Tk()
    app = App(root)
    import sys
    if len(sys.argv) > 1:
        root.after(300, lambda: app.open_path(sys.argv[1]))
    root.mainloop()


if __name__ == "__main__":
    main()
