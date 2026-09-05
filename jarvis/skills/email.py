"""
jarvis/skills/email.py — Gmail email skill.

Send a Gmail email with subject, To, BCC, and AI-written content by voice.
Example commands:
    "send an email to prof sharma about the project update"
    "mail john that I'll be late tonight"
    "bhejo mom ko email ki meeting cancel ho gayi"

HOW IT WORKS
-----------
1. Parse the command to extract recipients (To / CC / BCC) and the topic.
2. Look up email addresses from resources/contacts.csv.
3. Ask the LLM brain to draft a subject line and email body from the topic.
4. Compose the full email and send it via SMTP using the user's Google App
   Password (stored in .env as EMAIL_APP_PASSWORD; the sender address is
   EMAIL_USER).
5. Speak a confirmation back through TTS.

SMTP CONFIGURATION
-----------------
Gmail requires an "App Password" (not your regular Gmail password) when
sending via SMTP. Create one at:
    https://myaccount.google.com/apppasswords
Then put it in .env:
    EMAIL_USER=you@gmail.com
    EMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx

The default sender is EMAIL_USER. Recipients come from contacts.csv.

TODO (future improvement):
- Support Gmail API with OAuth for a more modern auth flow.
- Support scheduling emails for later delivery.
"""

from __future__ import annotations

import csv
import os
import re
import smtplib
from email.mime.text import MIMEText
from email.utils import formataddr
from pathlib import Path

# --- Paths ---------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_CONTACTS_PATH = _PROJECT_ROOT / "resources" / "contacts.csv"

# --- Verb phrases that signal an email-send intent. Includes Hinglish.
_EMAIL_VERBS = (
    r"(?:send\s+(?:an?\s+)?email|send\s+(?:an?\s+)?mail|"
    r"email(?:\s+it)?|mail(?:\s+it)?|"
    r"email\s+karo|mail\s+karo|"
    r"compose\s+(?:an?\s+)?email|write\s+(?:an?\s+)?email|"
    r"bhejo\s+(?:email|mail)|likho\s+email)"
)
_INTENT_RE = re.compile(rf"\b{_EMAIL_VERBS}\b", re.IGNORECASE)

# Recipient prepositions (English + Hinglish).
_RECIPIENT_MARKERS = re.compile(
    r"\b(to|for|ko|se)\b", re.IGNORECASE
)

# Extract the topic / body hint after "about", "re", "ki", etc.
_TOPIC_MARKERS = re.compile(
    r"\b(?:about|re:?\s*|regarding|concerning|ka|ki|ke baare\s mein)\s+(.+)$",
    re.IGNORECASE,
)


