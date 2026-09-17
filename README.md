# ClipForge

ClipForge turns a long video into suggested short clips.

## MVP flow

1. Upload a video.
2. Enter clipping instructions.
3. Transcribe the video with word timestamps.
4. Ask an LLM to return clip start/end times as JSON.
5. Cut the selected ranges with FFmpeg.
6. Review, download, and later add effects.

## Project layout

```text
clipforge/
├── backend/
│   ├── app/
│   │   ├── main.py              # HTTP API
│   │   ├── schemas.py           # Request/response models
│   │   └── services/
│   │       ├── clipper.py       # FFmpeg video cutting
│   │       ├── transcriber.py   # Whisper adapter (next)
│   │       └── selector.py      # LLM adapter (next)
│   ├── media/uploads/            # Original videos
│   ├── media/clips/              # Generated clips
│   └── requirements.txt
├── frontend/
│   ├── src/App.tsx              # Upload, instructions, results
│   ├── src/main.tsx
│   ├── src/styles.css
│   └── package.json
└── README.md
```

## Start the backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# Add local transcription support:
pip install faster-whisper
uvicorn app.main:app --reload
```

For local LLM clip selection, install Ollama and download a model:

```bash
ollama pull llama3.2
ollama serve
```

If Ollama is not running, the API uses a simple transcript-based fallback so the rest of the pipeline can still be tested.

## Start the frontend

```bash
cd frontend
npm install
npm run dev
```

The first working slice lets you upload a video and cut a clip by entering start/end seconds. The AI analysis endpoint is intentionally separated so we can add Whisper and an LLM without rewriting the rest of the app.
