"""Durable local jobs/reviews. One worker serializes PDFium and OCR operations."""
from __future__ import annotations

import json
import logging
import re
import shutil
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

from .document import SUPPORTED, open_document, reocr_pages
from .extract import extract_document, extract_page, validate
from .models import Cancelled, Document, ExportColumn, Layout, MarkCandidate, Page, Record, Word
from .storage import save_session

LOG = logging.getLogger(__name__)
MAX_UPLOAD_BYTES = 50 * 1024 * 1024
MAX_PAGES = 50
ACTIVE = {"queued", "processing", "cancelling"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path: Path, payload: dict):
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    temp.replace(path)


class StoreError(Exception):
    def __init__(self, status: int, message: str):
        self.status, self.message = status, message
        super().__init__(message)


class JobStore:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="result-extraction")
        self.cancellations: dict[str, threading.Event] = {}
        self.passwords: dict[str, str | None] = {}
        for meta_path in self.root.glob("*/meta.json"):
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                if meta.get("status") in ACTIVE or meta.get("status") == "uploading":
                    meta.update(status="error", error="The server stopped before extraction finished. Please upload this file again.",
                                progress="Extraction interrupted", updated_at=now())
                    atomic_json(meta_path, meta)
            except (ValueError, OSError):
                LOG.warning("Could not restore a local job", exc_info=True)

    def close(self):
        for event in list(self.cancellations.values()):
            event.set()
        self.passwords.clear()
        self.worker.shutdown(wait=True, cancel_futures=True)

    def folder(self, job_id: str) -> Path:
        if not re.fullmatch(r"[a-f0-9]{32}", job_id):
            raise StoreError(404, "Document not found.")
        folder = self.root / job_id
        if not (folder / "meta.json").is_file():
            raise StoreError(404, "Document not found.")
        return folder

    def meta(self, job_id: str) -> dict:
        return json.loads((self.folder(job_id) / "meta.json").read_text(encoding="utf-8"))

    def update_meta(self, job_id: str, **changes):
        with self.lock:
            meta = self.meta(job_id)
            meta.update(changes, updated_at=now())
            atomic_json(self.folder(job_id) / "meta.json", meta)
            return meta

    def reserve(self, filename: str, force_ocr: bool) -> tuple[str, Path]:
        filename = Path(filename.replace("\\", "/")).name
        suffix = Path(filename).suffix.lower()
        if suffix not in SUPPORTED:
            raise StoreError(415, "Choose a PDF, PNG, JPEG, TIFF, BMP, or WebP file.")
        name = re.sub(r"[^\w .()\-]", "_", Path(filename).stem)[:100].strip(". ") or "marksheet"
        filename = name + suffix
        job_id = uuid.uuid4().hex
        folder = self.root / job_id
        folder.mkdir()
        atomic_json(folder / "meta.json", {
            "id": job_id, "filename": filename, "status": "uploading", "progress": "Receiving file…",
            "force_ocr": force_ocr, "created_at": now(), "updated_at": now(), "version": 0,
            "row_count": 0, "review_count": 0, "page_count": 0, "error": None,
        })
        return job_id, folder / filename

    def submit(self, job_id: str, password: str | None = None):
        self.cancellations[job_id] = threading.Event()
        self.passwords[job_id] = password or None
        self.update_meta(job_id, status="queued", progress="Waiting for the local extraction engine…")
        self.worker.submit(self._extract, job_id)

    def import_file(self, source: Path, force_ocr=False, password: str | None = None) -> str:
        job_id, target = self.reserve(source.name, force_ocr)
        try:
            if source.stat().st_size > MAX_UPLOAD_BYTES:
                raise StoreError(413, "The file exceeds the 50 MB limit.")
            shutil.copyfile(source, target)
            self.submit(job_id, password)
        except Exception:
            shutil.rmtree(target.parent, ignore_errors=True)
            raise
        return job_id

    def _extract(self, job_id: str):
        event = self.cancellations[job_id]
        password = self.passwords.pop(job_id, None)
        try:
            if event.is_set():
                raise Cancelled()
            meta = self.update_meta(job_id, status="processing", progress="Opening document…")
            document = open_document(self.folder(job_id) / meta["filename"], force_ocr=meta["force_ocr"],
                                     password=password, cancel=event, max_pages=MAX_PAGES,
                                     progress=lambda text: self.update_meta(job_id, progress=text))
            self.update_meta(job_id, progress="Pairing rolls and marks by row…")
            extract_document(document)
            if not document.records and any(page.method == "PDF text" for page in document.pages):
                self.update_meta(job_id, progress="PDF text looked unusable; trying local image OCR…")
                reocr_pages(document, progress=lambda text: self.update_meta(job_id, progress=text))
                extract_document(document)
            if event.is_set():
                raise Cancelled()
            pages_dir = self.folder(job_id) / "pages"
            pages_dir.mkdir(exist_ok=True)
            for page in document.pages:
                page.image.save(pages_dir / f"{page.number}.png")
            with self.lock:
                if event.is_set():
                    raise Cancelled()
                self.save_document(job_id, document)
                self.update_meta(job_id, status="ready", progress="Extraction complete. Review your results.")
        except Cancelled:
            self.update_meta(job_id, status="cancelled", progress="Extraction cancelled.")
        except Exception as exc:
            LOG.exception("Document extraction failed")
            message = str(exc) if isinstance(exc, (ValueError, OSError, RuntimeError)) else "Extraction failed. Try a clearer PDF or image."
            self.update_meta(job_id, status="error", error=message, progress="Could not extract this document.")
        finally:
            self.cancellations.pop(job_id, None)

    def require_ready(self, job_id: str, version: int | None = None) -> dict:
        meta = self.meta(job_id)
        if meta["status"] != "ready":
            raise StoreError(409, "Wait for extraction to finish before editing or exporting.")
        if version is not None and meta["version"] != version:
            raise StoreError(409, "This document changed in another tab. Refresh it before saving your changes.")
        return meta

    def load_document(self, job_id: str, *, images=False) -> Document:
        """Reconstruct a saved review without invoking PDFium or OCR on reads/edits."""
        folder = self.folder(job_id)
        payload = json.loads((folder / "review.json").read_text(encoding="utf-8"))
        pages = []
        for saved in payload["pages"]:
            if images:
                with Image.open(folder / "pages" / f"{saved['number']}.png") as image:
                    preview = image.convert("RGB")
            else:
                preview = Image.new("RGB", (1, 1))
            pages.append(Page(saved["number"], preview, [Word(**w) for w in saved["words"]], saved["method"],
                              Layout(**saved["layout"]) if saved["layout"] else None,
                              [MarkCandidate(**c) for c in saved.get("mark_candidates", [])],
                              saved.get("notes", [])))
        return Document(folder / self.meta(job_id)["filename"], pages, [Record(**r) for r in payload["records"]],
                        payload["max_mark"], payload.get("warnings", []), payload["source_sha256"],
                        [ExportColumn(**c) for c in payload["export_columns"]] if payload.get("export_columns") is not None else None,
                        payload.get("export_overrides", {}), payload.get("absent_codes", []),
                        payload.get("allow_fractions", True))

    def save_document(self, job_id: str, document: Document):
        validate(document)
        save_session(document, self.folder(job_id) / "review.json", verify_source=False)
        meta = self.meta(job_id)
        # Dimensions are immutable. Keep them in metadata so normal reads never
        # open/deserialize full-resolution page images.
        dimensions = meta.get("dimensions") or [[p.image.width, p.image.height] for p in document.pages]
        self.update_meta(job_id, version=meta["version"] + 1,
                         page_count=len(document.pages), row_count=len(document.records),
                         review_count=sum(bool(r.issues) for r in document.records), dimensions=dimensions)

    def view(self, job_id: str, *, full=True) -> dict:
        with self.lock:
            meta = self.meta(job_id)
            result = {key: value for key, value in meta.items() if key != "dimensions"}
            if meta["status"] == "ready" and full:
                document = self.load_document(job_id)
                result.update(max_mark=document.max_mark, warnings=document.warnings,
                              absent_codes=document.absent_codes, allow_fractions=document.allow_fractions,
                              export_columns=[asdict(c) for c in document.export_columns] if document.export_columns is not None else None,
                              records=[dict(asdict(r), status=r.status) for r in document.records],
                              verified_count=sum(r.reviewed and not r.issues for r in document.records),
                              pages=[{"number": p.number, "method": p.method, "notes": p.notes,
                                      "width": meta["dimensions"][i][0], "height": meta["dimensions"][i][1],
                                      "layout": asdict(p.layout) if p.layout else None,
                                      "mark_candidates": [asdict(c) for c in p.mark_candidates],
                                      "image_url": f"/api/documents/{job_id}/pages/{p.number}.png"}
                                     for i, p in enumerate(document.pages)])
            return result

    def list(self) -> list[dict]:
        with self.lock:
            result = []
            for path in self.root.glob("*/meta.json"):
                try:
                    result.append(self.view(path.parent.name, full=False))
                except (ValueError, OSError):
                    continue
            return sorted(result, key=lambda doc: doc["created_at"], reverse=True)

    def cancel(self, job_id: str):
        with self.lock:
            meta = self.meta(job_id)
            if meta["status"] not in ACTIVE:
                raise StoreError(409, "This extraction is no longer running.")
            event = self.cancellations.get(job_id)
            if event:
                event.set()
            return self.update_meta(job_id, status="cancelling", progress="Cancelling after the current page…")

    def delete(self, job_id: str):
        with self.lock:
            if self.meta(job_id)["status"] in ACTIVE | {"uploading"}:
                raise StoreError(409, "Cancel extraction and wait for it to stop before deleting this document.")
            shutil.rmtree(self.folder(job_id))

    def reextract(self, job_id: str, page_number: int, layout: Layout | None, scope: str, version: int):
        with self.lock:
            self.require_ready(job_id, version)
            document = self.load_document(job_id, images=True)
            old_pages = {row.id: row.page for row in document.records}
            if not 1 <= page_number <= len(document.pages):
                raise StoreError(404, "Page not found.")
        if scope == "auto":
            extract_document(document)
        else:
            if layout is None:
                raise StoreError(422, "Select roll and marks columns first.")
            page = document.pages[page_number - 1]
            page.layout = layout
            if scope == "all":
                for other in document.pages:
                    if other is page:
                        continue
                    if other.layout is None:
                        other.layout = deepcopy(layout)
                        other.layout.top = 0
                    other.layout.roll, other.layout.mark = layout.roll, layout.mark
                    other.layout.label, other.layout.max_mark = layout.label, layout.max_mark
                    other.layout.automatic = False
                extract_document(document, autodetect=False)
            else:
                document.records = [r for r in document.records if r.page != page_number] + extract_page(page)
                document.records.sort(key=lambda r: (r.page, r.box[1]))
                document.warnings = [w for w in document.warnings if not w.startswith(f"Page {page_number}:")]
                if not any(r.page == page_number for r in document.records):
                    document.warnings.append(f"Page {page_number}: no rows found. Check your selection.")
        if scope in {"auto", "all"}:
            document.export_overrides.clear()
        else:
            document.export_overrides = {key: value for key, value in document.export_overrides.items()
                                         if old_pages.get(key) != page_number}
        if document.export_columns:
            from .columns import default_columns
            defaults = {c.source: c for c in default_columns(document)}
            for column in document.export_columns:
                if column.source in defaults:
                    column.regions = defaults[column.source].regions
        with self.lock:
            current = self.meta(job_id)
            if current["status"] != "ready":
                raise StoreError(409, "Wait for extraction to finish before editing or exporting.")
            if current["version"] != version:
                raise StoreError(409, "This document changed in another tab. Refresh it before saving your changes.")
            self.save_document(job_id, document)
            return self.view(job_id)
