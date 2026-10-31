"""Spatial table extraction. Missing cells never shift subsequent rows."""
from __future__ import annotations

import re
from collections import Counter
from decimal import Decimal, InvalidOperation
from statistics import median

import cv2
import numpy as np
from PIL import Image

from .models import Document, Layout, MarkCandidate, Page, Record, Word

DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
LOW_CONFIDENCE = 0.7
RETRY_ISSUES = ("Mark exceeds", "Mark is not a number", "Roll must contain digits only")


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


HEADER_WEIGHTS = (
    ("total", 5.0), ("marks", 4.0), ("mark", 3.0), ("score", 4.0), ("obtained", 4.0),
    ("project", 3.0), ("exam", 1.0), ("average", 1.0), ("avg", 1.0),
    ("grade", -6.0), ("letter", -4.0), ("roll", -5.0), ("serial", -5.0),
    ("name", -3.0), ("attendance", -1.0),
)


def _header_near(page: Page, left: float, right: float, top: float, bottom: float):
    nearby = [w for w in page.words if left <= w.cx <= right and top <= w.cy < bottom]
    if not nearby:
        return "", None
    rotated = any(w.box[3] - w.box[1] > (w.box[2] - w.box[0]) * 1.5 for w in nearby)
    text = " ".join(w.text for w in (nearby if rotated
                                    else sorted(nearby, key=lambda w: (round(w.cy, 2), w.cx)))).strip()
    match = re.search(r"\(\s*([0-9]+(?:\.[0-9]+)?)(?:\s+Marks?)?\s*\)", text, re.I)
    return re.sub(r"\s+", " ", text), (float(match[1]) if match else None)


def _candidate_columns(page: Page, xs: list[float], roll: tuple[float, float],
                       top: float, bottom: float, header_top: float, header_bottom: float,
                       previous: Layout | None) -> list[MarkCandidate]:
    candidates: list[MarkCandidate] = []
    body = [w for w in page.words if top <= w.cy <= bottom]
    columns = list(zip(xs, xs[1:])) if len(xs) >= 3 else []
    for index, (left, right) in enumerate(columns):
        center = (left + right) / 2
        if roll[0] <= center <= roll[1] or right - left < .015:
            continue
        inside = [w for w in body if left <= w.cx < right]
        numeric = [w for w in inside if number(w.text) is not None]
        label, maximum = _header_near(page, left, right, header_top, header_bottom)
        lowered = label.lower()
        header_score = sum(weight for needle, weight in HEADER_WEIGHTS if needle in lowered)
        ratio = len(numeric) / len(inside) if inside else 0.0
        score = header_score + min(len(numeric), 30) / 10 + ratio * 2 + max(0.0, center - .5) * 2
        if not numeric and header_score <= 0:
            continue
        candidates.append(MarkCandidate(f"mark-{index}", label or f"Column {index + 1}",
                                        max(0.0, left), min(1.0, right), top, bottom,
                                        maximum, score))
    if not columns:
        numeric = [w for w in body if number(w.text) is not None and w.cx > .5]
        clusters: list[list[Word]] = []
        for word in sorted(numeric, key=lambda w: w.cx):
            if not clusters or abs(word.cx - median(w.cx for w in clusters[-1])) > .03:
                clusters.append([])
            clusters[-1].append(word)
        for index, cluster in enumerate(clusters):
            center = median(w.cx for w in cluster)
            label, maximum = _header_near(page, max(0.0, center - .05), min(1.0, center + .05),
                                          header_top, header_bottom)
            candidates.append(MarkCandidate(f"mark-{index}", label or "Marks",
                                            max(0.0, center - .05), min(1.0, center + .05),
                                            top, bottom, maximum, len(cluster) + center))
    if not candidates:
        mark = previous.mark if previous else None
        if mark:
            label, maximum = (previous.label, previous.max_mark) if previous else ("Marks", None)
            candidates.append(MarkCandidate("mark-previous", label, mark[0], mark[1], top, bottom,
                                            maximum, 1.0))
    return sorted(candidates, key=lambda candidate: candidate.score, reverse=True)[:6]


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
    top, bottom = (ys[0], ys[-1]) if len(ys) >= 2 else (0.0, 0.98)
    if header_y is not None:
        above = [y for y in ys if y < header_y]
        below = [y for y in ys if y > header_y + 0.003]
        header_top = max(above) if above else header.box[1] - 0.02
        header_bottom = min(below) if below else header.box[3] + 0.004
        top = min(below) if below else header.box[3] + 0.004
    else:
        header_top = max(0.0, top - .08)
        header_bottom = top
    candidates = _candidate_columns(page, xs, roll, top, bottom, header_top, header_bottom, previous)
    if candidates:
        chosen = candidates[0]
        mark = chosen.left, chosen.right
        label, maximum = chosen.label, chosen.max_mark
        if header is None and previous and (not chosen.label or chosen.label.startswith("Column ")
                                            or chosen.label in {"Marks", "Rightmost marks"}):
            label, maximum = previous.label, previous.max_mark
    elif previous:
        mark = previous.mark
        label, maximum = previous.label, previous.max_mark
    else:
        numeric = [w for w in page.words if number(w.text) is not None and w.cx > 0.5]
        if not numeric:
            raise ValueError(f"Page {page.number}: could not locate the marks column.")
        rightmost = max(w.cx for w in numeric)
        mark = max(0.0, rightmost - 0.045), min(1.0, rightmost + 0.045)
        label, maximum = "Rightmost marks", None
    page.mark_candidates = candidates
    return Layout(roll, mark, top, bottom, label, maximum)


