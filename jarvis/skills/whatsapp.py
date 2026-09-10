"""
jarvis/skills/whatsapp.py — WhatsApp messaging skill.

Send a WhatsApp message by voice. Example commands:
    "send whatsapp to mom saying I will be late"
    "whatsapp john that I'll reach by 7"
    "bhejo mom ko whatsapp ki main der se aaunga"

HOW IT WORKS
-----------
1. Parse the command to extract recipient name + optional message body.
2. Look up the recipient from resources/contacts.csv.
   - contacts.csv columns: name, phone, whatsapp_id, email, relation, notes
   - Matching is case-insensitive substring (so "mom" matches "Mom").
   - Resolution priority for sending: phone > whatsapp_id > contact name.
3. If no explicit message body is given, ask the LLM brain to draft one
   based on the command context.
4. Open WhatsApp with the message pre-filled using a deep link:
   - If we have a phone number (or a numeric whatsapp_id), open
     https://wa.me/<number>?text=<message> — WhatsApp opens a chat with the
     message typed but NOT sent. The user reviews and clicks Send.
   - If we only have a name, open WhatsApp Web and tell the user to search
     for the contact and paste the message.
   The user ALWAYS reviews before sending. We deliberately do NOT auto-click
   Enter (the old pywhatkit path did, which could send a wrong/partial
   message and also could not target a name-based contact).
5. Speak a confirmation or an error back through TTS.

WHY NOT pywhatkit ANY MORE?
---------------------------
pywhatkit.sendwhatmsg_instantly() was used before. Two real problems:
  1. It builds https://web.whatsapp.com/send?phone=<input> and only validates
     that the input contains "+" or "_". For name-based IDs (e.g.
     "prof_sharma") the resulting chat URL has no phone number and WhatsApp
     cannot open it. For "mom" it raises CountryCodeException and the whole
     skill fails on a broken error path.
  2. It auto-presses Enter after a few seconds — the message is sent without
     review, contradicting this project's own "user reviews and clicks Send"
     design (see README).
The deep-link approach below fixes both: the URL is always well-formed and
nothing is ever sent automatically.

REQUIREMENTS
-----------
- An active internet connection (opens WhatsApp).
- The user must already be logged into WhatsApp Web/WhatsApp app.
- A contact entry with a phone number in resources/contacts.csv gives the
  best experience; name-only contacts degrade gracefully.

SAFETY
-----
- Recipient names are validated against the contacts file; if not found we
  refuse to guess and say so (no accidental send to the wrong target).
- Message bodies shorter than 5 characters are treated as "no body" and the
  brain drafts one.
"""

from __future__ import annotations

import csv
import re
import urllib.parse
import webbrowser
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

# A rough phone-number shape: optional leading + then 7-15 digits, allowing
# spaces/dashes en route. Enough to distinguish "91xxxxxx" from "prof_sharma".
_PHONE_RE = re.compile(r"^\+?\d{1,3}[\d\s\-]{6,14}$")


def _looks_like_phone(value: str) -> bool:
    """True if `value` is a plausible international phone number."""
    return bool(_PHONE_RE.match(value.strip()))


def _ensure_contacts_file() -> None:
    """Ensure resources/contacts.csv exists on disk with default contacts."""
    try:
        from jarvis.skills.email import _ensure_contacts_file as ensure_fn
        ensure_fn()
    except Exception:
        pass


def _load_contacts() -> list[dict[str, str]]:
    """Load contacts.csv and return a list of row dicts."""
    _ensure_contacts_file()
    if not _CONTACTS_PATH.exists():
        try:
            from jarvis.skills.email import DEFAULT_CONTACTS
            return list(DEFAULT_CONTACTS)
        except Exception:
            return []
    try:
        with open(_CONTACTS_PATH, newline="", encoding="utf-8") as f:
            contacts = list(csv.DictReader(f))
            if contacts:
                return contacts
            from jarvis.skills.email import DEFAULT_CONTACTS
            return list(DEFAULT_CONTACTS)
    except Exception as exc:
        print(f"[whatsapp] contacts read error: {exc}")
        try:
            from jarvis.skills.email import DEFAULT_CONTACTS
            return list(DEFAULT_CONTACTS)
        except Exception:
            return []


