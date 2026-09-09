"""Focused video signature and timestamped transcription tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException

from app.services.source_extraction import extract_source_chunks
from app.services.video_transcription import transcribe_video
from app.utils.file_validation import validate_file_signature


class VideoTranscriptionTests(unittest.TestCase):
    """Verify MP4 validation and citation-ready provider response handling."""

    def test_mp4_signature_rejects_masquerading_content(self) -> None:
        """Only an ISO base media header may pass as an MP4 upload."""
        valid_header = b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2"
        validate_file_signature("review.mp4", valid_header)
        with self.assertRaises(HTTPException) as raised:
            validate_file_signature("review.mp4", b"not-a-video")
        self.assertEqual(raised.exception.detail, "The file content does not match its extension.")

    def test_mp4_signature_rejects_malformed_file_type_boxes(self) -> None:
        """Truncated, out-of-bounds, and malformed brands cannot masquerade as MP4."""
        invalid_headers = [
            b"\x00\x00\x00\x18ftypisom",
            b"\x00\x00\x00\x0cftypisom\x00\x00\x00\x00",
            b"\x00\x00\x00\x20ftypisom\x00\x00\x00\x00isom",
            b"\x00\x00\x00\x18ftyp\x00\x00\x00\x00\x00\x00\x00\x00isomiso2",
            b"\x00\x00\x00\x18ftypisom\x00\x00\x00\x00\x00\x00\x00\x00iso2",
            b"\x00\x00\x00\x18ftypisom\x00\x00\x00\x00is\x00miso2",
        ]
        for header in invalid_headers:
            with self.subTest(header=header), self.assertRaises(HTTPException):
                validate_file_signature("review.mp4", header)

    def test_transcription_segments_keep_timestamps_in_rag_chunks(self) -> None:
        """Provider segments become persisted text and structured video locations."""
        response = SimpleNamespace(
            duration=8.5,
            language="en",
            segments=[
                SimpleNamespace(start=0.25, end=3.5, text="Manager opens the review."),
                SimpleNamespace(start=3.5, end=8.5, text="Targets are approved."),
            ],
        )
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "Manager Review.mp4"
            path.write_bytes(b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2")
            client = SimpleNamespace(
                audio=SimpleNamespace(
                    transcriptions=SimpleNamespace(create=lambda **_: response)
                )
            )
            with patch("app.services.video_transcription.Groq", return_value=client), patch(
                "app.services.video_transcription.settings.groq_api_key", "test-key"
            ):
                transcript = transcribe_video(path)
            self.assertEqual(len(transcript.segments), 2)

            with patch(
                "app.services.source_extraction.transcribe_video",
                return_value=transcript,
            ):
                chunks = extract_source_chunks(path)
        self.assertEqual(chunks[0].source_type, "video")
        self.assertIn("[0.250 --> 3.500]", chunks[0].text)
        self.assertEqual(chunks[1].location["timestamp_end_seconds"], 8.5)
        self.assertEqual(chunks[1].location["content_type"], "video_transcript")


if __name__ == "__main__":
    unittest.main()
