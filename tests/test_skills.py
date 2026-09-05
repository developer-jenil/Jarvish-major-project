"""
tests/test_skills.py — Unit tests for JARVIS skills (open_app, whatsapp, email, web_search).
"""

import unittest
from jarvis.skills.open_app import try_open_app, match_intent as open_app_match
from jarvis.skills.whatsapp import try_whatsapp, find_contact
from jarvis.skills.email import try_send_email, find_emails
from jarvis.skills.web_search import try_web_search, match_intent as search_match


class TestSkills(unittest.TestCase):
    # --- Open App Skill Tests ---
    def test_open_app_intent_positive(self):
        """Standard app opening commands should be recognized."""
        samples = [
            ("open chrome", "chrome", None),
            ("open notepad", "notepad", None),
            ("kholo calculator", "calculator", None),
            ("start spotify", "spotify", None),
            ("open youtube and play despacito", "youtube", "despacito"),
            ("open google and search for weather in mumbai", "google", "weather in mumbai"),
            ("Notepad application kholo", "Notepad", None),
            ("notepad kholo", "notepad", None),
            ("calculator app open karo", "calculator", None),
            ("chrome chalao", "chrome", None),
            ("whatsapp application ko open karo", "whatsapp", None),
            ("youtube par despacito chalao", "youtube", "despacito"),
        ]
        for text, expected_app, expected_q in samples:
            parsed = open_app_match(text)
            self.assertIsNotNone(parsed, f"Failed to parse: {text}")
            app, q = parsed
            self.assertEqual(app, expected_app)
            self.assertEqual(q, expected_q)

    def test_open_app_intent_negative(self):
        """Conversational sentences should not trigger open app."""
        self.assertIsNone(open_app_match("tell me a joke"))
        self.assertIsNone(open_app_match("what is the time"))
        self.assertIsNone(open_app_match(""))

    def test_open_app_security(self):
        """Malicious command injection attempts must be blocked."""
        handled, msg = try_open_app("open calc && del /f /q C:\\", dry_run=True)
        self.assertTrue(handled)
        self.assertIn("cannot open", msg.lower())

        handled, msg = try_open_app("open javascript:alert(1)", dry_run=True)
        self.assertTrue(handled)
        self.assertIn("cannot open", msg.lower())

    def test_open_app_dry_run(self):
        """Dry run mode should return handled=True with confirmation message."""
        handled, msg = try_open_app("open notepad", dry_run=True)
        self.assertTrue(handled)
        self.assertEqual(msg, "Opening notepad.")

    # --- WhatsApp Skill Tests ---
    def test_whatsapp_intent(self):
        """WhatsApp commands should trigger the skill in dry-run mode."""
        handled, msg = try_whatsapp("send a whatsapp to mom saying I will be late", dry_run=True)
        self.assertTrue(handled)
        self.assertIn("WhatsApp", msg)

        handled, msg = try_whatsapp("tell me the weather", dry_run=True)
        self.assertFalse(handled)

    def test_whatsapp_contact_lookup(self):
        """Contacts in resources/contacts.csv should resolve."""
        contact = find_contact("Mom")
        self.assertIsNotNone(contact)

    # --- Email Skill Tests ---
    def test_email_intent(self):
        """Email commands should trigger the email skill in dry-run mode."""
        handled, msg = try_send_email("send an email to prof sharma about the project update", dry_run=True)
        self.assertTrue(handled)
        self.assertIn("Drafted email", msg)

        handled, msg = try_send_email("how are you today", dry_run=True)
        self.assertFalse(handled)

    def test_email_contact_lookup(self):
        """Email addresses from resources/contacts.csv should resolve."""
        emails = find_emails("prof sharma")
        self.assertIn("sharma@college.edu", emails)

    # --- Web Search Skill Tests ---
    def test_web_search_intent(self):
        """Web search commands should extract the query."""
        self.assertEqual(search_match("search for weather in mumbai"), "weather in mumbai")
        self.assertEqual(search_match("google latest python news"), "latest python news")
        self.assertIsNone(search_match("open chrome"))

    def test_web_search_dry_run(self):
        """Dry run mode should return handled=True and reflect the query."""
        handled, msg = try_web_search("search for artificial intelligence", dry_run=True)
        self.assertTrue(handled)
        self.assertIn("artificial intelligence", msg)


if __name__ == "__main__":
    unittest.main()