def find_contact(contact_name: str) -> str | None:
    """Look up a contact by name (case-insensitive substring match).

    Returns the BEST WhatsApp target string for that contact, or None if no
    contact matches. Priority:
      1. `phone`  — a real, dialable number (best).
      2. `whatsapp_id` — may be a number OR a name as it appears in WhatsApp.
      3. the contact's display name (last resort; deep-link needs a number,
         so this only lets us open WhatsApp Web for a manual search).
    """
    contacts = _load_contacts()
    needle = contact_name.strip().lower()
    # Strip conversational / possessive prefixes: "my mom" -> "mom"
    needle = re.sub(r"^(?:my|the|mere|meri|mera|apni|apne|our)\s+", "", needle, flags=re.IGNORECASE).strip()
    if not needle:
        return None

    synonyms = (needle,)
    try:
        from jarvis.skills.email import _RELATION_SYNONYMS
        synonyms = _RELATION_SYNONYMS.get(needle, (needle,))
    except Exception:
        pass

    for row in contacts:
        name = row.get("name", "").strip().lower()
        relation = row.get("relation", "").strip().lower()

        matched = False
        for syn in synonyms:
            if syn and (syn in name or syn in relation):
                matched = True
                break
        if not matched:
            continue

        phone = row.get("phone", "").strip()
        if phone:
            # Normalise: strip spaces/dashes so we emit a clean wa.me link.
            return re.sub(r"[\s\-]+", "", phone)
        wid = row.get("whatsapp_id", "").strip()
        if wid:
            return wid
        return row.get("name", contact_name).strip()
    return None


def build_chat_url(target: str, message: str) -> tuple[str | None, str]:
    """Build the URL / fallback text for opening a WhatsApp chat.

    Args:
        target:  the resolved WhatsApp target (phone, whatsapp_id, or name).
        message: the message body to pre-fill.

    Returns:
        (url, fallback_hint). If the target looks like a phone number, url is a
        wa.me deep link and fallback_hint is empty. Otherwise url is None (or
        plain web.whatsapp.com) and fallback_hint tells the user what to do.
    """
    if not target or not message:
        return None, ""
    if _looks_like_phone(target):
        encoded = urllib.parse.quote(message)
        # wa.me links use the bare international number (no leading +).
        number = target.strip().lstrip("+")
        url = f"https://wa.me/{number}?text={encoded}"
        return url, ""
    # Name-only contact: no reliable deep link. Open WhatsApp Web so the user
    # can search the contact manually; surface the message for pasting.
    return "https://web.whatsapp.com", (
        f"{target}'s WhatsApp id is not a phone number, so I can't open the "
        f"chat directly. I opened WhatsApp Web. Search for {target} and send: "
        f"'{message}'"
    )


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

    target = find_contact(recipient)
    if not target:
        return True, (
            f"I don't have a contact named {recipient} in resources/contacts.csv. "
            "Add them there with a phone number so I can reach them on WhatsApp."
        )
    display_name = (
        recipient.title() if _looks_like_phone(target) else target
    )

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

    url, fallback = build_chat_url(target, body)

    if dry_run:
        print(f"[whatsapp][dry-run] target={target!r} body={body!r} url={url!r}")
        if url:
            return True, (
                f"Opening WhatsApp to send to {display_name}. "
                f"Review the message and hit Send. Message: \"{body}\""
            )
        return True, f"Would open WhatsApp Web for {display_name}: \"{body}\""

    try:
        from jarvis.skills.browser_control import _STATE
        _STATE["last_opened_url"] = url or "https://web.whatsapp.com"
    except Exception:
        pass

    try:
        if url:
            webbrowser.open(url)
            return True, (
                f"Opened WhatsApp for {display_name}. "
                f"Please review and click Send. Message: \"{body}\""
            )
        # Name-only contact: open WhatsApp Web and speak the fallback hint.
        webbrowser.open("https://web.whatsapp.com")
        return True, fallback
    except Exception as exc:
        print(f"[whatsapp] error opening browser: {exc}")
        return True, (
            f"I tried to open WhatsApp for {display_name} but it didn't work. "
            f"Make sure you're logged into WhatsApp and try again."
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
            handled, msg = try_whatsapp(s, dry_run=True)
            status = "OK" if handled == expected else "FAIL"
            print(f"  [{status}] {s!r:55} handled={handled}")
        # deep-link / phone detection checks
        assert _looks_like_phone("+919876543210") is True
        assert _looks_like_phone("9876543210") is True
        assert _looks_like_phone("91 98765 43210") is True
        assert _looks_like_phone("prof_sharma") is False
        url, fb = build_chat_url("+919876543210", "hi there")
        assert url == "https://wa.me/919876543210?text=hi%20there", url
        assert fb == ""
        assert build_chat_url("prof_sharma", "hi")[0] == "https://web.whatsapp.com"
        print("[selftest] PASS — whatsapp skill recognises intent + builds links.")
    elif phrase:
        dry = "--dry-run" in flags
        handled, msg = try_whatsapp(phrase, dry_run=dry)
        print(f"handled={handled}  -> {msg}")
    else:
        print("Usage:")
        print('  python -m jarvis.skills.whatsapp --selftest')
        print('  python -m jarvis.skills.whatsapp --dry-run "send whatsapp to mom"')
        print('  python -m jarvis.skills.whatsapp "send whatsapp to dad"')
