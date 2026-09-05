"""
tests/test_tts.py — Unit tests for Text-to-Speech (Piper) synthesis.
"""

import unittest
import numpy as np
from pathlib import Path

from jarvis.tts import (
    synthesize,
    clean_text_for_speech,
    synthesize_edge,
    VOICE_PATH,
    VOICE_CONFIG,
    AVAILABLE_EDGE_VOICES,
)


class TestTTS(unittest.TestCase):
    def test_voice_model_files_exist(self):
        """Ensure Piper voice model and its json config exist."""
        self.assertTrue(VOICE_PATH.exists(), f"Voice model not found: {VOICE_PATH}")
        self.assertTrue(VOICE_CONFIG.exists(), f"Voice config not found: {VOICE_CONFIG}")

    def test_clean_text_for_speech_parentheses(self):
        """Removes duplicate translations in parentheses and brackets."""
        raw = "Namaste! (Hello!) Main aapki madad kar sakta hoon. [help]"
        cleaned = clean_text_for_speech(raw)
        self.assertEqual(cleaned, "Namaste! Main aapki madad kar sakta hoon.")

    def test_clean_text_for_speech_markdown_and_bullets(self):
        """Removes markdown symbols like asterisks, hashes, and list bullets."""
        raw = "# Commands\n* Play video\n* Open app **Chrome**"
        cleaned = clean_text_for_speech(raw)
        self.assertNotIn("*", cleaned)
        self.assertNotIn("#", cleaned)
        self.assertIn("Play video", cleaned)
        self.assertIn("Chrome", cleaned)

    def test_clean_text_for_speech_full_hinglish_response(self):
        """Validates the exact real-world response clean-up."""
        raw = (
            "Namaste! Main JARVIS hoon. (Hello! I'm JARVIS.) "
            "Aap kya karna chahte hain? (What do you want to do?) "
            "* Play video (play a video) * Open website (open a website)"
        )
        cleaned = clean_text_for_speech(raw)
        self.assertNotIn("Hello!", cleaned)
        self.assertNotIn("What do you want to do?", cleaned)
        self.assertNotIn("*", cleaned)
        self.assertIn("Namaste! Main JARVIS hoon.", cleaned)

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

    def test_synthesize_edge(self):
        """Synthesize via Edge-TTS returns valid non-empty MP3 bytes."""
        mp3 = synthesize_edge("Namaste dosto, main JARVIS hoon.")
        self.assertIsInstance(mp3, bytes)
        self.assertGreater(len(mp3), 0)


if __name__ == "__main__":
    unittest.main()
