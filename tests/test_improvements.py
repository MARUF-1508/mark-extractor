from __future__ import annotations

import hashlib
from pathlib import Path

from PIL import Image, ImageDraw

from result_automation.extract import detect_layout, extract_document, refine_low_confidence, validate
from result_automation.models import Document, Layout, MarkCandidate, Page, Record, Word
from result_automation.preprocess import deskew, preprocess_image
from result_automation.storage import load_session, save_session


def table_page(rolls=("001", "002", "003"), marks=("12.5", "", "0"), *, method="PDF text",
               roll_confidence=1.0, mark_confidence=1.0):
    image = Image.new("RGB", (1000, 800), "white")
    draw = ImageDraw.Draw(image)
    for x in (50, 200, 800, 950):
        draw.line((x, 160, x, 440), fill="black", width=2)
    for y in (160, 200, 280, 360, 440):
        draw.line((50, y, 950, y), fill="black", width=2)
    words = [Word("Roll", (.08, .21, .17, .23)), Word("Marks(20)", (.82, .21, .94, .23))]
    for roll, mark, center in zip(rolls, marks, (.3, .4, .5)):
        if roll:
            words.append(Word(roll, (.09, center - .01, .15, center + .01), roll_confidence))
        if mark:
            words.append(Word(mark, (.85, center - .01, .90, center + .01), mark_confidence))
        words.append(Word("Student", (.3, center - .01, .5, center + .01)))
    return Page(1, image, words, method, Layout((.05, .2), (.8, .95), .25, .55, "Marks(20)", 20))


def test_detect_layout_offers_mark_column_candidates():
    page = table_page()
    page.layout = None
    layout = detect_layout(page)
    assert layout.label == "Marks(20)"
    assert layout.max_mark == 20
    assert page.mark_candidates
    assert all(isinstance(candidate, MarkCandidate) for candidate in page.mark_candidates)
    assert page.mark_candidates[0].id.startswith("mark-")
    assert page.mark_candidates[0].left <= layout.mark[0] < layout.mark[1] <= page.mark_candidates[0].right


def test_absent_codes_and_fractions_are_validated():
    page = table_page(marks=("12/15", "ab", "21"))
    document = Document(Path("test.pdf"), [page], max_mark=20, absent_codes=["AB"], allow_fractions=True)
    extract_document(document, autodetect=False)
    assert document.records[0].issues == []
    assert document.records[1].issues == []
    assert document.records[2].issues == ["Mark exceeds 20"]
    document.allow_fractions = False
    validate(document)
    assert document.records[0].issues == ["Mark is not a number"]
    document.allow_fractions = True
    document.records[0].mark = "15/12"
    validate(document)
    assert "Fraction exceeds its total" in document.records[0].issues


def test_low_confidence_mark_is_repaired_without_losing_the_original():
    page = table_page(marks=("1O",), rolls=("001",), method="Local OCR", mark_confidence=.3)
    document = Document(Path("test.pdf"), [page])
    extract_document(document, autodetect=False, refine=False)
    row = document.records[0]
    assert (row.mark, row.confidence) == ("1O", .3)
    assert "Mark is not a number" in row.issues

    class FakeOCR:
        def __init__(self):
            self.values = iter(["001", "10"])

        def recognize(self, crop):
            return [Word(next(self.values), (0, 0, 1, 1), .95)]

    assert refine_low_confidence(document, FakeOCR()) == 1
    assert (row.mark, row.raw_mark, row.confidence) == ("10", "1O", .95)
    validate(document)
    assert "Mark is not a number" not in row.issues
    assert "Verify OCR reading" in row.issues


def test_preprocess_deskews_a_rotated_scan():
    image = Image.new("RGB", (1200, 800), "white")
    draw = ImageDraw.Draw(image)
    for y in range(200, 600, 40):
        draw.line((100, y, 1100, y), fill="black", width=3)
    rotated = image.rotate(2, expand=True, fillcolor="white", resample=Image.Resampling.BICUBIC)
    corrected, angle = deskew(rotated)
    assert 1.2 < angle < 3.0
    assert abs(deskew(corrected)[1]) < .6
    processed, notes = preprocess_image(rotated)
    assert processed.size == rotated.size
    assert any("deskewed" in note for note in notes)


def test_session_round_trip_keeps_candidates_and_validation_settings(tmp_path):
    source = tmp_path / "scan.png"
    Image.new("RGB", (200, 100), "white").save(source)
    page = Page(1, Image.new("RGB", (200, 100), "white"), [Word("001", (.1, .1, .2, .2))],
                "Local OCR", Layout((.05, .2), (.8, .95), .25, .55, "Marks(20)", 20, False),
                [MarkCandidate("mark-1", "Marks(20)", .8, .95, .25, .55, 20, 2.0)],
                ["deskewed 1.0°"])
    record = Record("p1-r1", 1, "001", "12.5", "001", "12.5", (.05, .25, .95, .35),
                    "Local OCR", .95, 20, True)
    document = Document(source, [page], [record], 20, ["No rows found on page 2"],
                        hashlib.sha256(source.read_bytes()).hexdigest(), absent_codes=["AB"],
                        allow_fractions=False)
    session = tmp_path / "review.json"
    save_session(document, session)
    loaded = load_session(session)
    assert loaded.absent_codes == ["AB"]
    assert loaded.allow_fractions is False
    assert loaded.pages[0].notes == ["deskewed 1.0°"]
    assert loaded.pages[0].mark_candidates == page.mark_candidates
    assert tuple(loaded.pages[0].layout.roll) == page.layout.roll
    assert tuple(loaded.pages[0].layout.mark) == page.layout.mark


def test_validation_issue_triggers_a_targeted_reread():
    page = table_page(marks=("75",), rolls=("003",), method="Local OCR", mark_confidence=.95)
    document = Document(Path("test.pdf"), [page], max_mark=20)
    extract_document(document, autodetect=False, refine=False)
    row = document.records[0]
    assert row.issues == ["Mark exceeds 20", "Verify OCR reading"]

    class FakeOCR:
        def __init__(self):
            self.values = iter(["003", "7.5"])

        def recognize(self, crop):
            return [Word(next(self.values), (0, 0, 1, 1), .95)]

    assert refine_low_confidence(document, FakeOCR()) == 1
    assert row.mark == "7.5"
    validate(document)
    assert row.issues == ["Verify OCR reading"]
