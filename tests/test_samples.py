from pathlib import Path

import pytest

from result_automation.document import open_document
from result_automation.extract import extract_document
from sample_truth import SAMPLES

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


@pytest.mark.parametrize("filename,expected,counts,label,maximum", SAMPLES)
def test_every_pair_in_samples(filename, expected, counts, label, maximum):
    doc = extract_document(open_document(EXAMPLES / filename))
    assert [(r.roll, r.mark) for r in doc.records] == expected
    assert [sum(r.page == p.number for r in doc.records) for p in doc.pages] == counts
    assert all(p.layout.label == label and p.layout.max_mark == maximum for p in doc.pages)
    assert all(r.method == "PDF text" and not r.issues for r in doc.records)
    assert not doc.warnings


def test_rotated_headers_and_leftmost_roll_in_latest_pdf():
    path = EXAMPLES.parent / "test_sources" / "CSE-305-TUTORIAL-MARKS.pdf"
    if not path.is_file():
        pytest.skip("Optional user-supplied tutorial PDF is not present")
    doc = extract_document(open_document(path))
    assert len(doc.records) == 52
    assert (doc.records[0].roll, doc.records[0].mark) == ("328", "35")
    assert (doc.records[-1].roll, doc.records[-1].mark) == ("2052", "34")
    assert doc.pages[0].layout.label == "TOTAL (40 Marks)"
    assert doc.pages[0].layout.max_mark == 40
    assert all(not row.issues for row in doc.records)


@pytest.mark.ocr
@pytest.mark.parametrize("filename,expected,counts,label,maximum", SAMPLES)
def test_rasterized_samples_offline(filename, expected, counts, label, maximum, monkeypatch):
    import socket

    def blocked(*args, **kwargs):
        raise AssertionError("Network is disabled during the OCR test")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    doc = extract_document(open_document(EXAMPLES / filename, force_ocr=True))
    assert [(r.roll, r.mark) for r in doc.records] == expected
    assert all(r.method == "Local OCR" and "Verify OCR reading" in r.issues for r in doc.records)
    assert not doc.warnings


@pytest.mark.ocr
def test_png_image_input(tmp_path):
    source = open_document(EXAMPLES / "OOAD_tutorial.pdf", read_words=False)
    image_path = tmp_path / "marksheet.png"
    source.pages[0].image.save(image_path)
    document = extract_document(open_document(image_path))
    assert [(r.roll, r.mark) for r in document.records] == SAMPLES[1][1][:27]
