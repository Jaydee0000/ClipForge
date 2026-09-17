import os
from pathlib import Path
from typing import Any
from collections.abc import Callable
import subprocess


def _duration(video_path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
        check=True, capture_output=True, text=True,
    )
    return max(float(result.stdout.strip()), 1.0)


def transcribe_video(video_path: Path, on_progress: Callable[[float], None] | None = None) -> list[dict[str, Any]]:
    """Return timestamped transcript segments using a local faster-whisper model."""
    try:
        from faster_whisper import WhisperModel
    except ImportError as error:
        raise RuntimeError(
            "faster-whisper is not installed. Run: pip install faster-whisper"
        ) from error

    model_name = os.getenv("WHISPER_MODEL", "base")
    device = os.getenv("WHISPER_DEVICE", "cpu")
    compute_type = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
    model = WhisperModel(model_name, device=device, compute_type=compute_type)
    segments, _info = model.transcribe(str(video_path), word_timestamps=True)
    duration = _duration(video_path)

    transcript = []
    for segment in segments:
        transcript.append({
            "start": round(float(segment.start), 2),
            "end": round(float(segment.end), 2),
            "text": segment.text.strip(),
        })
        if on_progress:
            on_progress(min(float(segment.end) / duration, 1.0))
    return transcript
