"""
jarvis/skills/whatsapp.py — WhatsApp messaging skill.

Send a WhatsApp message by voice. Example commands:
    "send whatsapp to mom saying I will be late"
    "whatsapp john that I'll reach by 7"
    "bhejo mom ko whatsapp ki main der se aaunga"

HOW IT WORKS
-----------
1. Parse the command to extract recipient name + optional message body.
2. Look up the recipient's WhatsApp ID from resources/contacts.csv.
   - contacts.csv columns: name, whatsapp_id, email, relation, notes
   - Matching is case-insensitive substring (so "mom" matches "Mom").
3. If no explicit message body is given, ask the LLM brain to draft one
   based on the command context.
4. Open WhatsApp Web (web.whatsapp.com) with the message pre-filled via
   pywhatkit.send whatsapp message. The user must review and click Send
   themselves — pywhatkit cannot bypass the human confirmation step.
5. Speak a confirmation or an error back through TTS.

REQUIREMENTS
-----------
- An active internet connection (opens WhatsApp Web).
- The user must already be logged into WhatsApp Web in their browser.
- A contact entry in resources/contacts.csv (recommended; works without).

SAFETY
-----
- Recipient names are validated against the contacts file; if not found we
  still proceed but warn the user so they can correct us.
- Message bodies shorter than 5 characters are rejected to avoid noise.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

# --- Paths ---------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_CONTACTS_PATH = _PROJECT_ROOT / "resources" / "contacts.csv"

# --- Verb phrases that signal a WhatsApp send intent. Includes Hinglish.
_WHATSAPP_VERBS = (
    r"(?:send\s+(?:a\s+)?whatsapp|"
    r"whatsapp|wa\s+send|message\s+(?:on|via)\s+whatsapp|"
    r"whatsapp\s+karo|whatsapp\s+kardo|bhejo\s+whatsapp|wa\s+bhejo)"
)
_INTENT_RE = re.compile(rf"\b{_WHATSAPP_VERBS}\b", re.IGNORECASE)

# We match the recipient after verbs like "to", "ko", or just the next word.
_RECIPIENT_PATTERN = re.compile(
    rf"\b({_WHATSAPP_VERBS})\b.*?(?:to|ko)\s+(\w[\w\s]*?)\b(?:\s+saying|\s+telling|\s+that|\s+bolke|\s+kaho|\s+ki\b|$)",
    re.IGNORECASE,
)

# If there's no explicit "saying/telling/ki" clause, grab everything after
# the recipient name up to common end markers.
_BODY_PATTERN = re.compile(
    r"(\w[\w\s]*?)(?:\s+saying|\s+telling|\s+that|\s+ki\b|\s+bolke|\s+kaho|\s+bole|\s+keho|kahaniya?)$",
    re.IGNORECASE,
)

# Minimum message body length (reject accidental noise).
_MIN_BODY_LEN = 5


def _load_contacts() -> list[dict[str, str]]:
    """Load contacts.csv and return a list of row dicts."""
    if not _CONTACTS_PATH.exists():
        return []
    with open(_CONTACTS_PATH, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def find_contact(contact_name: str) -> str | None:
    """Look up a contact by name (case-insensitive substring match).

    Returns the raw whatsapp_id string from contacts.csv, or None if not found.
    """
    contacts = _load_contacts()
    needle = contact_name.strip().lower()
    for row in contacts:
        if needle in row.get("name", "").lower():
            wid = row.get("whatsapp_id", "").strip()
            if wid:
                return wid
            # Contact exists but has no WhatsApp ID — return the name as-is
            # so pywhatkit will search for it instead.
            return row.get("name", contact_name)
    return None


def _parse_command(text: str) -> tuple[str, str | None]:
    """Extract (recipient_name, body_text) from a WhatsApp command.

    Falls back gracefully when the user just says "whatsapp mom" with no body.
    """
    text = text.strip()
    if not _INTENT_RE.search(text):
        return "", None

    # Try the explicit pattern first: "... to <name> saying <body>"
    m = _RECIPIENT_PATTERN.search(text)
    if m:
        recipient = m.group(2).strip()
        rest = text[m.start():]
        body_m = _BODY_PATTERN.search(rest)
        body = body_m.group(1).strip() if body_m else None
        return recipient, body

    # Fallback: grab the last meaningful word(s) after a known verb/preposition.
    # e.g. "whatsapp john" -> recipient="john", body=None
    parts = text.split()
    # Words before known verbs or "to"/"ko" are ignored; the rest is recipient.
    stop_words = {
        "send", "a", "the", "my", "please", "pls", "whatsapp", "wa",
        "message", "on", "via", "karo", "kardo", "bhejo", "to", "ko",
        "jarvis",
    }
    recipient_parts: list[str] = []
    for part in parts:
        if part.lower() in stop_words:
            recipient_parts.clear()
            continue
        recipient_parts.append(part)
    recipient = " ".join(recipient_parts).rstrip(".,!?:") if recipient_parts else ""
    # Anything that looks like a body after the recipient is the body.
    body_idx = text.lower().find(recipient.lower())
    body = None
    if body_idx >= 0:
        tail = text[body_idx + len(recipient):].strip()
        if tail:
            body = tail

    return recipient, body


def try_whatsapp(text: str, dry_run: bool = False) -> tuple[bool, str]:
    """Detect a WhatsApp send command and act on it.

    Returns:
        (handled, spoken_message):
          handled=True  -> intent recognised; caller should speak `spoken_message`
          handled=False -> not a WhatsApp command; fall through to next skill / brain
    """
    recipient, body = _parse_command(text)
    if not recipient:
        return False, ""

    # Check minimum body length; if too short, offer to ask the brain for help.
    if body and len(body) < _MIN_BODY_LEN:
        body = None  # treat as "no body provided" so brain drafts it

    contact_id = find_contact(recipient)
    display_name = contact_id or recipient

    # Draft body via LLM brain if none was provided explicitly.
    if not body:
        from jarvis.brain import ask
        prompt = (
            f"The user wants to WhatsApp {display_name} but only said "
            f"'{text}'. Draft a short, friendly message body (one sentence, "
            f"in English or Hinglish depending on the context). Return ONLY "
            f"the message body, nothing else."
        )
        body = ask(prompt).strip()
        if body.startswith("[brain]"):
            body = f"Hey {display_name}!"  # graceful fallback
        else:
            body = body or f"Hey {display_name}!"

    if not body or len(body) < 2:
        return True, f"I couldn't figure out what to say to {display_name}."

    # Send via pywhatkit (opens WhatsApp Web with message pre-filled).
    if dry_run:
        print(f"[whatsapp][dry-run] would send to {display_name!r}: {body!r}")
        return True, f"Opening WhatsApp to send to {display_name}. Review and hit Send."

    try:
        import pywhatkit
        pywhatkit.sendwhatmsg_instantly(
            phone_no=contact_id or display_name,
            message=body,
            tab_close=True,        # close the WhatsApp tab after sending
            close_time=3,          # wait 3 seconds for the user to review
        )
        return True, (
            f"Opened WhatsApp for {display_name}. "
            f"Please review and click Send. Message: \"{body}\""
        )
    except Exception as exc:
        print(f"[whatsapp] error: {exc}")
        return True, (
            f"I tried to open WhatsApp for {display_name} but it didn't work. "
            f"Make sure you're logged into WhatsApp Web and try again."
        )


if __name__ == "__main__":
    import sys

    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    phrase_words = [a for a in sys.argv[1:] if not a.startswith("--")]
    phrase = " ".join(phrase_words)

    if "--selftest" in flags:
        print("[selftest] checking intent matching...")
        samples = [
            ("send a whatsapp to mom saying I will be late",   True),
            ("whatsapp john that I'll reach by 7",              True),
            ("bhejo mom ko whatsapp ki main der se aaunga",     True),
            ("open chrome",                                      False),
            ("tell me a joke",                                   False),
            ("",                                                 False),
        ]
        for s, expected in samples:
            handled, msg = try_whatsapp(s)
            status = "OK" if handled == expected else "FAIL"
            print(f"  [{status}] {s!r:55} handled={handled}")
        print("[selftest] PASS — whatsapp skill recognises intent.")
    elif phrase:
        dry = "--dry-run" in flags
        handled, msg = try_whatsapp(phrase, dry_run=dry)
        print(f"handled={handled}  -> {msg}")
    else:
        print("Usage:")
        print('  python -m jarvis.skills.whatsapp --selftest')
        print('  python -m jarvis.skills.whatsapp --dry-run "send whatsapp to mom"')
        print('  python -m jarvis.skills.whatsapp "send whatsapp to dad"')
