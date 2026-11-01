from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from scorecard.api import app

client = TestClient(app)


def _post(path, content, name="orders.csv"):
    return client.post(path, files={"file": (name, content, "text/csv")})


def test_health():
    assert client.get("/health").json()["status"] == "ok"


def test_score_returns_tiers_and_lowest_suppliers(demo_csv):
    r = _post("/score?top=5", demo_csv)
    assert r.status_code == 200
    body = r.json()
    assert body["suppliers"] == 120
    assert sum(body["tiers"].values()) == 120
    scores = [s["score"] for s in body["lowest_scoring"]]
    assert len(scores) == 5 and scores == sorted(scores)


def test_report_is_a_valid_workbook_with_three_sheets(demo_csv):
    r = _post("/report", demo_csv)
    assert r.status_code == 200
    assert "spreadsheetml" in r.headers["content-type"]
    wb = load_workbook(BytesIO(r.content))
    assert wb.sheetnames == ["Summary", "Scores", "Exceptions"]
    exceptions = list(wb["Exceptions"].iter_rows(min_row=2, values_only=True))
    assert exceptions and all(row[2] in ("Critical", "High") for row in exceptions)


@pytest.mark.parametrize(
    "content, status, fragment",
    [
        (b"supplier_id,po_id\nS1,1\n", 422, "Missing required column"),
        (b"", 422, "Could not read"),
        (b"\x00\x01\x02 not a csv at all", 422, ""),
    ],
)
def test_bad_uploads_return_a_clear_422(content, status, fragment):
    r = _post("/score", content)
    assert r.status_code == status
    assert fragment in r.json()["detail"]


def test_missing_file_is_rejected():
    assert client.post("/score").status_code == 422
