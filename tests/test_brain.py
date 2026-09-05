"""
tests/test_brain.py — Unit tests for the LLM brain integration.
"""

import unittest
from unittest.mock import patch, MagicMock
import json

from jarvis import brain


class TestBrain(unittest.TestCase):
    def test_load_api_key(self):
        """load_api_key should retrieve the OPENROUTER_API_KEY from env or .env."""
        key = brain.load_api_key()
        self.assertIsNotNone(key, "Expected OPENROUTER_API_KEY to be loaded")
        self.assertTrue(key.startswith("sk-or-v1-"), f"Unexpected key format: {key[:12]}...")

    @patch("urllib.request.urlopen")
    def test_ask_success_mock(self, mock_urlopen):
        """ask() should construct a proper payload and return choices[0].message.content."""
        fake_response = MagicMock()
        fake_response.read.return_value = json.dumps({
            "choices": [{"message": {"content": "Hello, I am Jarvis!"}}]
        }).encode("utf-8")
        fake_response.__enter__.return_value = fake_response
        mock_urlopen.return_value = fake_response

        reply = brain.ask("Hello Jarvis")
        self.assertEqual(reply, "Hello, I am Jarvis!")

    @patch.dict("os.environ", {}, clear=True)
    def test_ask_no_key(self):
        """ask() without API key should return friendly offline error message."""
        with patch("jarvis.brain.load_api_key", return_value=None):
            reply = brain.ask("Hello")
            self.assertTrue(reply.startswith("[brain] No OPENROUTER_API_KEY set"))


if __name__ == "__main__":
    unittest.main()
