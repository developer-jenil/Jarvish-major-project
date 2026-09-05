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


if __name__ == "__main__":
    unittest.main()
