from __future__ import annotations

import csv
import io
import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from result_automation.web import create_app
from result_automation.web_store import JobStore, atomic_json
from sample_truth import SAMPLES

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / "data")) as client:
        yield client


def ready(client, job_id):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        response = client.get(f"/api/documents/{job_id}")
        assert response.status_code == 200
        doc = response.json()
        if doc["status"] in {"ready", "error", "cancelled"}:
            return doc
        time.sleep(.02)
    pytest.fail("Extraction did not finish")


def upload(client, filename="CSE 251_CT_marks.pdf"):
    path = ROOT / "examples" / filename
    response = client.post("/api/documents", files={"file": (filename, path.read_bytes(), "application/pdf")})
    assert response.status_code == 202, response.text
    doc = ready(client, response.json()["id"])
    assert doc["status"] == "ready", doc
    return doc


@pytest.mark.parametrize("filename,expected,counts,label,maximum", SAMPLES)
def test_upload_pairs_pages_and_real_excel_download(client, filename, expected, counts, label, maximum):
    doc = upload(client, filename)
    assert [(r["roll"],r["mark"]) for r in doc["records"]] == expected
    assert doc["row_count"] == len(expected)
    assert doc["review_count"] == 0
    assert [sum(r["page"] == p["number"] for r in doc["records"]) for p in doc["pages"]] == counts
    assert all(page["layout"]["label"] == label for page in doc["pages"])
    assert client.get(doc["pages"][0]["image_url"]).content.startswith(b"\x89PNG")
    response = client.get(f"/api/documents/{doc['id']}/export/xlsx")
    assert response.status_code == 200
    assert "spreadsheetml" in response.headers["content-type"]
    assert ".results.xlsx" in response.headers["content-disposition"]
    book = load_workbook(io.BytesIO(response.content))
    assert book["Results"].max_row == len(expected) + 1
    assert book["Results"]["A2"].value == expected[0][0]
    assert book["Results"]["B2"].value == float(expected[0][1])
    assert "Source and review" in book.sheetnames
    assert not list((client.app.state.store.root / ".exports").glob("*.xlsx"))


def test_row_edit_conflict_raw_values_and_csv(client):
    doc = upload(client)
    url = f"/api/documents/{doc['id']}"
    edit = {"version": doc["version"], "roll":"00328", "mark":"38.25", "reviewed":True}
    response = client.patch(url + "/rows/p1-r1", json=edit)
    assert response.status_code == 200
    changed = response.json()
    row = changed["records"][0]
    assert (row["roll"], row["mark"], row["raw_roll"], row["raw_mark"],row["status"]) == ("00328","38.25","328","39","Reviewed")
    assert changed["verified_count"] == 1
    assert client.patch(url + "/rows/p1-r1", json=edit).status_code == 409
    exported = client.get(url + "/export/csv")
    rows = list(csv.DictReader(io.StringIO(exported.content.decode("utf-8-sig"))))
    assert len(rows) == 54 and rows[0]["Roll"] == "00328" and rows[0]["Marks"] == "38.25"
    assert "source" not in changed and str(client.app.state.store.root) not in json.dumps(changed)


def test_add_delete_rows_settings_and_validation(client):
    doc = upload(client)
    url = f"/api/documents/{doc['id']}"
    response = client.post(url + "/rows", json={"version":doc["version"], "page":1,"roll":"328","mark":"","reviewed":True})
    assert response.status_code == 201
    doc = response.json()
    assert doc["row_count"] == 55
    assert "Duplicate roll" in doc["records"][0]["issues"]
    assert doc["records"][-1]["issues"] == ["Duplicate roll", "Missing mark"]
    row_id = doc["records"][-1]["id"]
    response = client.request("DELETE", url + "/rows/" + row_id, json={"version":doc["version"]})
    doc = response.json()
    assert response.status_code == 200 and doc["row_count"] == 54 and doc["review_count"] == 0
    response = client.patch(url + "/settings", json={"version":doc["version"],"max_mark":35})
    doc = response.json()
    assert doc["review_count"] > 0
    assert client.patch(url + "/settings", json={"version":doc["version"],"max_mark":-5}).status_code == 422
    doc = client.patch(url + "/settings", json={"version":doc["version"],"max_mark":None}).json()
    assert doc["review_count"] == 0


def test_reextract_page_and_auto_reset(client):
    doc = upload(client)
    url = f"/api/documents/{doc['id']}"
    # The penultimate column is Avg; select it without changing row geometry.
    layout = doc["pages"][0]["layout"]
    layout.update(mark=[.79,.83],label="Custom marks column",max_mark=None,automatic=False)
    response = client.post(url + "/reextract",json={"version":doc["version"],"page":1,"scope":"page","layout":layout})
    assert response.status_code == 200, response.text
    doc = response.json()
    assert doc["records"][0]["mark"] == "29"
    assert doc["row_count"] == 54
    response = client.post(url + "/reextract",json={"version":doc["version"],"page":1,"scope":"auto"})
    doc = response.json()
    assert doc["records"][0]["mark"] == "39"
    bad = {**layout, "roll":[.8,.9]}
    assert client.post(url + "/reextract",json={"version":doc["version"],"page":1,"layout":bad}).status_code == 422


