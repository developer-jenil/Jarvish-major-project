"""
tests/test_stt.py — Unit tests for Speech-to-Text (faster-whisper) transcription.
"""

import unittest
import wave
from pathlib import Path
import numpy as np

from jarvis.stt import transcribe


class TestSTT(unittest.TestCase):
    def setUp(self):
        self.fixtures_dir = Path(__file__).parent / "fixtures"

    def test_transcribe_audio_fixture(self):
        """Transcribing real_heyjarvis.wav should produce accurate speech recognition text."""
        fixture_path = self.fixtures_dir / "real_heyjarvis.wav"
        self.assertTrue(fixture_path.exists(), f"Missing fixture {fixture_path}")

        with wave.open(str(fixture_path), "rb") as wf:
            frames = wf.readframes(wf.getnframes())
            audio = np.frombuffer(frames, dtype=np.int16)

        text = transcribe(audio)
        self.assertIsInstance(text, str)
        self.assertGreater(len(text), 0)
        # Fixture is "Turn on the office lights"
        self.assertTrue(
            "office" in text.lower() or "light" in text.lower() or "turn" in text.lower(),
            f"Expected recognized words in transcription, got: {text!r}"
        )

    def test_transcribe_silence(self):
        """Transcribing silent audio returns a string without crashing."""
        silence = np.zeros(16000, dtype=np.int16)
        text = transcribe(silence)
        self.assertIsInstance(text, str)

    def test_transcribe_groq_mock(self):
        """transcribe_groq should parse Groq response and return text."""
        from unittest.mock import patch, MagicMock
        from jarvis.stt import transcribe_groq

        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.json.return_value = {"text": "Namaste Jarvis open Chrome"}

        with patch("jarvis.stt.load_groq_api_key", return_value="gsk_test123"), \
             patch("requests.Session.post", return_value=fake_resp):
            audio = np.ones(16000, dtype=np.int16) * 1000
            result = transcribe_groq(audio)
            self.assertEqual(result, "Namaste Jarvis open Chrome")

    def test_transcribe_groq_fallback_when_error(self):
        """transcribe() falls back to local Whisper when Groq request fails."""
        from unittest.mock import patch
        from jarvis.stt import transcribe

        with patch("jarvis.stt.load_groq_api_key", return_value="gsk_test123"), \
             patch("jarvis.stt.transcribe_groq", return_value=None), \
             patch("jarvis.stt.transcribe_local", return_value="local fallback text"):
            audio = np.zeros(16000, dtype=np.int16)
            result = transcribe(audio)
            self.assertEqual(result, "local fallback text")


if __name__ == "__main__":
    unittest.main()
