from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from PIL import Image

Box = tuple[float, float, float, float]
Progress = Callable[[str], None]


@dataclass
class Word:
    text: str
    box: Box
    confidence: float = 1.0

    @property
    def cx(self) -> float:
        return (self.box[0] + self.box[2]) / 2

    @property
    def cy(self) -> float:
        return (self.box[1] + self.box[3]) / 2


@dataclass
class Layout:
    roll: tuple[float, float]
    mark: tuple[float, float]
    top: float = 0.0
    bottom: float = 1.0
    label: str = "Rightmost marks"
    max_mark: float | None = None
    automatic: bool = True


@dataclass
class MarkCandidate:
    id: str
    label: str
    left: float
    right: float
    top: float
    bottom: float
    max_mark: float | None = None
    score: float = 0.0


@dataclass
class Page:
    number: int
    image: Image.Image
    words: list[Word]
    method: str
    layout: Layout | None = None
    mark_candidates: list[MarkCandidate] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class Record:
    id: str
    page: int
    roll: str
    mark: str
    raw_roll: str
    raw_mark: str
    box: Box
    method: str
    confidence: float
    max_mark: float | None = None
    reviewed: bool = False
    issues: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        return "Needs review" if self.issues else "Reviewed" if self.reviewed else "Ready"


@dataclass
class ExportColumn:
    id: str
    name: str
    kind: str = "text"
    source: str = "region"
    regions: dict[str, Box] = field(default_factory=dict)


@dataclass
class Document:
    source: Path
    pages: list[Page]
    records: list[Record] = field(default_factory=list)
    max_mark: float | None = None
    warnings: list[str] = field(default_factory=list)
    source_sha256: str = ""
    export_columns: list[ExportColumn] | None = None
    export_overrides: dict[str, dict[str, str]] = field(default_factory=dict)
    absent_codes: list[str] = field(default_factory=list)
    allow_fractions: bool = True


class Cancelled(Exception):
    """Raised between pages when the user cancels a job."""
