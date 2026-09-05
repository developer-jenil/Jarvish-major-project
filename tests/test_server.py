"""
tests/test_server.py — Automated tests for the JARVIS Flask API and Dashboard Server.
"""

import unittest
import json
from server import app


class TestServer(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def test_index_page(self):
        """GET / should render the dashboard HTML."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"J.A.R.V.I.S.", response.data)
        self.assertIn(b"NEURAL OPERATING INTERFACE", response.data)

    def test_status_endpoint(self):
        """GET /api/status should return system telemetry JSON."""
        response = self.client.get("/api/status")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data.get("online"))
        self.assertIn("models", data)
        self.assertIn("wakeword", data["models"])
        self.assertIn("tts", data["models"])

    def test_command_open_app(self):
        """POST /api/command with open app intent should return skill response."""
        response = self.client.post(
            "/api/command",
            data=json.dumps({"text": "open notepad", "speak": False}),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("skill"), "open-app")
        self.assertIn("notepad", data.get("reply").lower())

    def test_command_empty(self):
        """POST /api/command with empty text should return 400."""
        response = self.client.post(
            "/api/command",
            data=json.dumps({"text": ""}),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)

    def test_skill_open_app(self):
        """POST /api/skills/open-app should launch or dry-run requested app."""
        response = self.client.post(
            "/api/skills/open-app",
            data=json.dumps({"app": "calc", "dry_run": True}),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data.get("success"))

    def test_skill_search(self):
        """POST /api/skills/search should query DuckDuckGo and return results list."""
        response = self.client.post(
            "/api/skills/search",
            data=json.dumps({"query": "python programming", "max_results": 2}),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("query"), "python programming")
        self.assertIsInstance(data.get("results"), list)

    def test_contacts_get(self):
        """GET /api/contacts should return contact list."""
        response = self.client.get("/api/contacts")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("contacts", data)
        self.assertIsInstance(data["contacts"], list)

    def test_tts_endpoint(self):
        """GET /api/tts should stream synthesized WAV audio."""
        response = self.client.get("/api/tts?text=test")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content_type, "audio/wav")
        # Check standard WAV RIFF header
        self.assertTrue(response.data.startswith(b"RIFF"))


if __name__ == "__main__":
    unittest.main()
