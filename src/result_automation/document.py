from __future__ import annotations

from pathlib import Path
import hashlib
import math
from threading import Event

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_raw
from PIL import Image, ImageOps, UnidentifiedImageError

from .models import Cancelled, Document, Page, Progress, Word
from .ocr import LocalOCR
from .preprocess import orient_image, preprocess_image

SUPPORTED = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}


def text_is_usable(words: list[Word]) -> bool:
    text = "".join(word.text for word in words)
    chars = len("".join(text.split()))
    numeric = sum(any(character.isdigit() for character in word.text) for word in words)
    damaged = text.count("\ufffd")
    return chars >= 20 and (numeric >= 8 or chars >= 160) and damaged <= max(3, chars * .05)


def ocr_score(words: list[Word]) -> float:
    if not words:
        return 0.0
    characters = sum(len(word.text.strip()) for word in words)
    return characters * (sum(word.confidence for word in words) / len(words))


def recognize_page(page: Page, ocr: LocalOCR, *, perspective: bool = False,
                   progress: Progress = lambda _: None) -> list[str]:
    image, notes = preprocess_image(page.image, perspective=perspective)
    words = ocr.recognize(image)
    if ocr_score(words) < 30 or not words:
        if progress:
            progress("Checking page orientation…")
        image, angle = orient_image(image, ocr.recognize)
        if angle:
            words = ocr.recognize(image)
            notes.append(f"rotated {angle:g}°")
    page.image, page.words, page.method = image, words, "Local OCR"
    page.notes = notes
    return notes


def reocr_page(page: Page, ocr: LocalOCR | None = None) -> list[Word]:
    engine = ocr or LocalOCR()
    recognize_page(page, engine, progress=lambda _: None)
    return page.words


def pdf_words(page) -> list[Word]:
    """Read character geometry rather than trusting PDF text reading order."""
    width, height = page.get_size()
    words: list[Word] = []
    textpage = page.get_textpage()
    chars: list[str] = []
    bounds = None
    last_box = None
    last_vertical = False

    def flush():
        nonlocal chars, bounds
        if chars and bounds:
            words.append(Word("".join(chars), tuple(bounds)))
        chars, bounds = [], None

    try:
        for index in range(textpage.count_chars()):
            char = textpage.get_text_range(index, 1)
            if not char or char.isspace():
                flush()
                continue
            left, bottom, right, top = textpage.get_charbox(index)
            box = [left / width, 1 - top / height, right / width, 1 - bottom / height]
            vertical = abs(math.sin(pdfium_raw.FPDFText_GetCharAngle(textpage, index))) > 0.7
            if right <= left or top <= bottom:
                continue
            if bounds:
                char_height = max(box[3] - box[1], bounds[3] - bounds[1])
                if vertical and last_vertical:
                    # Spreadsheet PDFs often rotate only their headers. Keep
                    # vertical glyphs in encoded reading order instead of
                    # splitting each letter into a separate OCR-like token.
                    char_width = max(box[2] - box[0], last_box[2] - last_box[0])
                    gap = max(0, box[1] - last_box[3], last_box[1] - box[3])
                    if (abs((box[0] + box[2] - last_box[0] - last_box[2]) / 2) > char_width * 0.7
                            or gap > max(box[3] - box[1], last_box[3] - last_box[1]) * 1.5):
                        flush()
                elif vertical != last_vertical or (abs((box[1] + box[3] - bounds[1] - bounds[3]) / 2) > char_height * 0.65
                        or box[0] < bounds[0] - 0.002
                        or box[0] - bounds[2] > char_height * height / width * 0.8):
                    flush()
            chars.append(char)
            bounds = box if bounds is None else [min(bounds[0], box[0]), min(bounds[1], box[1]),
                                                 max(bounds[2], box[2]), max(bounds[3], box[3])]
            last_box, last_vertical = box, vertical
        flush()
    finally:
        textpage.close()
    return words


def open_document(path: str | Path, *, force_ocr: bool = False, password: str | None = None,
                  progress: Progress = lambda _: None, cancel: Event | None = None,
                  read_words: bool = True, max_pages: int | None = None) -> Document:
    path = Path(path).resolve()
    if path.suffix.lower() not in SUPPORTED:
        raise ValueError("Choose a PDF, PNG, JPEG, TIFF, BMP, or WebP file.")
    if not path.is_file():
        raise FileNotFoundError(f"Source file was not found: {path}")
    with path.open("rb") as stream:
        source_digest = hashlib.file_digest(stream, "sha256").hexdigest()
    ocr = LocalOCR()
    pages = []

    def check_cancel():
        if cancel is not None and cancel.is_set():
            raise Cancelled()

    if path.suffix.lower() == ".pdf":
        try:
            pdf = pdfium.PdfDocument(path, password=password or None)
        except pdfium.PdfiumError as exc:
            message = str(exc).lower()
            if getattr(exc, "err_code", None) == getattr(pdfium_raw, "FPDF_ERR_PASSWORD", 4) or "password" in message:
                if password:
                    raise ValueError("The PDF password is incorrect.") from exc
                raise ValueError("This PDF is password protected. Add its password in the upload dialog.") from exc
            raise ValueError("Cannot open this PDF. It may be damaged or password protected.") from exc
        try:
            if max_pages is not None and len(pdf) > max_pages:
                raise ValueError(f"This document exceeds the {max_pages}-page limit. Split it into smaller files.")
            for index in range(len(pdf)):
                check_cancel()
                progress(f"Reading page {index + 1} of {len(pdf)}…")
                page = pdf[index]
                try:
                    words = pdf_words(page) if read_words and not force_ocr else []
                    # 200 DPI for OCR; enough pixels for small decimal marks.
                    width, height = page.get_size()
                    scale = min(200 / 72, 3000 / max(1.0, width, height))
                    bitmap = page.render(scale=scale)
                    image = bitmap.to_pil().convert("RGB")
                    bitmap.close()
                finally:
                    page.close()
                method, notes = "PDF text", []
                if read_words and (force_ocr or not text_is_usable(words)):
                    progress(f"Recognizing page {index + 1} locally…")
                    rendered = Page(index + 1, image, [], "Local OCR")
                    notes = recognize_page(rendered, ocr, progress=progress)
                    image, words = rendered.image, rendered.words
                    method = rendered.method
                pages.append(Page(index + 1, image, words, method, notes=notes))
        finally:
            pdf.close()
    else:
        try:
            with Image.open(path) as image_file:
                if max_pages is not None and getattr(image_file, "n_frames", 1) > max_pages:
                    raise ValueError(f"This image exceeds the {max_pages}-page limit.")
                for index in range(getattr(image_file, "n_frames", 1)):
                    check_cancel()
                    image_file.seek(index)
                    image = ImageOps.exif_transpose(image_file.copy()).convert("RGB")
                    image.thumbnail((3000, 3000), Image.Resampling.LANCZOS)
                    progress(f"Recognizing image {index + 1} locally…")
                    page = Page(index + 1, image, [], "Local OCR")
                    if read_words:
                        recognize_page(page, ocr, perspective=True, progress=progress)
                    pages.append(page)
        except UnidentifiedImageError as exc:
            raise ValueError("This image is damaged or uses an unsupported format.") from exc
    check_cancel()
    return Document(path, pages, source_sha256=source_digest)


def reocr_pages(document: Document, ocr: LocalOCR | None = None,
                progress: Progress = lambda _: None) -> None:
    engine = ocr or LocalOCR()
    for page in document.pages:
        progress(f"Recognizing page {page.number} locally…")
        recognize_page(page, engine, progress=progress)