def test_review_survives_backend_restart(tmp_path):
    path = tmp_path / "data"
    with TestClient(create_app(path)) as client:
        doc = upload(client)
        url = f"/api/documents/{doc['id']}"
        response = client.patch(url + "/rows/p1-r1",json={"version":doc["version"],"roll":"00328","mark":"0","reviewed":True})
        version = response.json()["version"]
    with TestClient(create_app(path)) as client:
        restored = client.get(url).json()
        assert restored["version"] == version
        assert restored["records"][0]["roll"] == "00328"
        assert restored["records"][0]["mark"] == "0"
        assert restored["records"][0]["reviewed"]
        assert len(client.get("/api/documents").json()) == 1


def test_reject_bad_uploads_and_report_broken_pdf(client):
    assert client.post("/api/documents",files={"file":("program.exe",b"abc")}).status_code == 415
    assert client.post("/api/documents",files={"file":("empty.pdf",b"")}).status_code == 400
    response = client.post("/api/documents",files={"file":("broken.pdf",b"not a pdf")})
    doc = ready(client,response.json()["id"])
    assert doc["status"] == "error" and doc["error"]
    assert client.get(f"/api/documents/{doc['id']}/export/xlsx").status_code == 409
    assert client.delete(f"/api/documents/{doc['id']}").status_code == 204
    assert client.get(f"/api/documents/{doc['id']}").status_code == 404


def test_loopback_request_guards(client):
    assert client.get("/api/health").status_code == 200
    assert client.post("/api/examples/cse251",headers={"Origin":"https://another-site.test"}).status_code == 403
    assert client.get("/api/documents",headers={"Host":"attacker.test"}).status_code == 400
    assert client.get("/api/documents/not-an-id").status_code == 404
    assert client.get("/api/documents/" + "a"*32).status_code == 404
    assert client.get("/static/../../pyproject.toml").status_code == 404


def test_interrupted_job_is_recoverable_on_restart(tmp_path):
    store = JobStore(tmp_path)
    job_id, _ = store.reserve("test.pdf", False)
    store.update_meta(job_id,status="processing")
    store.close()
    recovered = JobStore(tmp_path)
    try:
        assert recovered.meta(job_id)["status"] == "error"
        assert "server stopped" in recovered.meta(job_id)["error"]
    finally:
        recovered.close()


def test_page_limits_are_enforced_before_loading_all_pages(monkeypatch):
    from result_automation.document import open_document
    with pytest.raises(ValueError, match="page limit"):
        open_document(ROOT / "examples" / "CSE 251_CT_marks.pdf", max_pages=1)


def test_queued_job_can_be_cancelled_while_api_stays_responsive(client, monkeypatch):
    import threading
    import result_automation.web_store as module
    original = module.open_document
    started, release = threading.Event(), threading.Event()

    def delayed(*args, **kwargs):
        started.set()
        assert release.wait(10)
        return original(*args, **kwargs)

    monkeypatch.setattr(module, "open_document", delayed)
    source = (ROOT / "examples" / "OOAD_tutorial.pdf").read_bytes()
    first = client.post("/api/documents", files={"file":("first.pdf",source)}).json()
    try:
        assert started.wait(3)
        second = client.post("/api/documents", files={"file":("second.pdf",source)}).json()
        assert client.get("/api/health").status_code == 200
        assert client.post(f"/api/documents/{second['id']}/cancel").status_code == 200
        release.set()
        assert ready(client,first["id"])["status"] == "ready"
        assert ready(client,second["id"])["status"] == "cancelled"
    finally:
        release.set()


@pytest.mark.ocr
def test_image_upload_uses_local_ocr_with_networking_blocked(client, tmp_path, monkeypatch):
    import socket
    from result_automation.document import open_document
    source = open_document(ROOT / "examples" / "OOAD_tutorial.pdf", read_words=False)
    image = tmp_path / "scan.png"
    source.pages[0].image.save(image)

    def blocked(*args, **kwargs):
        raise AssertionError("OCR attempted a network request")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    response = client.post("/api/documents", files={"file":("scan.png",image.read_bytes(),"image/png")})
    assert response.status_code == 202
    doc = ready(client,response.json()["id"])
    assert doc["status"] == "ready", doc
    assert [(r["roll"],r["mark"]) for r in doc["records"]] == SAMPLES[1][1][:27]
    assert doc["review_count"] == 27
    assert doc["pages"][0]["method"] == "Local OCR"
