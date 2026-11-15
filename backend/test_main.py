from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import main

ASSETS = Path(__file__).parent.parent / "app" / "src" / "main" / "assets"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DATA_DIR", tmp_path / "runs")
    return TestClient(main.app)


def upload(client, summary: bytes, timeline: bytes):
    return client.post("/runs", files={"summary": ("s.csv", summary), "timeline": ("t.csv", timeline)})


def test_upload_then_fetch_round_trips_game_files(client):
    summary = (ASSETS / "song10-chart1-summary.csv").read_bytes()
    timeline = (ASSETS / "song10-chart1.csv").read_bytes()

    run_id = upload(client, summary, timeline).json()["runId"]

    assert client.get("/runs").json()[0]["runId"] == run_id
    assert client.get(f"/runs/{run_id}/summary.csv").text == summary.decode()
    assert client.get(f"/runs/{run_id}/timeline.csv").text == timeline.decode()


def test_rejects_files_that_are_not_game_output(client):
    assert upload(client, b"1,2,3", b"game_time,x\n0,1").status_code == 422
    assert upload(client, b"1,2,3,4,5,6,7,8", b"no header here").status_code == 422


def test_unknown_or_unsafe_run_ids(client):
    assert client.get("/runs/nope/summary.csv").status_code == 404
    assert client.get("/runs/..%2F..%2Fsecrets/summary.csv").status_code in (400, 404)
