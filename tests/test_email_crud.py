"""
tests/test_email_crud.py — Unit tests for interactive email draft CRUD operations.
"""

import unittest
from jarvis.skills.email import (
    try_send_email,
    try_edit_email_draft,
    get_active_draft,
    set_active_draft,
    clear_active_draft,
)


class TestEmailCRUD(unittest.TestCase):
    def setUp(self):
        clear_active_draft()

    def tearDown(self):
        clear_active_draft()

    def test_no_active_draft(self):
        """When no draft is active, edit commands return handled=True with guidance."""
        handled, msg = try_edit_email_draft("on the subject add rain today so i cant come", dry_run=True)
        self.assertTrue(handled)
        self.assertIn("no active email draft", msg.lower())

    def test_non_email_command_ignored(self):
        """Commands not related to editing a draft should return handled=False."""
        handled, msg = try_edit_email_draft("what is the weather today", dry_run=True)
        self.assertFalse(handled)
        self.assertEqual(msg, "")

    def test_initial_send_sets_active_draft(self):
        """A normal send email command should initialize the active draft."""
        handled, msg = try_send_email("send an email to mom about reaching late", dry_run=True)
        self.assertTrue(handled)
        draft = get_active_draft()
        self.assertIsNotNone(draft)
        self.assertIn("mom@example.com", draft["to"])

    def test_subject_update_spoken_reason(self):
        """Spoken reason like 'rain today so i cant come' should be reformulated and update subject."""
        set_active_draft({
            "to": ["mom@example.com"],
            "subject": "Regarding: train delay",
            "body": "Train let ho gai hai.",
        })
        handled, msg = try_edit_email_draft("on the subject add rain today so i cant come", dry_run=True)
        self.assertTrue(handled)
        draft = get_active_draft()
        self.assertIsNotNone(draft)
        self.assertIn("rain", draft["subject"].lower())
        self.assertIn("Updated email subject", msg)

    def test_subject_update_direct_phrase(self):
        """Direct subject change pattern."""
        set_active_draft({
            "to": ["mom@example.com"],
            "subject": "Old Subject",
            "body": "Body text.",
        })
        handled, msg = try_edit_email_draft("change the subject to urgent update", dry_run=True)
        self.assertTrue(handled)
        draft = get_active_draft()
        self.assertIn("urgent update", draft["subject"].lower())

    def test_body_remove(self):
        """Removing a specific phrase from the body."""
        set_active_draft({
            "to": ["mom@example.com"],
            "subject": "Train update",
            "body": "Train let ho gai hai. Please take care.",
        })
        handled, msg = try_edit_email_draft("remove train let ho gai from the body", dry_run=True)
        self.assertTrue(handled)
        draft = get_active_draft()
        self.assertNotIn("train let ho gai", draft["body"].lower())
        self.assertIn("Please take care", draft["body"])

    def test_body_replace(self):
        """Replacing a phrase in the body."""
        set_active_draft({
            "to": ["mom@example.com"],
            "subject": "Meeting",
            "body": "Let us meet at 5pm today.",
        })
        handled, msg = try_edit_email_draft("replace 5pm with 6pm in the body", dry_run=True)
        self.assertTrue(handled)
        draft = get_active_draft()
        self.assertIn("6pm", draft["body"])
        self.assertNotIn("5pm", draft["body"])

    def test_body_append(self):
        """Appending text to the existing body."""
        set_active_draft({
            "to": ["mom@example.com"],
            "subject": "Status",
            "body": "First paragraph.",
        })
        handled, msg = try_edit_email_draft("to the body add reaching in 10 minutes", dry_run=True)
        self.assertTrue(handled)
        draft = get_active_draft()
        self.assertIn("reaching in 10 minutes", draft["body"])

    def test_recipient_update(self):
        """Changing the recipient of an active draft."""
        set_active_draft({
            "to": ["mom@example.com"],
            "subject": "Status",
            "body": "First paragraph.",
        })
        handled, msg = try_edit_email_draft("change recipient to dad", dry_run=True)
        self.assertTrue(handled)
        draft = get_active_draft()
        self.assertEqual(draft["to"], ["dad@example.com"])

    def test_show_draft(self):
        """Reading/inspecting the current draft."""
        set_active_draft({
            "to": ["mom@example.com"],
            "subject": "Test Subject",
            "body": "Test Body Content",
        })
        handled, msg = try_edit_email_draft("show the draft", dry_run=True)
        self.assertTrue(handled)
        self.assertIn("mom@example.com", msg)
        self.assertIn("Test Subject", msg)

    def test_discard_draft(self):
        """Cancelling or discarding the current draft."""
        set_active_draft({
            "to": ["mom@family.local"],
            "subject": "Test Subject",
            "body": "Test Body Content",
        })
        handled, msg = try_edit_email_draft("cancel the draft", dry_run=True)
        self.assertTrue(handled)
        self.assertIsNone(get_active_draft())

    def test_send_now(self):
        """Sending the draft immediately."""
        set_active_draft({
            "to": ["mom@family.local"],
            "subject": "Test Subject",
            "body": "Test Body Content",
        })
        handled, msg = try_edit_email_draft("send the email now", dry_run=True)
        self.assertTrue(handled)
        self.assertIsNone(get_active_draft())


    def test_conversational_body_from_to_replace(self):
        """Conversational phrasing 'to tell you that change the body of the email from X to Y'."""
        set_active_draft({
            "to": ["mom@example.com"],
            "subject": "Running late",
            "body": "Hi Mom, I am late today. Please do not worry.",
        })
        handled, msg = try_edit_email_draft(
            "to tell you that change the body of the email from I am late to I wanted to eat something spicy",
            dry_run=True,
        )
        self.assertTrue(handled)
        draft = get_active_draft()
        self.assertIsNotNone(draft)
        self.assertIn("wanted to eat something spicy", draft["body"].lower())
        self.assertNotIn("i am late", draft["body"].lower())

    def test_new_email_intent_bypasses_draft_edit(self):
        """A new email send command must NOT be intercepted by try_edit_email_draft when an active draft exists."""
        set_active_draft({
            "to": ["dad@example.com"],
            "subject": "Old Subject",
            "body": "Old Body Content",
        })
        cmd = "I am late for train so send a mail to my mom that I am late for the train"
        handled, msg = try_edit_email_draft(cmd, dry_run=True)
        # Must return False so it falls through to try_send_email
        self.assertFalse(handled)

        # Now test that try_send_email creates the new draft for mom
        from jarvis.skills.email import try_send_email
        send_handled, send_msg = try_send_email(cmd, dry_run=True)
        self.assertTrue(send_handled)
        draft = get_active_draft()
        self.assertIsNotNone(draft)
        self.assertIn("mom@example.com", draft["to"])


if __name__ == "__main__":
    unittest.main()
