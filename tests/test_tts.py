"""
tests/test_tts.py — Unit tests for Text-to-Speech (Piper) synthesis.
"""

import unittest
import numpy as np
from pathlib import Path

from jarvis.tts import synthesize, VOICE_PATH, VOICE_CONFIG


class TestTTS(unittest.TestCase):
    def test_voice_model_files_exist(self):
        """Ensure Piper voice model and its json config exist."""
        self.assertTrue(VOICE_PATH.exists(), f"Voice model not found: {VOICE_PATH}")
        self.assertTrue(VOICE_CONFIG.exists(), f"Voice config not found: {VOICE_CONFIG}")

    def test_synthesize_english(self):
        """Synthesizing simple English text returns valid float32 samples and sample rate."""
        audio, sample_rate = synthesize("Hello, I am Jarvis.")
        self.assertIsInstance(audio, np.ndarray)
        self.assertEqual(audio.dtype, np.float32)
        self.assertGreater(len(audio), 0)
        self.assertGreater(sample_rate, 0)

    def test_synthesize_hindi(self):
        """Synthesizing Hindi text returns valid audio samples."""
        audio, sample_rate = synthesize("नमस्ते, मैं आपकी कैसे मदद कर सकता हूँ?")
        self.assertIsInstance(audio, np.ndarray)
        self.assertEqual(audio.dtype, np.float32)
        self.assertGreater(len(audio), 0)
        self.assertGreater(sample_rate, 0)

    def test_synthesize_empty(self):
        """Synthesizing empty string returns empty array without raising."""
        audio, sample_rate = synthesize("")
        self.assertEqual(len(audio), 0)


if __name__ == "__main__":
    unittest.main()