def _cell(words: list[Word], bounds: tuple[float, float], *, numeric: bool = False) -> tuple[str, float]:
    selected = sorted((w for w in words if bounds[0] < w.cx < bounds[1]), key=lambda w: w.cx)
    if numeric:
        text = "".join(w.text for w in selected)
    else:
        text = " ".join(w.text for w in selected)
    return text.strip(), min((w.confidence for w in selected), default=0.0)


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
        raw_roll, roll_score = _cell(words, layout.roll, numeric=True)
        raw_mark, mark_score = _cell(words, layout.mark, numeric=True)
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


def _fraction(text: str):
    match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)\s*/\s*([0-9]+(?:\.[0-9]+)?)", normalize(text))
    if not match:
        return None
    return Decimal(match[1]), Decimal(match[2])


def _absent(document: Document, text: str) -> bool:
    wanted = normalize(text).casefold()
    return bool(wanted) and wanted in {normalize(code).casefold() for code in document.absent_codes}


def _readable_mark(document: Document, text: str) -> bool:
    return bool(text) and (number(text) is not None or _absent(document, text)
                           or (document.allow_fractions and _fraction(text) is not None))


def validate(document: Document) -> None:
    counts = Counter(row.roll for row in document.records if valid_roll(row.roll))
    for row in document.records:
        row.issues = []
        if not valid_roll(row.roll):
            row.issues.append("Missing roll" if not row.roll else "Roll must contain digits only")
        elif counts[row.roll] > 1:
            row.issues.append("Duplicate roll")
        raw_mark = normalize(row.mark)
        value = number(raw_mark)
        fraction = _fraction(raw_mark) if document.allow_fractions else None
        if not raw_mark:
            row.issues.append("Missing mark")
        elif _absent(document, raw_mark):
            pass
        elif re.fullmatch(r"[-–—]+", raw_mark):
            row.issues.append("Missing mark")
        elif value is None and fraction is None:
            row.issues.append("Mark is not a number")
        elif fraction is not None:
            numerator, denominator = fraction
            maximum = document.max_mark if document.max_mark is not None else row.max_mark
            if denominator <= 0:
                row.issues.append("Fraction denominator must be positive")
            elif numerator > denominator:
                row.issues.append("Fraction exceeds its total")
            if maximum is not None and (numerator > Decimal(str(maximum)) or denominator > Decimal(str(maximum))):
                row.issues.append(f"Mark exceeds {maximum:g}")
        elif value < 0:
            row.issues.append("Negative mark")
        else:
            maximum = document.max_mark if document.max_mark is not None else row.max_mark
            if maximum is not None and value > Decimal(str(maximum)):
                row.issues.append(f"Mark exceeds {maximum:g}")
        if row.method == "Local OCR" and not row.reviewed:
            row.issues.append("Verify OCR reading")


def _crop_cell(image, x0: float, x1: float, y0: float, y1: float):
    width, height = image.size
    left = int(max(0.0, x0 - .006) * width)
    right = int(min(1.0, x1 + .006) * width)
    top = int(max(0.0, y0 - .004) * height)
    bottom = int(min(1.0, y1 + .004) * height)
    if right <= left or bottom <= top:
        return None
    crop = image.crop((left, top, right, bottom))
    return crop.resize((max(1, crop.width * 3), max(1, crop.height * 3)),
                       resample=Image.Resampling.LANCZOS)


def refine_low_confidence(document: Document, ocr=None, *, threshold: float = LOW_CONFIDENCE,
                          budget: int = 60) -> int:
    rows = [row for row in document.records if row.method == "Local OCR" and not row.reviewed
            and (row.confidence < threshold or any(issue.startswith(RETRY_ISSUES) for issue in row.issues))]
    if not rows:
        return 0
    if ocr is None:
        from .ocr import LocalOCR
        ocr = LocalOCR()
    changed = 0
    for row in rows:
        if budget <= 0:
            break
        page = document.pages[row.page - 1]
        layout = page.layout
        if layout is None:
            continue
        for field, bounds in (("roll", layout.roll), ("mark", layout.mark)):
            if budget <= 0:
                break
            crop = _crop_cell(page.image, bounds[0], bounds[1], row.box[1], row.box[3])
            if crop is None:
                continue
            budget -= 1
            try:
                words = ocr.recognize(crop)
            except Exception:
                continue
            if not words:
                continue
            text = "".join(word.text for word in sorted(words, key=lambda word: (word.cy, word.cx))).strip()
            score = sum(word.confidence for word in words) / len(words)
            current = getattr(row, field)
            valid = valid_roll(text) if field == "roll" else _readable_mark(document, text)
            current_valid = valid_roll(current) if field == "roll" else _readable_mark(document, current)
            if not text or not valid or text == current:
                continue
            if current_valid and not any(issue.startswith(RETRY_ISSUES) for issue in row.issues) \
                    and score < row.confidence + .08:
                continue
            setattr(row, field, normalize(text))
            row.confidence = max(row.confidence, score) if current_valid else score
            changed += 1
    return changed


def extract_document(document: Document, *, autodetect: bool = True, refine: bool = True,
                     ocr=None) -> Document:
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
    if refine and refine_low_confidence(document, ocr):
        validate(document)
    return document
