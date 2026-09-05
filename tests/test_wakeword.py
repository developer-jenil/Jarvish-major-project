"""
tests/test_wakeword.py — Unit tests for the wake-word detection module.
"""

import unittest
import numpy as np
from pathlib import Path

from jarvis.wakeword import detect, FRAME_SAMPLES, PROJECT_MODEL_PATH, DEFAULT_THRESHOLD


class TestWakeword(unittest.TestCase):
    def test_model_file_exists(self):
        """Ensure the wake-word ONNX model file is present."""
        self.assertTrue(PROJECT_MODEL_PATH.exists(), f"Model missing at {PROJECT_MODEL_PATH}")

    def test_detect_silence(self):
        """Feeding silence should produce a low score, well below threshold."""
        silence = np.zeros(FRAME_SAMPLES, dtype=np.int16)
        score = detect(silence)
        self.assertIsInstance(score, float)
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.0)
        self.assertLess(score, DEFAULT_THRESHOLD)

    def test_detect_random_noise(self):
        """Feeding random noise should also yield a score within [0.0, 1.0]."""
        np.random.seed(42)
        noise = (np.random.randn(FRAME_SAMPLES) * 500).astype(np.int16)
        score = detect(noise)
        self.assertIsInstance(score, float)
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.0)


if __name__ == "__main__":
    unittest.main()
