"""LAN prototype. Run: python -m uvicorn server:app --host 0.0.0.0 --port 8000"""
import json
import threading
import uuid
from pathlib import Path

import pytesseract
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from extract import MAX_IMAGE_BYTES, extract, load_image

ROOT = Path(__file__).resolve().parent
OUTPUTS = ROOT / "outputs"
OUTPUTS.mkdir(exist_ok=True)
app = FastAPI(title="Etterna results extractor")
app.mount("/outputs", StaticFiles(directory=OUTPUTS), name="outputs")
locks = {}
locks_guard = threading.Lock()


def directory_for(job_id):
    try:
        parsed = uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(404, "Unknown scan")
    if str(parsed) != job_id or not (OUTPUTS / job_id).is_dir():
        raise HTTPException(404, "Unknown scan")
    return OUTPUTS / job_id


def write_json(path, data):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, indent=2))
    temporary.replace(path)


def process(job_id, mode="auto", corners=None):
    directory = directory_for(job_id)
    try:
        source = directory / "original-source.bin"
        if not source.is_file():
            source = directory / "original.jpg"
        result = extract(load_image(source.read_bytes()),
                         directory, mode, corners)
        result["job_id"] = job_id
        result["review_path"] = f"/?job={job_id}"
        write_json(directory / "result.json", result)
    except Exception as error:
        write_json(directory / "result.json", {
            "status": "error", "job_id": job_id,
            "warnings": [f"{type(error).__name__}: {error}"]})
    finally:
        with locks_guard:
            locks[job_id] = False


@app.get("/")
def index():
    return FileResponse(ROOT / "index.html")


@app.get("/health")
def health():
    try:
        from native_ocr import engine
        selected = engine()
        # Numeric crops always require Tesseract, including experimental Vision mode.
        version = str(pytesseract.get_tesseract_version())
    except Exception as error:
        raise HTTPException(503, f"OCR setup error: {error}")
    import os
    from qr_reader import decoder_name
    return {"status": "ok", "extractor_version": "16.0", "csv_formats": [1, 2], "session_coaching_api": 1, "session_api": 1, "qr_decoder": decoder_name(), "game_run_api": 1, "coach_api": 1,
            "coach_service_configured": bool(os.getenv("RHYTHM_COACH_URL", "").strip()), "ocr_engine": selected,
            "judgment_ocr_engine": "rapidocr" if selected == "rapidocr" else "tesseract",
            "tesseract": version, "alignment": "game_content_registration"}


@app.get("/api/jobs")
def jobs():
    return [{"job_id": p.name} for p in sorted(
        OUTPUTS.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
        if p.is_dir() and (p / "result.json").exists()][:30]


def submit_image(data, background_tasks, mode):
    # Validate before scheduling. Decode/EXIF normalize once into a JPEG for review.
    try:
        image = load_image(bytes(data))
    except Exception as error:
        raise HTTPException(400, f"Invalid image: {error}")
    import cv2
    job_id = str(uuid.uuid4())
    directory = OUTPUTS / job_id
    directory.mkdir()
    (directory / "original-source.bin").write_bytes(bytes(data))
    cv2.imwrite(str(directory / "original.jpg"), image, [cv2.IMWRITE_JPEG_QUALITY, 98])
    write_json(directory / "result.json", {"status": "processing", "job_id": job_id})
    with locks_guard:
        locks[job_id] = True
    background_tasks.add_task(process, job_id, mode)
    return {"job_id": job_id, "status": "processing", "review_path": f"/?job={job_id}"}


@app.post("/api/jobs", status_code=202)
async def create_job(request: Request, background_tasks: BackgroundTasks, mode: str = "auto"):
    if mode not in ("auto", "screen"):
        raise HTTPException(400, "mode must be auto or screen")
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > MAX_IMAGE_BYTES:
            raise HTTPException(413, "Photo exceeds 20 MB")
    return submit_image(bytes(data), background_tasks, mode)


@app.post("/api/demo", status_code=202)
def demo(background_tasks: BackgroundTasks):
    sample = ROOT.parent / "samples" / "etterna-4k-results.png"
    if not sample.is_file():
        raise HTTPException(404, "Copy the samples folder next to backend to use the demo")
    return submit_image(sample.read_bytes(), background_tasks, "screen")


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    directory = directory_for(job_id)
    return json.loads((directory / "result.json").read_text())


@app.get("/api/jobs/{job_id}/preview/{name}")
def preview(job_id: str, name: str):
    # Fetch through the miniapp background bridge; WebView needs no LAN CORS access.
    allowed = {"original", "screen", "overlay", "detected_content", "results", "accuracy", "grade", "ratings",
               "timing_stats", "auxiliary_counts", "ratios_and_streaks", "offset_graph",
               "song_and_rate", "options", "footer"}
    if name not in allowed:
        raise HTTPException(404, "Unknown image")
    directory = directory_for(job_id)
    filename = directory / ("original.jpg" if name == "original" else f"{name}.png")
    if not filename.is_file():
        raise HTTPException(404, "Image is not available for this scan")
    import cv2
    image = cv2.imread(str(filename))
    if image is None:
        raise HTTPException(404, "Unreadable image")
    scale = min(1, 1200/image.shape[1])
    if scale < 1:
        image = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    if name in ("original", "detected_content"):
        _, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 88])
        media_type = "image/jpeg"
    else:
        _, encoded = cv2.imencode(".png", image)
        media_type = "image/png"
    return Response(encoded.tobytes(), media_type=media_type,
                    headers={"Cache-Control": "no-store"})


class Reprocess(BaseModel):
    corners: list[list[float]]


@app.post("/api/jobs/{job_id}/auto-align", status_code=202)
def auto_align_again(job_id: str, background_tasks: BackgroundTasks):
    directory = directory_for(job_id)
    if not (directory / "original-source.bin").is_file() and not (directory / "original.jpg").is_file():
        raise HTTPException(400, "This game run has CSV data, not a photo to align")
    with locks_guard:
        if locks.get(job_id):
            raise HTTPException(409, "This scan is still processing")
        locks[job_id] = True
    write_json(directory / "result.json", {"status": "processing", "job_id": job_id})
    background_tasks.add_task(process, job_id, "auto")
    return {"job_id": job_id, "status": "processing"}


@app.post("/api/jobs/{job_id}/corners", status_code=202)
def correct_corners(job_id: str, body: Reprocess, background_tasks: BackgroundTasks):
    directory = directory_for(job_id)
    # Validate corner geometry before resetting the job result.
    from extract import rectify
    try:
        source = directory / "original-source.bin"
        if not source.is_file():
            source = directory / "original.jpg"
        rectify(load_image(source.read_bytes()), body.corners)
    except Exception as error:
        raise HTTPException(400, str(error))
    with locks_guard:
        if locks.get(job_id):
            raise HTTPException(409, "This scan is still processing")
        locks[job_id] = True
    write_json(directory / "result.json", {"status": "processing", "job_id": job_id})
    background_tasks.add_task(process, job_id, "auto", body.corners)
    return {"job_id": job_id, "status": "processing"}


from runs_api import router as game_router
app.include_router(game_router)
from coach_api import router as coach_router
app.include_router(coach_router)
