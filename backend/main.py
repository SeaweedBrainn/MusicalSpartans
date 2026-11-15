"""MusicalSpartans backend: stores runs uploaded by the game and serves them to the phone app.

Run with:  python -m fastapi dev main.py --host 0.0.0.0
Docs/test page: http://localhost:8000/docs
"""

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse

DATA_DIR = Path(__file__).parent / "data" / "runs"
RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
SUMMARY_FIELDS = 8

app = FastAPI(title="MusicalSpartans backend")


def _run_dir(run_id: str) -> Path:
    # Run IDs become folder names, so reject anything that could escape DATA_DIR.
    if not RUN_ID_PATTERN.match(run_id):
        raise HTTPException(status_code=400, detail="Invalid run id")
    path = DATA_DIR / run_id
    if not path.is_dir():
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return path


def _validate(summary: str, timeline: str) -> None:
    if len(summary.strip().split(",")) < SUMMARY_FIELDS:
        raise HTTPException(status_code=422, detail=f"Summary needs {SUMMARY_FIELDS} comma-separated values")
    if not any(line.strip().startswith("game_time,") for line in timeline.splitlines()):
        raise HTTPException(status_code=422, detail="Timeline has no game_time header row")


@app.post("/runs")
async def upload_run(summary: UploadFile = File(...), timeline: UploadFile = File(...)):
    """The game uploads its two CSV files here and gets back a run ID (for the QR code)."""
    summary_text = (await summary.read()).decode("utf-8-sig")
    timeline_text = (await timeline.read()).decode("utf-8-sig")
    _validate(summary_text, timeline_text)

    uploaded_at = datetime.now(timezone.utc)
    run_id = f"{uploaded_at:%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"
    run_dir = DATA_DIR / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "summary.csv").write_text(summary_text, encoding="utf-8")
    (run_dir / "timeline.csv").write_text(timeline_text, encoding="utf-8")
    (run_dir / "meta.json").write_text(json.dumps({
        "runId": run_id,
        "uploadedAt": uploaded_at.isoformat(),
        "summaryFile": summary.filename,
        "timelineFile": timeline.filename,
    }), encoding="utf-8")
    return {"runId": run_id}


@app.get("/runs")
def list_runs():
    """All runs, newest first."""
    if not DATA_DIR.is_dir():
        return []
    runs = [json.loads((d / "meta.json").read_text(encoding="utf-8"))
            for d in DATA_DIR.iterdir() if (d / "meta.json").is_file()]
    return sorted(runs, key=lambda r: r["uploadedAt"], reverse=True)


@app.get("/runs/{run_id}/summary.csv", response_class=PlainTextResponse)
def get_summary(run_id: str):
    return (_run_dir(run_id) / "summary.csv").read_text(encoding="utf-8")


@app.get("/runs/{run_id}/timeline.csv", response_class=PlainTextResponse)
def get_timeline(run_id: str):
    return (_run_dir(run_id) / "timeline.csv").read_text(encoding="utf-8")
