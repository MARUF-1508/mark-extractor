from __future__ import annotations

import csv
import io
from copy import deepcopy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from result_automation.columns import apply_export_plan, discover_columns, table_preview
from result_automation.document import open_document
from result_automation.extract import extract_document
from result_automation.models import ExportColumn
from result_automation.storage import export_xlsx, load_session, save_session
from result_automation.web import create_app
from test_web import ready, upload

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def document():
    return extract_document(open_document(ROOT / "examples" / "CSE 251_CT_marks.pdf"))


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / "data")) as client:
        yield client


def test_discover_real_columns_names_and_blank_cell_alignment(document):
    columns = discover_columns(document)
    assert len(columns) == 11
    by_id = {c.id: c for c in columns}
    assert by_id["source-2"].name == "Name of the Student"
    assert by_id["source-4"].name == "T-1 (30)"
    assert by_id["source-4"].kind == "number"
    preview = table_preview(document, [by_id["source-2"],by_id["source-4"]])
    assert preview["rows"][0]["values"] == {"source-2":"Dipta Kumar Das","source-4":"29"}
    assert preview["rows"][17]["values"]["source-4"] == ""
    assert preview["rows"][18]["values"]["source-4"] == "24"
    assert preview["rows"][-1]["values"]["source-2"] == "Nandini Howlader"


def test_ordered_named_excel_and_session_keep_values_and_originals(document,tmp_path):
    columns = {c.id:c for c in discover_columns(document)}
    selected = [columns["source-2"],columns["roll"],columns["marks"],columns["source-4"]]
    for column,name in zip(selected,["Student","Student ID","Final mark","Quiz 1"]):
        column.name = name
    apply_export_plan(document,selected,{"p1-r1":{"roll":"00328","marks":"38.25","source-2":"Dipta K. Das"}})
    path = tmp_path / "review.json"
    save_session(document,path)
    restored = load_session(path)
    assert [c.name for c in restored.export_columns] == ["Student","Student ID","Final mark","Quiz 1"]
    assert restored.records[0].roll == "00328"
    assert restored.records[0].raw_roll == "328"
    output = tmp_path / "preview.xlsx"
    export_xlsx(restored,output)
    workbook = load_workbook(output)
    sheet = workbook["Results"]
    assert list(next(sheet.values)) == ["Student","Student ID","Final mark","Quiz 1"]
    assert list(sheet.values)[1] == ("Dipta K. Das","00328",38.25,29)
    assert sheet["B2"].data_type == "s"
    assert sheet.max_row == 55 and sheet.max_column == 4
    assert sheet.cell(19,4).value is None
    assert sheet.cell(20,4).value == 24
    audit = list(workbook["Source and review"].values)
    assert any("Dipta Kumar Das" in row for row in audit)
    assert any("328" in row for row in audit)


def test_preview_is_read_only_and_save_exports_selected_order(client):
    doc = upload(client)
    base = f"/api/documents/{doc['id']}"
    options = client.get(base + "/columns").json()
    candidates = {c["id"]:c for c in options["candidates"]}
    selected = [candidates["source-2"],candidates["roll"],candidates["source-4"]]
    for col,name in zip(selected,["Student","Roll number","Test one"]):
        col["name"] = name
    plan = {"version":doc["version"],"columns":selected,"overrides":{"p1-r1":{"roll":"00328","source-4":"0"}}}
    preview = client.post(base+"/columns/preview",json=plan)
    assert preview.status_code == 200, preview.text
    assert preview.json()["rows"][0]["values"]["roll"] == "00328"
    unchanged = client.get(base).json()
    assert unchanged["version"] == doc["version"] and unchanged["records"][0]["roll"] == "328"
    response = client.put(base+"/columns",json=plan)
    assert response.status_code == 200,response.text
    saved = response.json()
    assert [c["name"] for c in saved["export_columns"]] == ["Student","Roll number","Test one"]
    assert saved["records"][0]["roll"] == "00328"
    assert client.put(base+"/columns",json=plan).status_code == 409
    book = load_workbook(io.BytesIO(client.get(base+"/export/xlsx").content))
    assert list(book["Results"].values)[0] == ("Student","Roll number","Test one")
    assert list(book["Results"].values)[1] == ("Dipta Kumar Das","00328",0)
    csv_rows = list(csv.reader(io.StringIO(client.get(base+"/export/csv").content.decode("utf-8-sig"))))
    assert csv_rows[0] == ["Student","Roll number","Test one"]
    assert csv_rows[1] == ["Dipta Kumar Das","00328","0"]


