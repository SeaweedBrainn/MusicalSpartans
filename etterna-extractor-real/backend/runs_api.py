"""Game upload endpoints and adapters to the existing miniapp job protocol."""
import json
import uuid
from pathlib import Path

import cv2
from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

import game_runs

router = APIRouter()
ROOT = Path(__file__).resolve().parent


async def read_csv(upload):
    try:
        data = await upload.read(game_runs.MAX_CSV_BYTES+1)
        if len(data) > game_runs.MAX_CSV_BYTES:
            raise HTTPException(413, "Each CSV must be at most 2 MB")
        try:
            return data.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise HTTPException(400, "CSV must use UTF-8 text encoding")
    finally:
        await upload.close()


def create(summary, timeline=None):
    try:
        return game_runs.create_run(summary, timeline)
    except ValueError as error:
        raise HTTPException(422, str(error))


def get(run_id):
    try:
        return game_runs.load_run(run_id)
    except ValueError as error:
        raise HTTPException(400, str(error))
    except FileNotFoundError as error:
        raise HTTPException(404, str(error))


def receipt(result):
    run_id = result["run_id"]
    return {"runId": run_id, "run_id": run_id, "qr_payload": game_runs.PREFIX+run_id,
            "qr_path": f"/runs/{run_id}/qr.png", "run_path": f"/runs/{run_id}"}


def sample_run():
    directory = ROOT.parent / "samples" / "custom-game"
    try:
        return create((directory / "song10-chart1-summary.csv").read_text(),
                      (directory / "song10-chart1.csv").read_text())
    except FileNotFoundError:
        raise HTTPException(404, "Copy samples/custom-game alongside backend to use the game sample")


def store_job(result):
    from server import OUTPUTS, write_json
    job_id = str(uuid.uuid4())
    directory = OUTPUTS / job_id
    directory.mkdir()
    result.update(job_id=job_id, review_path=f"/?job={job_id}")
    write_json(directory / "result.json", result)
    return {"job_id": job_id, "status": "processing"}


def miniapp_job(payload):
    # Import lazily to keep the extraction module independent of the API server.
    from session_qr import resolve
    result = resolve(payload)
    if result is not None:
        return store_job(result)
    result = game_runs.resolve_qr(payload)
    if result is None:
        raise HTTPException(400, "Paste a supported game session QR link or a legacy mentra-run:v1: payload")
    if result["status"] != "run_analyzed":
        raise HTTPException(404, " ".join(result["warnings"]))
    return store_job(result)


@router.post("/runs", status_code=201)
async def upload_run(summary: UploadFile = File(...), timeline: UploadFile | None = File(None)):
    summary_text = await read_csv(summary)
    timeline_text = await read_csv(timeline) if timeline is not None else None
    return receipt(create(summary_text, timeline_text))


@router.get("/runs")
def list_runs():
    if not game_runs.STORE.is_dir():
        return []
    result = []
    for path in game_runs.STORE.glob("*/result.json"):
        data = json.loads(path.read_text())
        result.append({"run_id": data["run_id"], "created_at": data["created_at"],
                       "song_id": data["run"]["summary"]["song_id"],
                       "qr_payload": game_runs.PREFIX+data["run_id"]})
    return sorted(result, key=lambda r: r["created_at"], reverse=True)[:100]


@router.get("/runs/{run_id}")
def run_result(run_id: str):
    return get(run_id)


@router.get("/runs/{run_id}/qr.png")
def run_qr(run_id: str):
    get(run_id)
    code = cv2.QRCodeEncoder_create().encode(game_runs.PREFIX+run_id)
    code = cv2.copyMakeBorder(code, 4, 4, 4, 4, cv2.BORDER_CONSTANT, value=255)
    code = cv2.resize(code, None, fx=10, fy=10, interpolation=cv2.INTER_NEAREST)
    ok, encoded = cv2.imencode(".png", code)
    if not ok:
        raise HTTPException(500, "Could not generate QR image")
    return Response(encoded.tobytes(), media_type="image/png")


@router.get("/runs/{run_id}/{filename}")
def run_file(run_id: str, filename: str):
    get(run_id)
    if filename not in ("summary.csv", "timeline.csv"):
        raise HTTPException(404, "Unknown game file")
    path = game_runs.run_directory(run_id) / filename
    if not path.is_file():
        raise HTTPException(404, "No timeline was supplied for this run")
    return FileResponse(path, media_type="text/csv; charset=utf-8")


class LoadRun(BaseModel):
    payload: str


@router.post("/api/game-run", status_code=202)
def load_game_run(body: LoadRun):
    return miniapp_job(body.payload.strip())


@router.post("/api/game-demo", status_code=202)
def game_demo():
    return miniapp_job(game_runs.PREFIX+sample_run()["run_id"])


class RefreshSession(BaseModel):
    handle: str
    run_id: str | None = None


@router.post("/api/game-session", status_code=202)
def refresh_game_session(body: RefreshSession):
    from session_qr import refresh
    return store_job(refresh(body.handle, body.run_id))
