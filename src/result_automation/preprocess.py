"""Local image cleanup for scans and photos before OCR."""
from __future__ import annotations

import math
from statistics import median

import cv2
import numpy as np
from PIL import Image


def _array(image: Image.Image) -> np.ndarray:
    return np.asarray(image.convert("RGB"))


def _image(array: np.ndarray) -> Image.Image:
    return Image.fromarray(array, "RGB")


def _projection_angle(gray: np.ndarray) -> float:
    height, width = gray.shape
    scale = min(1.0, 900 / max(height, width))
    if scale < 1:
        gray = cv2.resize(gray, (max(1, int(width * scale)), max(1, int(height * scale))),
                          interpolation=cv2.INTER_AREA)
    binary = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                   cv2.THRESH_BINARY_INV, 31, 15)
    height, width = binary.shape
    best_angle, best_score = 0.0, -1.0
    for angle in np.arange(-6.0, 6.01, 0.5):
        matrix = cv2.getRotationMatrix2D((width / 2, height / 2), float(angle), 1.0)
        rotated = cv2.warpAffine(binary, matrix, (width, height), flags=cv2.INTER_NEAREST,
                                 borderMode=cv2.BORDER_CONSTANT, borderValue=0)
        profile = rotated.sum(axis=1, dtype=np.float64)
        score = float(np.var(profile))
        if score > best_score:
            best_angle, best_score = float(angle), score
    return best_angle


def estimate_skew(image: Image.Image) -> float:
    array = _array(image)
    gray = cv2.cvtColor(array, cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    height, width = gray.shape
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=80,
                            minLineLength=max(40, width // 4), maxLineGap=20)
    angles = []
    if lines is not None:
        for x0, y0, x1, y1 in np.asarray(lines).reshape(-1, 4):
            dx, dy = int(x1) - int(x0), int(y1) - int(y0)
            if not dx or abs(dx) < abs(dy) * 3:
                continue
            angle = math.degrees(math.atan2(dy, dx))
            if abs(angle) <= 12:
                angles.append(angle)
    if len(angles) >= 5:
        correction = -median(angles)
    else:
        correction = -_projection_angle(gray)
    return 0.0 if abs(correction) < 0.35 else max(-12.0, min(12.0, correction))


def deskew(image: Image.Image) -> tuple[Image.Image, float]:
    angle = estimate_skew(image)
    if not angle:
        return image, 0.0
    array = _array(image)
    height, width = array.shape[:2]
    matrix = cv2.getRotationMatrix2D((width / 2, height / 2), -angle, 1.0)
    rotated = cv2.warpAffine(array, matrix, (width, height), flags=cv2.INTER_CUBIC,
                             borderMode=cv2.BORDER_CONSTANT, borderValue=(255, 255, 255))
    return _image(rotated), angle


def _order_points(points: np.ndarray) -> np.ndarray:
    ordered = np.zeros((4, 2), dtype=np.float32)
    sums, differences = points.sum(axis=1), np.diff(points, axis=1).ravel()
    ordered[0] = points[np.argmin(sums)]
    ordered[2] = points[np.argmax(sums)]
    ordered[1] = points[np.argmin(differences)]
    ordered[3] = points[np.argmax(differences)]
    return ordered


def correct_perspective(image: Image.Image) -> tuple[Image.Image, bool]:
    array = _array(image)
    gray = cv2.cvtColor(array, cv2.COLOR_RGB2GRAY)
    height, width = gray.shape
    if float(np.mean(gray > 242)) > .84:
        return image, False
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 40, 120)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates = sorted(contours, key=cv2.contourArea, reverse=True)[:5]
    for contour in candidates:
        area = cv2.contourArea(contour)
        if area < width * height * .3:
            continue
        perimeter = cv2.arcLength(contour, True)
        corners = cv2.approxPolyDP(contour, .02 * perimeter, True)
        if len(corners) != 4 or not cv2.isContourConvex(corners):
            continue
        points = _order_points(corners.reshape(4, 2).astype(np.float32))
        rect = cv2.minAreaRect(corners.reshape(4, 2))
        (_, _), (rect_w, rect_h), _ = rect
        if rect_w < 10 or rect_h < 10:
            continue
        if area / max(1.0, rect_w * rect_h) > .985:
            continue
        top_left, top_right, bottom_right, bottom_left = points
        target_width = int(max(np.linalg.norm(bottom_right - bottom_left),
                               np.linalg.norm(top_right - top_left)))
        target_height = int(max(np.linalg.norm(top_right - bottom_right),
                                np.linalg.norm(top_left - bottom_left)))
        if target_width < width * .35 or target_height < height * .35:
            continue
        destination = np.array([[0, 0], [target_width - 1, 0],
                                [target_width - 1, target_height - 1], [0, target_height - 1]],
                               dtype=np.float32)
        matrix = cv2.getPerspectiveTransform(points, destination)
        warped = cv2.warpPerspective(array, matrix, (target_width, target_height),
                                     flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_CONSTANT,
                                     borderValue=(255, 255, 255))
        return _image(warped), True
    return image, False


def normalize_illumination(image: Image.Image) -> tuple[Image.Image, bool]:
    array = _array(image)
    gray = cv2.cvtColor(array, cv2.COLOR_RGB2GRAY)
    small = cv2.resize(gray, (32, 32), interpolation=cv2.INTER_AREA)
    background = cv2.GaussianBlur(small, (0, 0), 7)
    if float(np.std(background.astype(np.float32))) < 3.5:
        return image, False
    lab = cv2.cvtColor(array, cv2.COLOR_RGB2LAB)
    lightness, a_channel, b_channel = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    lightness = clahe.apply(lightness)
    return _image(cv2.cvtColor(cv2.merge((lightness, a_channel, b_channel)), cv2.COLOR_LAB2RGB)), True


def preprocess_image(image: Image.Image, *, perspective: bool = False) -> tuple[Image.Image, list[str]]:
    notes: list[str] = []
    processed = image.convert("RGB")
    if perspective:
        processed, changed = correct_perspective(processed)
        if changed:
            notes.append("perspective corrected")
    processed, angle = deskew(processed)
    if angle:
        notes.append(f"deskewed {abs(angle):.1f}°")
    processed, changed = normalize_illumination(processed)
    if changed:
        notes.append("lighting normalized")
    return processed, notes


def orientation_score(words) -> float:
    return sum(len(word.text.strip()) * max(0.1, word.confidence) for word in words)


def orient_image(image: Image.Image, recognize) -> tuple[Image.Image, float]:
    sample = image.copy()
    sample.thumbnail((1400, 1400), Image.Resampling.LANCZOS)
    best_angle, best_score = 0, -1.0
    for angle in (0, 90, 180, 270):
        candidate = sample if angle == 0 else sample.rotate(angle, expand=True, fillcolor="white")
        try:
            words = recognize(candidate)
        except Exception:
            words = []
        score = orientation_score(words)
        if score > best_score:
            best_angle, best_score = angle, score
    if best_angle == 0:
        return image, 0.0
    return image.rotate(best_angle, expand=True, fillcolor="white"), float(best_angle)
