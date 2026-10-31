"""Spatial table extraction. Missing cells never shift subsequent rows."""
from __future__ import annotations

import re
from collections import Counter
from decimal import Decimal, InvalidOperation
from statistics import median

import cv2
import numpy as np

from .models import Document, Layout, Page, Record, Word

DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")


def normalize(text: str) -> str:
    return text.translate(DIGITS).strip().replace("\u2212", "-")


def valid_roll(text: str) -> bool:
    return bool(re.fullmatch(r"[0-9]{1,16}", normalize(text)))


def number(text: str) -> Decimal | None:
    text = normalize(text)
    if not re.fullmatch(r"-?[0-9]+(?:\.[0-9]+)?", text):
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _runs(indices) -> list[float]:
    groups: list[list[int]] = []
    for index in indices:
        if not groups or index - groups[-1][-1] > 2:
            groups.append([])
        groups[-1].append(int(index))
    return [float(median(group)) for group in groups]


def detect_grid(page: Page) -> tuple[list[float], list[float]]:
    image = page.image.copy()
    image.thumbnail((1800, 2000))
    gray = cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2GRAY)
    height, width = gray.shape
    binary = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                   cv2.THRESH_BINARY_INV, 31, 15)
    vertical = cv2.morphologyEx(binary, cv2.MORPH_OPEN,
                              np.ones((max(20, height // 18), 1), np.uint8))
    horizontal = cv2.morphologyEx(binary, cv2.MORPH_OPEN,
                                np.ones((1, max(20, width // 18)), np.uint8))
    xs = _runs(np.flatnonzero(np.count_nonzero(vertical, axis=0) > height * 0.16))
    ys = _runs(np.flatnonzero(np.count_nonzero(horizontal, axis=1) > width * 0.35))
    return [x / width for x in xs], [y / height for y in ys]


def _column(center: float, rules: list[float], fallback_half: float) -> tuple[float, float]:
    for left, right in zip(rules, rules[1:]):
        if left <= center <= right:
            return left, right
    return max(0.0, center - fallback_half), min(1.0, center + fallback_half)


def group_lines(words: list[Word]) -> list[list[Word]]:
    lines: list[list[Word]] = []
    for word in sorted(words, key=lambda w: w.cy):
        height = max(0.003, word.box[3] - word.box[1])
        if lines and abs(word.cy - median(w.cy for w in lines[-1])) < height * 0.6:
            lines[-1].append(word)
        else:
            lines.append([word])
    return [sorted(line, key=lambda w: w.box[0]) for line in lines]


def detect_layout(page: Page, previous: Layout | None = None,
                  grid: tuple[list[float], list[float]] | None = None) -> Layout:
    xs, ys = grid if grid is not None else detect_grid(page)
    headers = [w for w in page.words if re.search(r"\broll\b", w.text, re.I)]
    header = min(headers, key=lambda w: (w.cx, w.cy)) if headers else None
    if header:
        roll = _column(header.cx, xs, max(0.035, (header.box[2] - header.box[0]) / 2 + 0.01))
        header_y = header.cy
    elif previous:
        roll = previous.roll
        header_y = None
    else:
        # For a headerless image, find a vertical cluster of integer cells on the left.
        candidates = [w for w in page.words if w.cx < 0.45 and valid_roll(w.text)]
        clusters: list[list[Word]] = []
        for word in sorted(candidates, key=lambda w: w.cx):
            if not clusters or abs(word.cx - median(w.cx for w in clusters[-1])) > 0.025:
                clusters.append([])
            clusters[-1].append(word)
        if not clusters:
            raise ValueError(f"Page {page.number}: could not locate the roll column. "
                             "Select the roll and marks columns manually.")
        best = max(clusters, key=lambda c: (len(c), -median(w.cx for w in c)))
        roll = _column(median(w.cx for w in best), xs, 0.055)
        header_y = None
    if len(xs) >= 3:
        mark = xs[-2], xs[-1]
    elif previous:
        mark = previous.mark
    else:
        numeric = [w for w in page.words if number(w.text) is not None and w.cx > 0.5]
        if not numeric:
            raise ValueError(f"Page {page.number}: could not locate the marks column.")
        rightmost = max(w.cx for w in numeric)
        mark = max(0.0, rightmost - 0.045), min(1.0, rightmost + 0.045)
    top, bottom = (ys[0], ys[-1]) if len(ys) >= 2 else (0.0, 0.98)
    label, maximum = (previous.label, previous.max_mark) if previous else ("Rightmost marks", None)
    if header_y is not None:
        above = [y for y in ys if y < header_y]
        below = [y for y in ys if y > header_y + 0.003]
        header_top = max(above) if above else header.box[1] - 0.02
        header_bottom = min(below) if below else header.box[3] + 0.004
        nearby = [w for w in page.words if mark[0] <= w.cx <= mark[1]
                  and header_top <= w.cy < header_bottom]
        if nearby:
            rotated = any(w.box[3] - w.box[1] > (w.box[2] - w.box[0]) * 1.5 for w in nearby)
            label = " ".join(w.text for w in (nearby if rotated else sorted(nearby, key=lambda w: (round(w.cy, 2), w.cx))))
            match = re.search(r"\(\s*([0-9]+(?:\.[0-9]+)?)(?:\s+Marks?)?\s*\)", label, re.I)
            maximum = float(match[1]) if match else None
        top = min(below) if below else header.box[3] + 0.004
    return Layout(roll, mark, top, bottom, label, maximum)


def _cell(words: list[Word], bounds: tuple[float, float]) -> tuple[str, float]:
    selected = sorted((w for w in words if bounds[0] < w.cx < bounds[1]), key=lambda w: w.cx)
    # OCR may separate the decimal dot. Join pieces within the same cell only.
    return "".join(w.text for w in selected).strip(), min((w.confidence for w in selected), default=0.0)


def extract_page(page: Page) -> list[Record]:
    layout = page.layout
    if layout is None:
        return []
    _, ys = detect_grid(page)
    body = [w for w in page.words if layout.top <= w.cy <= layout.bottom]
    rules = [y for y in ys if layout.top - 0.002 <= y <= layout.bottom + 0.002]
    bands = []
    if len(rules) >= 3:
        boundaries = sorted(set([layout.top, *rules, layout.bottom]))
        for top, bottom in zip(boundaries, boundaries[1:]):
            if bottom - top > 0.006:
                bands.append((top, bottom, [w for w in body if top <= w.cy < bottom]))
    else:
        for line in group_lines(body):
            bands.append((min(w.box[1] for w in line) - 0.003,
                          max(w.box[3] for w in line) + 0.003, line))
    records = []
    for top, bottom, words in bands:
        raw_roll, roll_score = _cell(words, layout.roll)
        raw_mark, mark_score = _cell(words, layout.mark)
        # Exclude page furniture and repeated headers. Ruled rows with a name or
        # mark remain visible even when OCR misses the roll entirely.
        if re.search(r"roll|total|project|attendance", raw_roll, re.I):
            continue
        middle = [w for w in words if layout.roll[1] <= w.cx < layout.mark[0]]
        if not raw_roll and not raw_mark and not middle:
            continue
        if not valid_roll(raw_roll) and not raw_mark and not middle:
            continue
        if not rules and not raw_roll:
            continue
        row_id = f"p{page.number}-r{len(records) + 1}"
        records.append(Record(row_id, page.number, normalize(raw_roll), normalize(raw_mark),
                              raw_roll, raw_mark, (layout.roll[0], top, layout.mark[1], bottom),
                              page.method, min(roll_score, mark_score), layout.max_mark))
    return records


def validate(document: Document) -> None:
    counts = Counter(row.roll for row in document.records if valid_roll(row.roll))
    for row in document.records:
        row.issues = []
        if not valid_roll(row.roll):
            row.issues.append("Missing roll" if not row.roll else "Roll must contain digits only")
        elif counts[row.roll] > 1:
            row.issues.append("Duplicate roll")
        value = number(row.mark)
        if value is None:
            row.issues.append("Missing mark" if not row.mark or re.fullmatch(r"[-–—]+", row.mark)
                              else "Mark is not a number")
        elif value < 0:
            row.issues.append("Negative mark")
        else:
            maximum = document.max_mark if document.max_mark is not None else row.max_mark
            if maximum is not None and value > Decimal(str(maximum)):
                row.issues.append(f"Mark exceeds {maximum:g}")
        if row.method == "Local OCR" and not row.reviewed:
            row.issues.append("Verify OCR reading")


def extract_document(document: Document, *, autodetect: bool = True) -> Document:
    previous = None
    document.warnings = []
    document.records = []
    for page in document.pages:
        if autodetect or page.layout is None:
            try:
                page.layout = detect_layout(page, previous)
            except ValueError as exc:
                document.warnings.append(str(exc))
                continue
        previous = page.layout
        records = extract_page(page)
        if not records:
            document.warnings.append(f"Page {page.number}: no rows found; check the column selection.")
        document.records.extend(records)
    validate(document)
    return document