def test_single_column_export_and_literal_formula_text(client):
    doc = upload(client)
    base = f"/api/documents/{doc['id']}"
    column = next(c for c in client.get(base+"/columns").json()["candidates"] if c["id"] == "source-2")
    column["name"] = "=Student name"
    plan = {"version":doc["version"],"columns":[column],"overrides":{"p1-r1":{column["id"]:"=1+1"}}}
    assert client.put(base+"/columns",json=plan).status_code == 200
    book = load_workbook(io.BytesIO(client.get(base+"/export/xlsx").content))
    sheet = book["Results"]
    assert sheet.max_column == 1 and sheet.max_row == 55
    assert sheet["A1"].value == "=Student name" and sheet["A1"].data_type == "s"
    assert sheet["A2"].value == "=1+1" and sheet["A2"].data_type == "s"


def test_custom_region_scope_and_export_settings_survive_restart(tmp_path):
    directory = tmp_path / "data"
    with TestClient(create_app(directory)) as client:
        doc = upload(client,"OOAD_tutorial.pdf")
        base = f"/api/documents/{doc['id']}"
        candidate = next(c for c in client.get(base+"/columns").json()["candidates"] if c["id"] == "source-3")
        candidate.update(id="custom-report",name="Report score")
        # A page-specific region must leave other pages empty, not borrow values.
        candidate["regions"] = {"1":candidate["regions"]["1"]}
        plan = {"version":doc["version"],"columns":[candidate],"overrides":{}}
        assert client.put(base+"/columns",json=plan).status_code == 200
    with TestClient(create_app(directory)) as client:
        restored = client.get(base+"/columns").json()
        assert restored["preview"]["columns"][0]["name"] == "Report score"
        assert restored["preview"]["rows"][0]["values"]["custom-report"] == "8.5"
        assert restored["preview"]["rows"][27]["values"]["custom-report"] == ""
        book = load_workbook(io.BytesIO(client.get(base+"/export/xlsx").content))
        assert book["Results"].max_row == 53  # Preserve all trailing blank rows.
        assert book["Results"]["A53"].value is None


def test_reextract_clears_stale_custom_cell_overrides(client):
    doc = upload(client)
    base = f"/api/documents/{doc['id']}"
    column = next(c for c in client.get(base+"/columns").json()["candidates"] if c["id"] == "source-4")
    saved = client.put(base+"/columns",json={"version":doc["version"],"columns":[column],"overrides":{"p1-r1":{column["id"]:"1"},"p2-r1":{column["id"]:"2"}}}).json()
    doc = client.post(base+"/reextract",json={"version":saved["version"],"page":1,"scope":"page","layout":doc["pages"][0]["layout"]}).json()
    preview = client.get(base+"/columns").json()
    assert preview["preview"]["rows"][0]["values"][column["id"]] == "29"
    assert preview["overrides"]["p2-r1"][column["id"]] == "2"
    assert "p1-r1" not in preview["overrides"]


def test_manual_rows_do_not_read_an_entire_source_column(client):
    doc = upload(client)
    base = f"/api/documents/{doc['id']}"
    column = next(c for c in client.get(base+"/columns").json()["candidates"] if c["id"] == "source-2")
    doc = client.post(base+"/rows",json={"version":doc["version"],"page":1,"roll":"0001","mark":"0"}).json()
    preview = client.post(base+"/columns/preview",json={"version":doc["version"],"columns":[column],"overrides":{}}).json()
    assert preview["rows"][-1]["values"][column["id"]] == ""


def test_export_rejects_a_version_newer_than_the_preview(client):
    doc = upload(client)
    base = f"/api/documents/{doc['id']}"
    client.patch(base+"/rows/p1-r1",json={"version":doc["version"],"roll":"328","mark":"38"})
    response = client.get(base+f"/export/xlsx?version={doc['version']}")
    assert response.status_code == 409
    assert "another tab" in response.json()["detail"]


@pytest.mark.parametrize("change",["empty","duplicate_name","duplicate_id","bad_region","unknown_row","unknown_cell"])
def test_invalid_export_plans_are_rejected(client,change):
    doc = upload(client)
    base = f"/api/documents/{doc['id']}"
    options = client.get(base+"/columns").json()
    plan = {"version":doc["version"],"columns":deepcopy(options["preview"]["columns"]),"overrides":{}}
    if change == "empty": plan["columns"] = []
    elif change == "duplicate_name": plan["columns"][1]["name"] = " roll "
    elif change == "duplicate_id": plan["columns"][1]["id"] = "roll"
    elif change == "bad_region": plan["columns"][0]["regions"]["1"] = [-.1,0,.2,1]
    elif change == "unknown_row": plan["overrides"] = {"missing-row":{"roll":"12"}}
    else: plan["overrides"] = {"p1-r1":{"not-selected":"12"}}
    response = client.put(base+"/columns",json=plan)
    assert response.status_code == 422,response.text
    assert client.get(base).json()["export_columns"] is None
