"""FastAPI backend and same-origin web UI, served locally by default."""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import threading
import uuid
import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from starlette.background import BackgroundTask
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .extract import LOW_CONFIDENCE, normalize, validate
from .models import ExportColumn, Layout, Record
from .columns import apply_export_plan, discover_columns, table_preview
from .storage import export_csv, export_xlsx
from .web_store import JobStore, MAX_PAGES, MAX_UPLOAD_BYTES, StoreError

STATIC = Path(__file__).with_name("static")
PROJECT = Path(__file__).resolve().parents[2]


class Versioned(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    version: int = Field(ge=1)


class RowEdit(Versioned):
    roll: str = Field(max_length=64)
    mark: str = Field(max_length=64)
    reviewed: bool = True


class RowAdd(RowEdit):
    page: int = Field(ge=1)


class SettingsEdit(Versioned):
    max_mark: float | None = Field(default=None, gt=0)
    absent_codes: list[Annotated[str, Field(max_length=16)]] | None = Field(default=None, max_length=20)
    allow_fractions: bool | None = None

    @field_validator("absent_codes")
    @classmethod
    def clean_absent_codes(cls, codes):
        if codes is None:
            return None
        cleaned = []
        for code in codes:
            value = code.strip()
            if value and value not in cleaned:
                cleaned.append(value)
        return cleaned


class LayoutEdit(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    roll: tuple[float, float]
    mark: tuple[float, float]
    top: float = Field(ge=0, le=1)
    bottom: float = Field(ge=0, le=1)
    label: str = Field(default="Custom marks column", max_length=80)
    max_mark: float | None = Field(default=None, gt=0)
    automatic: bool = False

    @model_validator(mode="after")
    def valid_geometry(self):
        if not (0 <= self.roll[0] < self.roll[1] <= self.mark[0] < self.mark[1] <= 1 and self.top < self.bottom):
            raise ValueError("Select separate roll and marks columns from left to right, and a non-empty row area.")
        return self


class Reextract(Versioned):
    page: int = Field(ge=1)
    scope: Literal["page", "all", "auto"] = "page"
    layout: LayoutEdit | None = None


class ColumnChoice(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    name: str = Field(min_length=1, max_length=80)
    kind: Literal["text", "number"] = "text"
    source: Literal["roll", "mark", "region"] = "region"
    regions: dict[str, tuple[float, float, float, float]] = Field(default_factory=dict, max_length=50)

    @field_validator("name")
    @classmethod
    def nonblank_name(cls, name):
        if not name.strip():
            raise ValueError("Every column needs a name.")
        return name.strip()

    @model_validator(mode="after")
    def geometry(self):
        if self.source == "region" and not self.regions:
            raise ValueError("Select a source region for this column.")
        for page, box in self.regions.items():
            if not page.isdigit() or int(page) < 1 or not (0 <= box[0] < box[2] <= 1 and 0 <= box[1] < box[3] <= 1):
                raise ValueError("Column regions must be inside a source page.")
        return self


class ExportPlan(Versioned):
    columns: list[ColumnChoice] = Field(min_length=1, max_length=32)
    overrides: dict[str, dict[str, Annotated[str, Field(max_length=4096)]]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def unique_columns(self):
        if len({c.id for c in self.columns}) != len(self.columns):
            raise ValueError("Each selected column must be unique.")
        if len({c.name.casefold() for c in self.columns}) != len(self.columns):
            raise ValueError("Give each column a different name.")
        for source in ("roll", "mark"):
            if sum(c.source == source for c in self.columns) > 1:
                raise ValueError("Select each built-in column only once.")
        return self


def available_examples() -> dict:
    options = {
        "cse251": {"filename": "CSE 251_CT_marks.pdf", "title": "CSE 251 · Class test", "description": "A marksheet with a serial column and total marks.", "folder": "examples"},
        "ooad": {"filename": "OOAD_tutorial.pdf", "title": "OOAD · Lab evaluation", "description": "A multi-page table with a headerless continuation.", "folder": "examples"},
        "cse305": {"filename": "CSE-305-TUTORIAL-MARKS.pdf", "title": "CSE 305 · Tutorial", "description": "Your latest tutorial marksheet.", "folder": "test_sources"},
    }
    return {key: value for key, value in options.items() if (PROJECT / value["folder"] / value["filename"]).is_file()}


def create_app(data_dir: str | Path | None = None, *, initial_source: Path | None = None,
               browser_url: str | None = None) -> FastAPI:
    default_data = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "ResultDesk" if os.name == "nt" else Path.cwd() / ".result-desk"
    data_dir = Path(data_dir or os.environ.get("RESULT_DESK_DATA_DIR", default_data))
    store = JobStore(data_dir)

    @asynccontextmanager
    async def lifespan(app):
        if initial_source is not None:
            store.import_file(initial_source.resolve())
        if browser_url:
            timer = threading.Timer(1.0, lambda: webbrowser.open(browser_url))
            timer.daemon = True
            timer.start()
        yield
        store.close()

    app = FastAPI(title="Result Desk", version="0.3.0", lifespan=lifespan, docs_url=None, redoc_url=None,
                  openapi_url="/api/openapi.json")
    app.state.store = store
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "[::1]", "testserver"])

    @app.exception_handler(StoreError)
    async def store_error(_request, exc):
        return JSONResponse({"detail": exc.message}, status_code=exc.status)

    @app.middleware("http")
    async def local_requests(request: Request, call_next):
        # Mutations must originate from the app itself. No cross-origin API is
        # enabled; the UI and backend are served from the same local origin.
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            if (origin and urlsplit(origin).netloc != request.headers.get("host")) or request.headers.get("sec-fetch-site") == "cross-site":
                return JSONResponse({"detail": "Cross-origin changes are not allowed."}, status_code=403)
        try:
            length = int(request.headers.get("content-length", "0"))
        except ValueError:
            return JSONResponse({"detail": "Invalid request size."}, status_code=400)
        if length > MAX_UPLOAD_BYTES + 1024 * 1024:
            return JSONResponse({"detail": "The file exceeds the 50 MB limit."}, status_code=413)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        if request.url.path.startswith("/api/"):
            if "/pages/" in request.url.path or request.url.path.endswith("/source"):
                response.headers["Cache-Control"] = "private, max-age=3600"
            else:
                response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/api/health")
    def health():
        return {"status": "ok", "storage": "local", "max_upload_mb": 50, "max_pages": MAX_PAGES,
                "low_confidence_threshold": LOW_CONFIDENCE}

    @app.get("/api/examples")
    def examples():
        return [{"id": key, **{k: v for k, v in value.items() if k != "folder"}} for key, value in available_examples().items()]

    @app.post("/api/examples/{example_id}", status_code=202)
    def use_example(example_id: str):
        example = available_examples().get(example_id)
        if not example:
            raise HTTPException(404, "Example not found.")
        job_id = store.import_file(PROJECT / example["folder"] / example["filename"])
        return store.view(job_id)

    @app.get("/api/documents")
    def documents():
        return store.list()

    @app.post("/api/documents", status_code=202)
    async def upload(file: Annotated[UploadFile, File()], force_ocr: Annotated[bool, Form()] = False,
                     password: Annotated[str | None, Form()] = None):
        job_id = None
        try:
            job_id, target = store.reserve(file.filename or "marksheet", force_ocr)
            size = 0
            with target.open("wb") as stream:
                while chunk := await file.read(1024 * 1024):
                    size += len(chunk)
                    if size > MAX_UPLOAD_BYTES:
                        raise StoreError(413, "The file exceeds the 50 MB limit.")
                    stream.write(chunk)
            if not size:
                raise StoreError(400, "The file is empty. Choose a PDF or image with a marksheet.")
            store.submit(job_id, password)
            return store.view(job_id)
        except Exception:
            if job_id:
                shutil.rmtree(store.root / job_id, ignore_errors=True)
            raise
        finally:
            await file.close()

    @app.get("/api/documents/{job_id}")
    def document(job_id: str):
        return store.view(job_id)

    @app.delete("/api/documents/{job_id}", status_code=204)
    def remove_document(job_id: str):
        store.delete(job_id)

    @app.post("/api/documents/{job_id}/cancel")
    def cancel(job_id: str):
        store.cancel(job_id)
        return store.view(job_id)

    @app.get("/api/documents/{job_id}/pages/{page_number}.png")
    def page_image(job_id: str, page_number: int):
        meta = store.require_ready(job_id)
        if not 1 <= page_number <= meta["page_count"]:
            raise HTTPException(404, "Page not found.")
        return FileResponse(store.folder(job_id) / "pages" / f"{page_number}.png", media_type="image/png")

    @app.get("/api/documents/{job_id}/source")
    def source(job_id: str):
        meta = store.meta(job_id)
        return FileResponse(store.folder(job_id) / meta["filename"], filename=meta["filename"])

    @app.patch("/api/documents/{job_id}/rows/{row_id}")
    def edit_row(job_id: str, row_id: str, values: RowEdit):
        with store.lock:
            store.require_ready(job_id, values.version)
            doc = store.load_document(job_id)
            row = next((r for r in doc.records if r.id == row_id), None)
            if row is None:
                raise HTTPException(404, "Row not found.")
            row.roll, row.mark, row.reviewed = normalize(values.roll), normalize(values.mark), values.reviewed
            store.save_document(job_id, doc)
            return store.view(job_id)

    @app.post("/api/documents/{job_id}/rows", status_code=201)
    def add_row(job_id: str, values: RowAdd):
        with store.lock:
            store.require_ready(job_id, values.version)
            doc = store.load_document(job_id)
            if not 1 <= values.page <= len(doc.pages):
                raise HTTPException(404, "Page not found.")
            page = doc.pages[values.page - 1]
            doc.records.append(Record("manual-" + uuid.uuid4().hex, values.page, normalize(values.roll),
                                      normalize(values.mark), "", "", (0, 0, 1, 1), "Manual", 1.0,
                                      page.layout.max_mark if page.layout else None, reviewed=values.reviewed))
            store.save_document(job_id, doc)
            return store.view(job_id)

    @app.delete("/api/documents/{job_id}/rows/{row_id}")
    def delete_row(job_id: str, row_id: str, values: Versioned):
        with store.lock:
            store.require_ready(job_id, values.version)
            doc = store.load_document(job_id)
            if not any(r.id == row_id for r in doc.records):
                raise HTTPException(404, "Row not found.")
            doc.records = [r for r in doc.records if r.id != row_id]
            doc.export_overrides.pop(row_id, None)
            store.save_document(job_id, doc)
            return store.view(job_id)

    @app.patch("/api/documents/{job_id}/settings")
    def settings(job_id: str, values: SettingsEdit):
        with store.lock:
            store.require_ready(job_id, values.version)
            doc = store.load_document(job_id)
            if "max_mark" in values.model_fields_set:
                doc.max_mark = values.max_mark
            if values.absent_codes is not None:
                doc.absent_codes = values.absent_codes
            if values.allow_fractions is not None:
                doc.allow_fractions = values.allow_fractions
            store.save_document(job_id, doc)
            return store.view(job_id)

    @app.post("/api/documents/{job_id}/reextract")
    def reextract(job_id: str, values: Reextract):
        layout = Layout(**values.layout.model_dump()) if values.layout else None
        return store.reextract(job_id, values.page, layout, values.scope, values.version)

    @app.get("/api/documents/{job_id}/columns")
    def column_designer(job_id: str):
        from dataclasses import asdict
        with store.lock:
            meta = store.require_ready(job_id)
            doc = store.load_document(job_id, images=True)
            return {"version": meta["version"], "candidates": [asdict(c) for c in discover_columns(doc)],
                    "overrides": doc.export_overrides, "preview": table_preview(doc)}

    def read_plan(job_id: str, values: ExportPlan):
        store.require_ready(job_id, values.version)
        doc = store.load_document(job_id)
        columns = [ExportColumn(**c.model_dump()) for c in values.columns]
        if any(int(page) > len(doc.pages) for c in columns for page in c.regions):
            raise HTTPException(422, "A selected column refers to a page that does not exist.")
        try:
            apply_export_plan(doc, columns, values.overrides)
            validate(doc)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return doc

    @app.post("/api/documents/{job_id}/columns/preview")
    def preview_columns(job_id: str, values: ExportPlan):
        with store.lock:
            doc = read_plan(job_id, values)
            return table_preview(doc)

    @app.put("/api/documents/{job_id}/columns")
    def save_columns(job_id: str, values: ExportPlan):
        with store.lock:
            doc = read_plan(job_id, values)
            store.save_document(job_id, doc)
            return store.view(job_id)

    @app.get("/api/documents/{job_id}/export/{file_format}")
    def export(job_id: str, file_format: Literal["xlsx", "csv"], version: Annotated[int | None, Query(ge=1)] = None):
        with store.lock:
            meta = store.require_ready(job_id, version)
            doc = store.load_document(job_id)
        # A document can be deleted in another tab while a download is in
        # flight. Keep export snapshots outside its folder until sent.
        folder = store.root / ".exports"
        folder.mkdir(exist_ok=True)
        output = folder / f"{uuid.uuid4().hex}.{file_format}"
        try:
            (export_xlsx if file_format == "xlsx" else export_csv)(doc, output)
        except Exception:
            output.unlink(missing_ok=True)
            raise
        return FileResponse(output, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" if file_format == "xlsx" else "text/csv",
                            filename=Path(meta["filename"]).stem + f".results.{file_format}",
                            background=BackgroundTask(output.unlink, missing_ok=True))

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})

    app.mount("/static", StaticFiles(directory=STATIC, check_dir=False), name="static")
    return app


def main(argv=None):
    import uvicorn

    parser = argparse.ArgumentParser(description="Run Result Desk's local web interface and backend.")
    parser.add_argument("source", nargs="?", type=Path, help="Optionally import a PDF/image on startup")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    if args.source and not args.source.is_file():
        parser.error("The source file does not exist")
    url = f"http://127.0.0.1:{args.port}"
    app = create_app(args.data_dir, initial_source=args.source,
                     browser_url=None if args.no_browser else url)
    if sys.stdout:
        print(f"Result Desk: {url}\nKeep this terminal open. Press Ctrl+C to stop the local backend.", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=args.port, workers=1, loop="asyncio", http="h11",
                log_config=None if sys.stderr is None else uvicorn.config.LOGGING_CONFIG,
                access_log=False)


if __name__ == "__main__":
    main()
