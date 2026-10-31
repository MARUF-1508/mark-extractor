import csv
from pathlib import Path

import pytest
from openpyxl import load_workbook

from result_automation.document import open_document
from result_automation.extract import extract_document, validate
from result_automation.storage import export_csv, export_xlsx, load_session, save_session

SAMPLE = Path(__file__).resolve().parents[1] / "examples" / "CSE 251_CT_marks.pdf"


@pytest.fixture
def document():
    return extract_document(open_document(SAMPLE))


def test_session_keeps_edits_original_values_and_layout(document, tmp_path):
    row = document.records[0]
    row.roll, row.mark, row.reviewed = "00328", "38.5", True
    document.max_mark = 40
    path = tmp_path / "session.json"
    save_session(document, path)
    restored = load_session(path)
    assert (restored.records[0].roll, restored.records[0].mark) == ("00328", "38.5")
    assert (restored.records[0].raw_roll, restored.records[0].raw_mark) == ("328", "39")
    assert restored.records[0].reviewed
    assert restored.pages[0].layout.label == "Total (40)"
    assert len(restored.pages[0].words) == len(document.pages[0].words)


def test_session_refuses_changed_source(document, tmp_path):
    source = tmp_path / "source.pdf"
    source.write_bytes(SAMPLE.read_bytes())
    document.source = source
    session = tmp_path / "review.json"
    save_session(document, session)
    source.write_bytes(source.read_bytes() + b"\n% changed")
    with pytest.raises(ValueError, match="changed"):
        load_session(session)


def test_session_refuses_source_changed_during_review(document, tmp_path):
    source = tmp_path / "source.pdf"
    source.write_bytes(SAMPLE.read_bytes() + b"\n% changed")
    document.source = source
    with pytest.raises(ValueError, match="changed while"):
        save_session(document, tmp_path / "review.json")


def test_csv_and_excel_keep_all_rows_and_review_status(document, tmp_path):
    document.records[0].roll = "00328"
    document.records[1].mark = ""
    validate(document)
    csv_path, xlsx_path = tmp_path / "results.csv", tmp_path / "results.xlsx"
    export_csv(document, csv_path)
    export_xlsx(document, xlsx_path)
    with csv_path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 54
    assert rows[0]["Roll"] == "00328"
    assert rows[1]["Issues"] == "Missing mark"
    workbook = load_workbook(xlsx_path)
    assert workbook["Results"]["A2"].value == "00328"
    assert workbook["Results"]["B3"].value is None
    assert workbook["Results"]["B4"].value == 36
    assert workbook["Results"]["D3"].value == "Needs review"
    assert workbook["Results"].max_row == 55
    assert "Source and review" in workbook.sheetnames


def test_export_does_not_create_formulas_from_ocr(document, tmp_path):
    document.records[0].roll = "=1+1"
    path = tmp_path / "results.xlsx"
    export_xlsx(document, path)
    workbook = load_workbook(path)
    assert workbook["Results"]["A2"].data_type == "s"
    assert workbook["Results"]["A2"].value == "'=1+1"
