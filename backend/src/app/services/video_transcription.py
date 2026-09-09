"""Timestamped video transcription through the configured Groq account."""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path

from groq import Groq

from app.config import settings


VIDEO_EXTENSIONS = frozenset({".mp4"})
_PLACEHOLDER_KEYS = {"", "paste_key_1_here", "paste_your_groq_api_key_here"}


class VideoTranscriptionError(ValueError):
    """Raised when a supported video cannot produce a safe transcript."""


@dataclass(frozen=True)
class TranscriptSegment:
    """Store one timestamped speech segment returned by the provider."""

    start_seconds: float
    end_seconds: float
    text: str


@dataclass(frozen=True)
class VideoTranscript:
    """Represent the complete transcript and its citation-ready segments."""

    segments: tuple[TranscriptSegment, ...]
    duration_seconds: float | None
    language: str | None


def _response_value(value: object, key: str, default: object = None) -> object:
    """Read SDK models and test dictionaries through one narrow adapter."""
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _safe_seconds(value: object, default: float) -> float:
    """Normalize provider timestamps and reject non-finite or negative values."""
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return default
    return seconds if math.isfinite(seconds) and seconds >= 0 else default


def transcribe_video(path: Path) -> VideoTranscript:
    """Transcribe an MP4 once and return segment timestamps for durable citations."""
    if path.suffix.lower() not in VIDEO_EXTENSIONS:
        raise VideoTranscriptionError("Unsupported video type.")
    if settings.groq_api_key.strip().lower() in _PLACEHOLDER_KEYS:
        raise VideoTranscriptionError(
            "Video transcription is not configured. Set GROQ_API_KEY."
        )

    client = Groq(
        api_key=settings.groq_api_key,
        timeout=settings.parser_timeout_seconds,
    )
    with path.open("rb") as video:
        response = client.audio.transcriptions.create(
            file=video,
            model=settings.groq_transcription_model,
            response_format="verbose_json",
            timestamp_granularities=["segment"],
            temperature=0.0,
        )

    segments: list[TranscriptSegment] = []
    for raw in _response_value(response, "segments", []) or []:
        text = str(_response_value(raw, "text", "") or "").strip()
        if not text:
            continue
        start = _safe_seconds(_response_value(raw, "start", 0), 0)
        end = _safe_seconds(_response_value(raw, "end", start), start)
        segments.append(TranscriptSegment(start, max(start, end), text))

    duration_value = _response_value(response, "duration")
    duration = _safe_seconds(duration_value, 0) if duration_value is not None else None
    if not segments:
        text = str(_response_value(response, "text", "") or "").strip()
        if text:
            segments.append(TranscriptSegment(0, duration or 0, text))
    if not segments:
        raise VideoTranscriptionError(
            "No spoken transcript was found in the uploaded video."
        )
    language = str(_response_value(response, "language", "") or "").strip() or None
    return VideoTranscript(tuple(segments), duration, language)
