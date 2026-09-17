from pathlib import Path
import shutil
import subprocess
import uuid
from typing import Any

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .schemas import AnalyzeRequest, ClipRequest, SuggestedClip
from .services.clipper import create_clip
from .services.selector import select_clips
from .services.transcriber import transcribe_video

ROOT = Path(__file__).resolve().parents[1]
UPLOAD_DIR = ROOT / "media" / "uploads"
CLIP_DIR = ROOT / "media" / "clips"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
CLIP_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="ClipForge API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/media", StaticFiles(directory=ROOT / "media"), name="media")
jobs: dict[str, dict[str, Any]] = {}


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/videos")
async def upload_video(file: UploadFile = File(...)):
    allowed = {"video/mp4", "video/quicktime", "video/webm", "video/x-matroska"}
    if file.content_type not in allowed:
        raise HTTPException(400, "Upload an MP4, MOV, WebM, or MKV video")

    video_id = uuid.uuid4().hex
    extension = Path(file.filename or "video.mp4").suffix.lower() or ".mp4"
    destination = UPLOAD_DIR / f"{video_id}{extension}"
    with destination.open("wb") as output:
        shutil.copyfileobj(file.file, output)

    return {"video_id": video_id, "filename": file.filename, "path": str(destination)}


@app.post("/api/clips")
def make_clip(request: ClipRequest):
    source_matches = list(UPLOAD_DIR.glob(f"{request.video_id}.*"))
    if not source_matches:
        raise HTTPException(404, "Video not found")

    try:
        output = create_clip(source_matches[0], CLIP_DIR, request.start, request.end)
    except (ValueError, subprocess.CalledProcessError) as error:
        raise HTTPException(400, f"Could not create clip: {error}") from error

    return {
        "title": request.title,
        "start": request.start,
        "end": request.end,
        "url": f"/media/clips/{output.name}",
    }


@app.post("/api/analyze")
def analyze_video(request: AnalyzeRequest, background_tasks: BackgroundTasks):
    source_matches = list(UPLOAD_DIR.glob(f"{request.video_id}.*"))
    if not source_matches:
        raise HTTPException(404, "Video not found")

    job_id = uuid.uuid4().hex
    jobs[job_id] = {"status": "queued", "progress": 0, "message": "Queued for analysis", "eta_seconds": None, "ideas": []}
    background_tasks.add_task(run_analysis, job_id, source_matches[0], request.instructions)
    return {"job_id": job_id, "status": "queued"}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    if job_id not in jobs:
        raise HTTPException(404, "Analysis job not found")
    return jobs[job_id]


def run_analysis(job_id: str, source: Path, instructions: str):
    import time
    started = time.monotonic()

    def update(progress: float, message: str):
        elapsed = time.monotonic() - started
        eta = round(elapsed * (100 - progress) / progress) if progress > 2 else None
        jobs[job_id].update({"status": "processing", "progress": round(progress, 1), "message": message, "eta_seconds": eta})

    try:
        update(2, "Loading Whisper transcription model...")
        transcript = transcribe_video(source, lambda fraction: update(5 + fraction * 65, "Transcribing video..."))
        update(74, "Asking the AI to select the best moments...")
        suggestions = select_clips(
            transcript,
            instructions,
            lambda fraction: update(74 + fraction * 8, "Analyzing transcript chunks with Ollama..."),
            lambda ideas: jobs[job_id].update({"ideas": ideas}),
        )
        update(82, "Creating clips with FFmpeg...")
        for index, suggestion in enumerate(suggestions):
            output = create_clip(source, CLIP_DIR, suggestion["start"], suggestion["end"])
            suggestion["clip_url"] = f"/media/clips/{output.name}"
            update(min(99, 82 + 17 * (index + 1) / max(len(suggestions), 1)), "Creating clips with FFmpeg...")
        final_suggestions = [SuggestedClip(**item).model_dump() for item in suggestions]
        jobs[job_id].update({"status": "complete", "progress": 100, "message": f"Analysis complete — created {len(suggestions)} clips.", "eta_seconds": 0, "ideas": final_suggestions, "suggestions": final_suggestions, "transcript": transcript})
    except Exception as error:
        jobs[job_id].update({"status": "failed", "progress": 0, "message": str(error), "eta_seconds": None})
