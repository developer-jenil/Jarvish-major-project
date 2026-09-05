"""
tests/test_skills.py — Unit tests for JARVIS skills (open_app, whatsapp, email, web_search).
"""

import unittest
from jarvis.skills.open_app import try_open_app, match_intent as open_app_match
from jarvis.skills.datetime_skill import try_datetime, match_intent as datetime_match
from jarvis.skills.whatsapp import try_whatsapp, find_contact
from jarvis.skills.email import try_send_email, find_emails
from jarvis.skills.web_search import try_web_search, match_intent as search_match
from jarvis.skills.browser_control import (
    try_browser_control,
    get_chrome_path,
    reset_browser_state,
    get_browser_state,
    _STATE,
)


class TestSkills(unittest.TestCase):
    # --- DateTime Skill Tests ---
    def test_datetime_intent(self):
        """DateTime skill should detect time, date, and day in English and Hinglish."""
        self.assertEqual(datetime_match("what is the time"), "time")
        self.assertEqual(datetime_match("what time is it"), "time")
        self.assertEqual(datetime_match("Maine poochha ki abhi time kya ho raha hai"), "time")
        self.assertEqual(datetime_match("time kya ho raha hai"), "time")
        self.assertEqual(datetime_match("kitne baje hain"), "time")
        self.assertEqual(datetime_match("what is today's date"), "date")
        self.assertEqual(datetime_match("aaj kya tareekh hai"), "date")
        self.assertEqual(datetime_match("what day is today"), "day")
        self.assertEqual(datetime_match("aaj kaun sa din hai"), "day")
        self.assertIsNone(datetime_match("open notepad"))

    def test_datetime_execution(self):
        """DateTime skill should return formatted responses."""
        handled, msg = try_datetime("what is the time")
        self.assertTrue(handled)
        self.assertIn("The current time is", msg)

        handled, msg = try_datetime("Maine poochha ki abhi time kya ho raha hai")
        self.assertTrue(handled)
        self.assertIn("Abhi", msg)
        self.assertIn("ho rahe hain", msg)

        handled, msg = try_datetime("what is today's date")
        self.assertTrue(handled)
        self.assertIn("Today is", msg)

        handled, msg = try_datetime("aaj kaun sa din hai")
        self.assertTrue(handled)
        self.assertIn("Aaj", msg)

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
        self.assertIsNone(search_match("what is the time"))
        self.assertIsNone(search_match("what is today's date"))

    def test_web_search_dry_run(self):
        """Dry run mode should return handled=True and reflect the query."""
        handled, msg = try_web_search("search for artificial intelligence", dry_run=True)
        self.assertTrue(handled)
        self.assertIn("artificial intelligence", msg)

    # --- Browser Control Skill Tests ---
    def test_browser_control_chrome_path(self):
        """Chrome path resolver should be callable."""
        path = get_chrome_path()
        # May be str or None depending on OS environment, but must not crash
        self.assertTrue(path is None or isinstance(path, str))

    def test_browser_control_plain_open(self):
        """Plain Chrome open commands and 'crome' spelling variants should open Chrome."""
        reset_browser_state()
        samples = [
            "Jarvis Chrome open karo",
            "open chrome",
            "open the chrome",
            "open crome",
            "open the crome",
            "crome open karo",
            "kholo chrome",
            "chrome kholo",
            "I said that open the chrome",
            "i told it to open the crome",
            "i told you to open chrome",
            "open browser",
        ]
        for phrase in samples:
            handled, msg = try_browser_control(phrase, dry_run=True)
            self.assertTrue(handled, f"Failed for {phrase}")
            state = get_browser_state()
            self.assertEqual(state["last_opened_url"], "https://www.google.com")

    def test_browser_control_chrome_search_intents(self):
        """Chrome search intent matching in English and Hinglish."""
        reset_browser_state()
        samples = [
            ("open chrome and search for artificial intelligence", "artificial intelligence"),
            ("chrome par search karo latest laptops", "latest laptops"),
            ("search python tutorials on chrome", "python tutorials"),
            ("google chrome me search karo machine learning", "machine learning"),
            ("Chrome open karo and search for latest news", "latest news"),
            ("crome kholo aur search karo python", "python"),
        ]
        for phrase, expected_query in samples:
            handled, msg = try_browser_control(phrase, dry_run=True)
            self.assertTrue(handled, f"Failed for {phrase}")
            state = get_browser_state()
            self.assertEqual(state["last_query"], expected_query)
            self.assertIn("https://www.google.com/search?q=", state["last_opened_url"])

    def test_browser_control_link_clicking(self):
        """Link clicking should select the requested search result."""
        reset_browser_state()
        _STATE["last_query"] = "python tutorials"
        _STATE["results"] = [
            {"title": "Python Official", "url": "https://www.python.org", "snippet": "Official site"},
            {"title": "W3Schools Python", "url": "https://www.w3schools.com/python", "snippet": "Tutorials"},
            {"title": "GeeksforGeeks Python", "url": "https://www.geeksforgeeks.org/python", "snippet": "GFG"},
        ]

        # First link / pehla link
        handled, msg = try_browser_control("click on the first link", dry_run=True)
        self.assertTrue(handled)
        self.assertEqual(_STATE["last_opened_url"], "https://www.python.org")
        self.assertIn("first", msg.lower())

        handled, msg = try_browser_control("pehla link kholo", dry_run=True)
        self.assertTrue(handled)
        self.assertEqual(_STATE["last_opened_url"], "https://www.python.org")

        # Second link / dusra link
        handled, msg = try_browser_control("open the second result", dry_run=True)
        self.assertTrue(handled)
        self.assertEqual(_STATE["last_opened_url"], "https://www.w3schools.com/python")

        handled, msg = try_browser_control("dusre link par click karo", dry_run=True)
        self.assertTrue(handled)
        self.assertEqual(_STATE["last_opened_url"], "https://www.w3schools.com/python")

        # Open the website (default to first)
        handled, msg = try_browser_control("open the website", dry_run=True)
        self.assertTrue(handled)
        self.assertEqual(_STATE["last_opened_url"], "https://www.python.org")

    def test_browser_control_gmail_drafting(self):
        """Gmail compose drafting should resolve contacts and construct valid URLs."""
        reset_browser_state()
        # Contact prof sharma exists in resources/contacts.csv
        handled, msg = try_browser_control(
            "draft a mail to prof sharma saying project report is ready",
            dry_run=True
        )
        self.assertTrue(handled)
        state = get_browser_state()
        self.assertEqual(state["active_site"], "gmail")
        self.assertIn("mail.google.com", state["last_opened_url"])
        self.assertIn("to=sharma%40college.edu", state["last_opened_url"])
        self.assertIn("Project+report+is+ready", state["last_opened_url"])

        # Contextual drafting when active_site is gmail
        _STATE["active_site"] = "gmail"
        handled, msg = try_browser_control(
            "compose mail to mom saying I will be home soon",
            dry_run=True
        )
        self.assertTrue(handled)
        state = get_browser_state()
        self.assertIn("mail.google.com", state["last_opened_url"])

    def test_browser_control_compound_search_and_click(self):
        """Compound voice commands like search Gmail and click first link should execute directly."""
        reset_browser_state()
        cases = [
            (
                "Chrome kholo aur uske search bar Mein jakar Gmail likho aur jo Pahli link hai use click kar do",
                "https://mail.google.com"
            ),
            (
                "Gmail and click on the first link that what it appear",
                "https://mail.google.com"
            ),
            (
                "search python tutorial and click first link",
                "https://en.wikipedia.org/wiki/python%20tutorial"
            ),
            (
                "uske search bar me Gmail likho",
                "https://www.google.com/search?q=Gmail"
            ),
        ]
        for phrase, expected_url in cases:
            reset_browser_state()
            handled, msg = try_browser_control(phrase, dry_run=True)
            self.assertTrue(handled, f"Failed for {phrase}")
            state = get_browser_state()
            self.assertEqual(state["last_opened_url"], expected_url, f"URL mismatch for {phrase}")


if __name__ == "__main__":
    unittest.main()
