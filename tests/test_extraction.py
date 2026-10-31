from pathlib import Path

from PIL import Image, ImageDraw

from result_automation.extract import extract_document, extract_page, normalize, validate
from result_automation.models import Document, Layout, Page, Record, Word


def table_page(rolls=("001", "002", "003"), marks=("12.5", "", "0")):
    image = Image.new("RGB", (1000, 800), "white")
    draw = ImageDraw.Draw(image)
    for x in (50, 200, 800, 950):
        draw.line((x, 160, x, 440), fill="black", width=2)
    for y in (160, 200, 280, 360, 440):
        draw.line((50, y, 950, y), fill="black", width=2)
    words = [Word("Roll", (.08, .21, .17, .23)), Word("Marks(20)", (.82, .21, .94, .23))]
    for roll, mark, center in zip(rolls, marks, (.3, .4, .5)):
        if roll:
            words.append(Word(roll, (.09, center - .01, .15, center + .01)))
        if mark:
            words.append(Word(mark, (.85, center - .01, .90, center + .01)))
        words.append(Word("Student", (.3, center - .01, .5, center + .01)))
    return Page(1, image, words, "PDF text", Layout((.05, .2), (.8, .95), .25, .55, "Marks(20)", 20))


def test_blank_mark_does_not_shift_rows():
    doc = extract_document(Document(Path("test.pdf"), [table_page()]), autodetect=False)
    assert [(r.roll, r.mark) for r in doc.records] == [("001", "12.5"), ("002", ""), ("003", "0")]
    assert doc.records[1].issues == ["Missing mark"]
    assert not doc.records[2].issues


def test_missing_roll_is_kept_in_a_ruled_row():
    doc = extract_document(Document(Path("test.pdf"), [table_page(("001", "", "003"), ("5", "6", "7"))]), autodetect=False)
    assert len(doc.records) == 3
    assert doc.records[1].mark == "6"
    assert "Missing roll" in doc.records[1].issues


def test_duplicate_range_and_review_are_independent():
    page = table_page(("001", "001", "003"), ("21", "-1", "3"))
    page.method = "Local OCR"
    doc = extract_document(Document(Path("test.pdf"), [page]), autodetect=False)
    assert doc.records[0].issues == ["Duplicate roll", "Mark exceeds 20", "Verify OCR reading"]
    doc.records[0].reviewed = True
    validate(doc)
    assert doc.records[0].issues == ["Duplicate roll", "Mark exceeds 20"]
    assert "Negative mark" in doc.records[1].issues
    doc.max_mark = 30
    validate(doc)
    assert doc.records[0].issues == ["Duplicate roll"]


def test_bengali_normalization_preserves_leading_zeros():
    assert normalize(" ০০১ ") == "001"
    doc = extract_document(Document(Path("test.pdf"), [table_page(("০০১", "০০২", "০০৩"), ("১২.৫", "০", "৭"))]), autodetect=False)
    assert [(r.roll, r.mark) for r in doc.records] == [("001", "12.5"), ("002", "0"), ("003", "7")]
    assert all(not row.issues for row in doc.records)


def test_unruled_row_alignment_and_missing_mark():
    page = table_page()
    page.image = Image.new("RGB", (1000, 800), "white")
    rows = extract_page(page)
    assert [(r.roll, r.mark) for r in rows] == [("001", "12.5"), ("002", ""), ("003", "0")]


def test_ambiguous_ocr_is_not_silently_fixed():
    doc = extract_document(Document(Path("test.pdf"), [table_page(("O01", "002", "003"), ("1O", "AB", "---"))]), autodetect=False)
    assert doc.records[0].roll == "O01"
    assert doc.records[0].issues == ["Roll must contain digits only", "Mark is not a number"]
    assert doc.records[2].issues == ["Missing mark"]
