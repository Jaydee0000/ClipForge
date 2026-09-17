import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

MAX_SUGGESTIONS = int(os.getenv("MAX_SUGGESTIONS", "50"))
CHUNK_SECONDS = int(os.getenv("TRANSCRIPT_CHUNK_SECONDS", "180"))
OVERLAP_SECONDS = int(os.getenv("TRANSCRIPT_OVERLAP_SECONDS", "30"))

CLIP_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "clips": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start": {"type": "number"},
                    "end": {"type": "number"},
                    "title": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["start", "end", "title", "reason"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["clips"],
    "additionalProperties": False,
}


def _split_transcript(transcript: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    if not transcript:
        return []
    video_end = max(float(segment["end"]) for segment in transcript)
    chunks = []
    chunk_start = 0.0
    while chunk_start < video_end:
        chunk_end = chunk_start + CHUNK_SECONDS
        chunk = [segment for segment in transcript if float(segment["end"]) > chunk_start and float(segment["start"]) < chunk_end]
        if chunk:
            chunks.append(chunk)
        if chunk_end >= video_end:
            break
        chunk_start += CHUNK_SECONDS - OVERLAP_SECONDS
    return chunks


def _fallback(transcript: list[dict[str, Any]], instructions: str) -> list[dict[str, Any]]:
    if not transcript:
        return []
    count = min(MAX_SUGGESTIONS, len(transcript))
    indexes = [round(index * (len(transcript) - 1) / max(count - 1, 1)) for index in range(count)]
    suggestions = []
    for index, transcript_index in enumerate(indexes):
        segment = transcript[transcript_index]
        center = (float(segment["start"]) + float(segment["end"])) / 2
        start = max(0, center - 12.5)
        suggestions.append({
            "start": round(start, 2), "end": round(start + 25, 2),
            "title": f"Candidate clip {index + 1}",
            "reason": f"Fallback candidate related to: {instructions}",
        })
    return suggestions


def select_clips(
    transcript: list[dict[str, Any]],
    instructions: str,
    on_progress: Callable[[float], None] | None = None,
    on_suggestions: Callable[[list[dict[str, Any]]], None] | None = None,
) -> list[dict[str, Any]]:
    chunks = _split_transcript(transcript)
    if not chunks:
        return []
    all_suggestions = []
    for index, chunk in enumerate(chunks):
        all_suggestions.extend(_select_chunk(chunk, instructions))
        current = _remove_overlaps(all_suggestions)
        if on_suggestions:
            on_suggestions(current[:MAX_SUGGESTIONS])
        if on_progress:
            on_progress((index + 1) / len(chunks))
    merged = _remove_overlaps(all_suggestions)
    if merged:
        return merged[:MAX_SUGGESTIONS]
    print("No AI clips were returned across any transcript chunk; using fallback candidates.")
    return _fallback(transcript, instructions)


def _select_chunk(chunk: list[dict[str, Any]], instructions: str) -> list[dict[str, Any]]:
    if os.getenv("OPENAI_API_KEY"):
        return _select_chunk_openai(chunk, instructions)

    return _select_chunk_ollama(chunk, instructions)


def _build_prompt(chunk: list[dict[str, Any]], instructions: str) -> str:
    chunk_start = float(chunk[0]["start"])
    chunk_end = float(chunk[-1]["end"])
    return f"""
You are an expert YouTube Shorts editor analyzing one section of a longer video.

User instructions:
{instructions}

This transcript section covers {chunk_start:.2f} to {chunk_end:.2f} seconds.
Find every relevant, self-contained moment in this section.

Selection rules:
- Analyze the complete thought, not isolated sentences.
- Include context before a rant, opinion, or player discussion when needed.
- End after the speaker finishes the point, reaction, or conclusion.
- Aim for 20–35 seconds, but use up to 60 seconds when a meaningful discussion needs it.
- Do not force a fixed duration or cut a player discussion in half.
- Exclude greetings, filler, advertisements, and repeated points.
- Use absolute timestamps from the transcript.
- Return an empty list only when this section has none of the requested topics.
- Return several distinct clips when several relevant moments exist; do not stop after finding only one.

Return only a JSON object with this exact shape:
{{"clips": [{{"start": 0, "end": 25, "title": "short title", "reason": "why this moment is strong"}}]}}

Transcript section:
{json.dumps(chunk, ensure_ascii=False)}
"""


def _select_chunk_openai(chunk: list[dict[str, Any]], instructions: str) -> list[dict[str, Any]]:
    api_key = os.environ["OPENAI_API_KEY"]
    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    chunk_start = float(chunk[0]["start"])
    chunk_end = float(chunk[-1]["end"])
    prompt = _build_prompt(chunk, instructions)
    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "temperature": 0.2,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": "Return valid JSON only. Never add commentary outside the JSON object."},
                    {"role": "user", "content": prompt},
                ],
            },
            timeout=180,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            parsed = parsed.get("clips", parsed.get("suggestions", []))
        return _validate(parsed)
    except Exception as error:
        print(f"OpenAI chunk {chunk_start:.2f}-{chunk_end:.2f} selection failed: {error}")
        return []


def _select_chunk_ollama(chunk: list[dict[str, Any]], instructions: str) -> list[dict[str, Any]]:
    ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434/api/chat")
    model = os.getenv("OLLAMA_MODEL", "llama3.2")
    chunk_start = float(chunk[0]["start"])
    chunk_end = float(chunk[-1]["end"])
    prompt = _build_prompt(chunk, instructions)
    try:
        response = requests.post(ollama_url, json={
            "model": model, "stream": False, "format": CLIP_RESPONSE_SCHEMA,
            "options": {"temperature": 0.2, "num_ctx": 8192},
            "messages": [{"role": "user", "content": prompt}],
        }, timeout=600)
        response.raise_for_status()
        content = response.json()["message"]["content"]
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            parsed = parsed.get("clips", parsed.get("suggestions", []))
        return _validate(parsed)
    except Exception as error:
        print(f"Chunk {chunk_start:.2f}-{chunk_end:.2f} selection failed: {error}")
        return []


def _validate(items: Any) -> list[dict[str, Any]]:
    valid = []
    if not isinstance(items, list):
        return valid
    for item in items:
        try:
            start = max(0, float(item["start"]))
            end = float(item["end"])
            duration = end - start
            if duration < 15 or duration > 60:
                continue
            valid.append({
                "start": round(start, 2), "end": round(end, 2),
                "title": str(item.get("title", "Suggested clip")),
                "reason": str(item.get("reason", "Selected by the AI")),
            })
        except (KeyError, TypeError, ValueError):
            continue
    return valid


def _remove_overlaps(suggestions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    kept = []
    for suggestion in sorted(suggestions, key=lambda item: item["start"]):
        overlaps = False
        for existing in kept:
            intersection = max(0, min(suggestion["end"], existing["end"]) - max(suggestion["start"], existing["start"]))
            shorter = min(suggestion["end"] - suggestion["start"], existing["end"] - existing["start"])
            if shorter > 0 and intersection / shorter >= 0.5:
                overlaps = True
                break
        if not overlaps:
            kept.append(suggestion)
    return kept
