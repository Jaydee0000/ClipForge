from pathlib import Path
import subprocess
import uuid


def create_clip(source: Path, output_dir: Path, start: float, end: float) -> Path:
    if end <= start:
        raise ValueError("Clip end must be greater than clip start")

    output = output_dir / f"clip_{uuid.uuid4().hex[:10]}.mp4"
    duration = end - start

    subprocess.run(
        [
            "ffmpeg", "-y", "-ss", str(start), "-i", str(source),
            "-t", str(duration), "-map", "0:v:0", "-map", "0:a?",
            "-c:v", "libx264", "-c:a", "aac", "-movflags", "+faststart",
            str(output),
        ],
        check=True,
        capture_output=True,
    )
    return output