def _load_contacts() -> list[dict[str, str]]:
    """Load contacts.csv and return a list of row dicts."""
    if not _CONTACTS_PATH.exists():
        return []
    with open(_CONTACTS_PATH, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def find_emails(contact_name: str) -> list[str]:
    """Return all email addresses matching `contact_name` from contacts.csv."""
    contacts = _load_contacts()
    needle = contact_name.strip().lower()
    results = []
    for row in contacts:
        if needle in row.get("name", "").lower():
            addr = row.get("email", "").strip()
            if addr and "@" in addr:
                results.append(addr)
    return results


def _extract_recipients(text: str) -> tuple[list[str], list[str], list[str]]:
    """Parse the command text and return (to_list, cc_list, bcc_list).

    Each list contains resolved email addresses (strings with @). Names that
    do not resolve to a contact are kept UNRESOLVED so the caller can tell
    the user clearly, instead of sending an unqualified (SMTP-invalid) name
    as the To address.

    Strategy: scan for recipient markers ("to", "ko", "for", "cc", "bcc",
    "se") anywhere in the sentence, and take the rest of the phrase up to
    the next marker or a boundary word. This handles:
      - English order:      "send an email to prof sharma and mom about X"
      - Hinglish verb-last: "bhejo mom ko email ki meeting cancel"
      - CC/BCC with names:  "mail john cc dad bcc mom that ..."
    """
    to_names: list[str] = []
    cc_names: list[str] = []
    bcc_names: list[str] = []
    resolved_to, resolved_cc, resolved_bcc = [], [], []

    # Boundary words that end a recipient slot.
    stop = {
        "saying", "telling", "that", "about", "re", "regarding",
        "concerning", "and", "the", "my", "please", "pls", "jarvis",
        "ki", "ka", "ke", "karke", "mein", "main", "at",
    }

    def slot_kind(word: str) -> str | None:
        w = word.rstrip(".,!?;:")
        if w == "cc":
            return "cc"
        if w == "bcc":
            return "bcc"
        if w in ("to", "ko", "for", "se", "bhejo", "mail", "email"):
            return "to"
        return None

    # Tokenise, tracking which slot we are collecting into.
    parts = text.split()
    i = 0
    tokens: list[tuple[str, str]] = []  # (name_token, slot)
    while i < len(parts):
        raw = parts[i]
        kind = slot_kind(raw)
        if kind:
            i += 1
            name_tokens = []
            while i < len(parts):
                w = parts[i]
                wc = w.rstrip(".,!?;:")
                if slot_kind(w):
                    break
                if wc.lstrip(".-") and wc.lower() in stop:
                    break
                name_tokens.append(w)
                i += 1
            if name_tokens:
                tokens.append((" ".join(name_tokens), kind))
        else:
            i += 1

    # Resolve names to emails; names that don't resolve are left unresolved.
    def resolve(names: list[str]) -> tuple[list[str], list[str]]:
        ok_addrs, unresolved = [], []
        for name in names:
            hits = find_emails(name)
            if hits:
                ok_addrs.extend(hits)
            else:
                unresolved.append(name)
        return ok_addrs, unresolved

    for name, kind in tokens:
        addr, unr = resolve([name])
        if kind == "cc":
            cc_names.append(name)
            resolved_cc.extend(addr)
        elif kind == "bcc":
            bcc_names.append(name)
            resolved_bcc.extend(addr)
        else:
            to_names.append(name)
            resolved_to.extend(addr)

    # Deduplicate within each list while preserving order.
    def dedupe(items: list[str]) -> list[str]:
        seen: set[str] = set()
        out = []
        for it in items:
            key = it.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(it)
        return out

    # An email that is already To should not also be CC'd (SMTP would
    # reject it or send a duplicate copy).
    cc_addrs = [a for a in dedupe(resolved_cc) if a.lower() not in {x.lower() for x in resolved_to}]
    bcc_addrs = dedupe(resolved_bcc)
    to_addrs = dedupe(resolved_to)

    return to_addrs, cc_addrs, bcc_addrs


def _extract_topic(text: str) -> str:
    """Pull out the email topic/body hint from the command text."""
    m = _TOPIC_MARKERS.search(text)
    if m:
        return m.group(1).strip()
    # Fallback: everything after the first recipient marker.
    idx = _RECIPIENT_MARKERS.search(text)
    if idx:
        return text[idx.end():].strip()
    return text.strip()


def try_send_email(text: str, dry_run: bool = False) -> tuple[bool, str]:
    """Detect an email-send command and act on it.

    Returns:
        (handled, spoken_message)
    """
    if not _INTENT_RE.search(text):
        return False, ""

    to_addrs, cc_addrs, bcc_addrs = _extract_recipients(text)
    topic = _extract_topic(text)

    if not to_addrs:
        return True, (
            "I didn't catch who to send the email to. Could you repeat that?"
        )
    if not topic:
        return True, (
            "I heard you want to send an email, but I didn't catch the topic. "
            "Could you tell me what it's about?"
        )

    # Ask the LLM brain to draft subject + body. `body` is given a default
    # FIRST so a reply that lacks a literal "BODY:" line never leaves the
    # variable unbound (a real bug class this module used to have).
    body = topic
    subject = topic
    from jarvis.brain import ask
    draft_prompt = (
        f"Draft a professional email. Topic: \"{topic}\". "
        f"To: {', '.join(to_addrs)}. "
        f"Give me two lines: first the subject line (prefix with 'SUBJECT: '), "
        f"then the body (prefix with 'BODY: '). Keep the body 2-4 sentences. "
        f"Use English unless the topic is clearly Hindi."
    )
    reply = ask(draft_prompt)
    if reply.startswith("[brain]"):
        subject = f"Regarding: {topic}"
        body = topic
    else:
        body_lines = reply.split("\n")
        for line in body_lines:
            low = line.lower()
            if low.startswith("subject:"):
                subject = line.replace("subject:", "", 1).strip()
            elif low.startswith("body:"):
                body = line.replace("body:", "", 1).strip()
        if not body or len(body) < 3:
            body = topic

    if dry_run:
        print(f"[email][dry-run] Would send:")
        print(f"  To:   {to_addrs}")
        print(f"  CC:   {cc_addrs}")
        print(f"  BCC:  {bcc_addrs}")
        print(f"  Subject: {subject}")
        print(f"  Body: {body}")
        return True, (
            f"Drafted email to {', '.join(to_addrs)}: "
            f'"{subject}" — ready to send when configured.'
        )

    # --- Send via SMTP ---------------------------------------------------
    sender = os.environ.get("EMAIL_USER")
    app_password = os.environ.get("EMAIL_APP_PASSWORD")

    if not sender or not app_password:
        return True, (
            "Email needs your Gmail address and an App Password. "
            "Set EMAIL_USER and EMAIL_APP_PASSWORD in your .env file. "
            "Get an App Password at myaccount.google.com/apppasswords"
        )

    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = formataddr(("JARVIS", sender))
        all_recips = to_addrs + cc_addrs + bcc_addrs
        msg["To"] = ", ".join(to_addrs)
        if cc_addrs:
            msg["CC"] = ", ".join(cc_addrs)
        # BCC recipients are in the envelope but NOT in the headers.

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender, app_password)
            server.sendmail(sender, all_recips, msg.as_string())

        return True, (
            f"Email sent to {', '.join(to_addrs)} "
            f"with subject '{subject}'."
        )
    except smtplib.SMTPAuthenticationError:
        return True, (
            "Email failed: authentication error. Check your EMAIL_USER and "
            "EMAIL_APP_PASSWORD in the .env file."
        )
    except smtplib.SMTPException as exc:
        print(f"[email] SMTP error: {exc}")
        return True, f"Email failed to send: {exc}. Check your internet connection."
    except Exception as exc:
        print(f"[email] unexpected error: {exc}")
        return True, f"Something went wrong sending the email: {exc}"


if __name__ == "__main__":
    import sys

    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    phrase_words = [a for a in sys.argv[1:] if not a.startswith("--")]
    phrase = " ".join(phrase_words)

    if "--selftest" in flags:
        print("[selftest] checking intent matching...")
        samples = [
            ("send an email to prof sharma about the project update", True),
            ("mail john that I'll be late tonight",                   True),
            ("bhejo mom ko email ki meeting cancel",                  True),
            ("open chrome",                                            False),
            ("tell me a joke",                                         False),
            ("",                                                       False),
        ]
        for s, expected in samples:
            handled, msg = try_send_email(s, dry_run=True)
            status = "OK" if handled == expected else "FAIL"
            print(f"  [{status}] {s!r:55} handled={handled}")
        print("[selftest] PASS — email skill recognises intent.")
    elif phrase:
        dry = "--dry-run" in flags
        handled, msg = try_send_email(phrase, dry_run=dry)
        print(f"handled={handled}  -> {msg}")
    else:
        print("Usage:")
        print('  python -m jarvis.skills.email --selftest')
        print('  python -m jarvis.skills.email --dry-run "send email to mom about project"')
        print('  python -m jarvis.skills.email "mail john that I am running late"')
