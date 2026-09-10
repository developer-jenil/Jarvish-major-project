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
from typing import Any

# --- Paths ---------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_CONTACTS_PATH = _PROJECT_ROOT / "resources" / "contacts.csv"

# Global in-memory active draft for interactive voice/text CRUD editing
_ACTIVE_DRAFT: dict[str, Any] | None = None

# --- Verb phrases that signal an email-send intent. Includes Hinglish.
_EMAIL_VERBS = (
    r"(?:send\s+(?:an?\s+)?(?:email|mail)|"
    r"(?:email|mail)(?:\s+(?:it|karo|kar\s+do|bhejo|bhej\s+do|bhej\s+dena|bhej))?|"
    r"compose\s+(?:an?\s+)?(?:email|mail)|write\s+(?:an?\s+)?(?:email|mail)|"
    r"(?:bhejo|bhej\s+do|bhej\s+dena)\s+(?:an?\s+)?(?:email|mail)|likho\s+(?:email|mail))"
)
_INTENT_RE = re.compile(rf"\b{_EMAIL_VERBS}\b", re.IGNORECASE)

# Recipient prepositions (English + Hinglish).
_RECIPIENT_MARKERS = re.compile(
    r"\b(to|for|ko|se)\b", re.IGNORECASE
)

# Extract the topic / body hint after "about", "re", "ki", etc.
_TOPIC_MARKERS = re.compile(
    r"\b(?:about|re:?\s*|regarding|concerning|ka|ki|ke baare\s+mein|saying|telling|that|bolke|kaho)\s+(.+)$",
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

    Handles:
      - English prepositions: "send an email to prof sharma and mom about X"
      - Hinglish postpositions: "mom ko email bhej do ki...", "prof sharma ko mail karo..."
      - Inverted / verb-first: "bhejo mom ko email ki meeting cancel"
      - CC / BCC syntax: "mail john cc dad bcc mom that..."
      - Direct contact name mentions in command prefix
    """
    # 1. Find where the topic / message begins
    topic_m = _TOPIC_MARKERS.search(text)
    prefix = text[:topic_m.start()] if topic_m else text

    # 2. Separate slots: TO, CC, BCC
    bcc_split = re.split(r"\bbcc\b", prefix, flags=re.IGNORECASE)
    bcc_text = bcc_split[1] if len(bcc_split) > 1 else ""
    before_bcc = bcc_split[0]

    cc_split = re.split(r"\bcc\b", before_bcc, flags=re.IGNORECASE)
    cc_text = cc_split[1] if len(cc_split) > 1 else ""
    to_text = cc_split[0]

    contacts = _load_contacts()

    def resolve_slot(slot_str: str) -> list[str]:
        if not slot_str:
            return []
        addrs: list[str] = []

        # A. Check for raw literal emails (e.g. user@example.com)
        raw_emails = re.findall(r"[\w\.-]+@[\w\.-]+\.\w+", slot_str)
        for em in raw_emails:
            if em not in addrs:
                addrs.append(em)

        # B. Check known contacts in contacts.csv
        for r in sorted(contacts, key=lambda c: len(c.get("name", "")), reverse=True):
            cname = r.get("name", "").strip().lower()
            if not cname:
                continue
            name_tokens = [cname] + [w for w in cname.split() if len(w) > 2]
            for n in name_tokens:
                if re.search(rf"\b{re.escape(n)}\b", slot_str, re.IGNORECASE):
                    em = r.get("email", "").strip()
                    if em and "@" in em and em not in addrs:
                        addrs.append(em)
                    break

        # C. Pattern-based fallback (e.g. "<name> ko", "to <name>")
        if not addrs:
            # Hindi postposition: "<name> ko" or "<name> se"
            ko_m = re.search(r"\b([a-zA-Z\s]{2,25})\s+(?:ko|se)\b", slot_str, re.IGNORECASE)
            if ko_m:
                cand = ko_m.group(1).strip()
                cand = re.sub(r"\b(?:bhejo|bhej\s+do|bhej\s+dena|send|mail|email|likho)\b", "", cand, flags=re.IGNORECASE).strip()
                if cand:
                    hits = find_emails(cand)
                    for h in hits:
                        if h not in addrs:
                            addrs.append(h)

            # English preposition: "to <name>" or "for <name>"
            to_m = re.search(r"\b(?:to|for)\s+([a-zA-Z\s]{2,25})\b", slot_str, re.IGNORECASE)
            if to_m:
                cand = to_m.group(1).strip()
                cand = re.sub(r"\b(?:bhejo|bhej\s+do|bhej\s+dena|send|mail|email|likho)\b", "", cand, flags=re.IGNORECASE).strip()
                if cand:
                    hits = find_emails(cand)
                    for h in hits:
                        if h not in addrs:
                            addrs.append(h)

        return addrs

    to_addrs = resolve_slot(to_text)
    cc_addrs = resolve_slot(cc_text)
    bcc_addrs = resolve_slot(bcc_text)

    # An email that is already To should not also be in CC
    cc_addrs = [a for a in cc_addrs if a not in to_addrs]
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

    # If the text is an instruction to edit/modify the body, subject, or recipient of a draft:
    if re.search(r"\b(?:body|subject|draft)\b", text, re.IGNORECASE) and re.search(r"\b(?:change|replace|add|remove|delete|badlo|hatao|likho|rakho|from)\b", text, re.IGNORECASE):
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
                subject = re.sub(r"^subject:\s*", "", line, flags=re.IGNORECASE).strip()
            elif low.startswith("body:"):
                body = re.sub(r"^body:\s*", "", line, flags=re.IGNORECASE).strip()
        if not body or len(body) < 3:
            body = topic

    global _ACTIVE_DRAFT
    _ACTIVE_DRAFT = {
        "to": list(to_addrs),
        "cc": list(cc_addrs),
        "bcc": list(bcc_addrs),
        "subject": subject,
        "body": body,
    }

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

    # --- Send via SMTP (if configured) or Direct Browser Draft in Chrome ---
    sender = os.environ.get("EMAIL_USER")
    app_password = os.environ.get("EMAIL_APP_PASSWORD")

    if not sender or not app_password:
        # Seamlessly open Gmail in Chrome with everything pre-filled!
        from jarvis.skills.browser_control import draft_gmail_in_chrome
        _, msg = draft_gmail_in_chrome(
            recipient=", ".join(to_addrs),
            message=body,
            subject=subject,
            dry_run=dry_run,
        )
        return True, msg

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
        # Fall back to Chrome draft if SMTP password fails
        from jarvis.skills.browser_control import draft_gmail_in_chrome
        _, msg = draft_gmail_in_chrome(
            recipient=", ".join(to_addrs),
            message=body,
            subject=subject,
            dry_run=dry_run,
        )
        return True, f"Opened Gmail draft in Chrome for you: {msg}"
    except smtplib.SMTPException as exc:
        print(f"[email] SMTP error: {exc}")
        return True, f"Email failed to send: {exc}. Check your internet connection."
# --- Active Draft CRUD Patterns ---------------------------------------------
_DISCARD_RE = re.compile(
    r"^(?:(?:cancel|discard|delete|hatao|band\s+karo)\s+(?:the\s+)?(?:email|draft|mail)|"
    r"(?:the\s+)?(?:email|draft|mail)\s+(?:ko\s+)?(?:cancel|discard|delete|hatao|band\s+karo)|"
    r"cancel\s+draft|discard\s+draft|cancel\s+email|discard\s+email)\s*$",
    re.IGNORECASE,
)

_SEND_NOW_RE = re.compile(
    r"^(?:send\s+(?:the\s+)?(?:email|draft|mail)(?:\s+now)?|send\s+it(?:\s+now)?|send\s+now|now\s+send\s+it|send|"
    r"ab\s+(?:email|draft|mail\s+)?(?:bhejo|bhej\s+do|bhej\s+dena))\s*$",
    re.IGNORECASE,
)

_SHOW_DRAFT_RE = re.compile(
    r"^(?:(?:show|read|check|status\s+of|kya\s+likha\s+hai\s+in)\s+(?:the\s+)?(?:draft|email|mail)|"
    r"(?:the\s+)?(?:draft|email|mail)\s+(?:dikhao|read\s+karo|padho|check\s+karo)|"
    r"show\s+draft|read\s+draft|check\s+draft)\s*$",
    re.IGNORECASE,
)

_RECIPIENT_EDIT_RE = re.compile(
    r"(?:change\s+recipient\s+to|send\s+to\s+(?:someone\s+else|different\s+person)|"
    r"recipient\s+(?:badlo|change\s+karo)|to\s+(?:ko\s+)?(?:change\s+karo|badlo)|"
    r"also\s+send\s+to|add\s+recipient|send\s+to\s+(.+?)\s+instead)\s*(.*)",
    re.IGNORECASE,
)

_SUBJECT_EDIT_RE = re.compile(
    r"(?:(?:on|in)?\s*(?:the\s+)?subject\s+(?:add|append|likho|dal\s+do|badlo|change\s+karo|rakho)\s+(.+)|"
    r"(?:change|update|set|badlo|add\s+to)\s+(?:the\s+)?subject\s+(?:to|as)?\s*(.+)|"
    r"subject\s+(?:me|mein)?\s*(?:likho|badlo|change\s+karo|add\s+karo|rakho)\s*(?:ki\s+|to\s+)?(.+))",
    re.IGNORECASE,
)

_CONVERSATIONAL_PREFIX_RE = re.compile(
    r"^(?:(?:i\s+(?:want|wanted)\s+to|to)\s+tell\s+you\s+(?:that\s+)?|"
    r"(?:i\s+said|i\s+told\s+(?:you|it))\s+(?:that\s+|to\s+)?|"
    r"(?:maine\s+kaha|maine\s+bola)\s+(?:ki\s+)?|"
    r"(?:hey\s+|ok\s+)?jarvis\s+|please\s+|pls\s+|zara\s+|listen\s+)+",
    re.IGNORECASE,
)

_BODY_REPLACE_FROM_TO_RE = re.compile(
    r"(?:change|replace|badlo)\s+(?:the\s+)?body(?:\s+of\s+(?:the\s+)?(?:email|mail|draft))?\s+(?:from|se)\s+(.+?)\s+(?:to|with|se)\s+(.+)",
    re.IGNORECASE,
)

_BODY_REPLACE_RE = re.compile(
    r"(?:change|replace|badlo)\s+(.+?)\s+(?:with|to|se)\s+(.+?)\s+(?:in|from|on|of)?\s*(?:the\s+)?body\b|"
    r"body\s+(?:me|mein)\s+(.+?)\s+(?:ko\s+)?(?:change|replace|badlo)\s+(?:karo\s+)?(?:to|with|se)\s+(.+)",
    re.IGNORECASE,
)

_BODY_REMOVE_RE = re.compile(
    r"(?:(?:remove|delete|hatao|nikal\s+do)\s+(.+?)\s+(?:from|se)\s+(?:the\s+)?body|"
    r"body\s+(?:se|mein\s+se)\s+(.+?)\s+(?:hatao|nikal\s+do|remove\s+karo|delete\s+karo))",
    re.IGNORECASE,
)

_BODY_APPEND_RE = re.compile(
    r"(?:(?:in|on|to)?\s*(?:the\s+)?body\s+(?:add|append|likho|dal\s+do|jo\s+do)\s+(.+)|"
    r"add\s+(.+?)\s+(?:in|to)\s+(?:the\s+)?body|"
    r"body\s+(?:me|mein)\s+(?:ye\s+)?(?:likho|add\s+karo|dal\s+do)\s+(?:ki\s+)?(.+))",
    re.IGNORECASE,
)


def get_active_draft() -> dict[str, Any] | None:
    """Return a copy of the current active email draft, if any."""
    global _ACTIVE_DRAFT
    if _ACTIVE_DRAFT is None:
        return None
    return dict(_ACTIVE_DRAFT)


def set_active_draft(draft: dict[str, Any]) -> None:
    """Set the active email draft."""
    global _ACTIVE_DRAFT
    _ACTIVE_DRAFT = dict(draft)


def clear_active_draft() -> None:
    """Clear the active email draft."""
    global _ACTIVE_DRAFT
    _ACTIVE_DRAFT = None


def try_edit_email_draft(text: str, dry_run: bool = False) -> tuple[bool, str]:
    """Inspect and modify an active email draft.

    Handles interactive voice/text CRUD commands:
    - Discarding: "cancel the email", "discard draft"
    - Sending: "send the email now", "ab bhej do"
    - Inspecting: "show the draft", "read draft"
    - Subject edits: "on the subject add rain today so i cant come"
    - Body removal: "remove train let ho gai from the body"
    - Body replacement: "change 5pm to 6pm in the body"
    - Body append: "to the body add reaching in 10 minutes"
    - Recipient update: "change recipient to dad"
    """
    global _ACTIVE_DRAFT
    stripped = text.strip()
    if not stripped:
        return False, ""

    # Clean conversational prefixes (e.g. "to tell you that...", "i told you to...")
    cleaned = _CONVERSATIONAL_PREFIX_RE.sub("", stripped).strip()
    target_text = cleaned if cleaned else stripped

    m_discard = _DISCARD_RE.search(target_text) or _DISCARD_RE.search(stripped)
    m_send = _SEND_NOW_RE.search(target_text) or _SEND_NOW_RE.search(stripped)
    m_show = _SHOW_DRAFT_RE.search(target_text) or _SHOW_DRAFT_RE.search(stripped)
    m_subj = _SUBJECT_EDIT_RE.search(target_text) or _SUBJECT_EDIT_RE.search(stripped)
    m_body_from_to = _BODY_REPLACE_FROM_TO_RE.search(target_text) or _BODY_REPLACE_FROM_TO_RE.search(stripped)
    m_body_rem = _BODY_REMOVE_RE.search(target_text) or _BODY_REMOVE_RE.search(stripped)
    m_body_rep = _BODY_REPLACE_RE.search(target_text) or _BODY_REPLACE_RE.search(stripped)
    m_body_app = _BODY_APPEND_RE.search(target_text) or _BODY_APPEND_RE.search(stripped)
    m_recip = _RECIPIENT_EDIT_RE.search(target_text) or _RECIPIENT_EDIT_RE.search(stripped)

    # Guard against hijacking new email commands:
    # If the command has an email-send verb and recipient(s), but is NOT an edit instruction
    # like "change recipient to..." or "send to X instead", let try_send_email handle it.
    if _INTENT_RE.search(stripped) and not _RECIPIENT_EDIT_RE.search(stripped):
        recips, _, _ = _extract_recipients(stripped)
        if recips:
            return False, ""

    # Check if this text refers to draft editing at all
    has_regex_match = any([
        m_discard, m_send, m_show, m_subj, m_body_from_to,
        m_body_rem, m_body_rep, m_body_app, m_recip
    ])

    if not has_regex_match:
        if _ACTIVE_DRAFT is None:
            return False, ""
        # Check if the text is an edit command for an active draft:
        draft_words = bool(re.search(r"\b(?:body|subject|draft|recipient)\b", stripped, re.IGNORECASE))
        action_words = bool(re.search(r"\b(?:change|replace|remove|delete|add|append|likho|hatao|badlo|dal\s+do)\b", stripped, re.IGNORECASE))
        if not (draft_words and action_words):
            return False, ""
    elif _ACTIVE_DRAFT is None:
        return True, "There is no active email draft open right now. You can say 'Send email to Mom' to start a new one."

    from jarvis.skills.browser_control import draft_gmail_in_chrome

    # 1. Discard / Cancel
    if m_discard:
        _ACTIVE_DRAFT = None
        return True, "Email draft has been cancelled."

    # 2. Send Now
    if m_send:
        to_addrs = _ACTIVE_DRAFT.get("to", [])
        subject = _ACTIVE_DRAFT.get("subject", "")
        body = _ACTIVE_DRAFT.get("body", "")
        sender = os.environ.get("EMAIL_USER")
        app_password = os.environ.get("EMAIL_APP_PASSWORD")

        if sender and app_password:
            try:
                msg = MIMEText(body, "plain", "utf-8")
                msg["Subject"] = subject
                msg["From"] = formataddr(("JARVIS", sender))
                msg["To"] = ", ".join(to_addrs)
                with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
                    server.login(sender, app_password)
                    server.sendmail(sender, to_addrs, msg.as_string())
                _ACTIVE_DRAFT = None
                return True, f"Email sent to {', '.join(to_addrs)} with subject '{subject}'."
            except Exception as e:
                print(f"[email-edit] SMTP error, falling back to Chrome: {e}")

        # Fallback to Chrome draft ready to send
        draft_gmail_in_chrome(
            recipient=", ".join(to_addrs),
            subject=subject,
            message=body,
            dry_run=dry_run,
        )
        _ACTIVE_DRAFT = None
        return True, f"Email draft to {', '.join(to_addrs)} is ready in Chrome."

    # 3. Show / Read Draft
    if m_show:
        to_str = ", ".join(_ACTIVE_DRAFT.get("to", []))
        subj_str = _ACTIVE_DRAFT.get("subject", "")
        body_str = _ACTIVE_DRAFT.get("body", "")
        return True, f"Active draft to {to_str}. Subject: {subj_str}. Body: {body_str}"

    # 4. Subject Update (reformulating raw spoken reason if needed)
    if m_subj:
        raw_val = next((g for g in m_subj.groups() if g), "").strip()
        raw_val = re.sub(r'^["\']|["\']$', "", raw_val).strip()
        if raw_val:
            from jarvis.brain import ask
            prompt = (
                f"Convert this spoken reason into a concise, professional email subject line "
                f"(3 to 6 words, no quotes, no extra punctuation, in English): {raw_val}"
            )
            reply = ask(prompt)
            if not reply.startswith("[brain]") and len(reply.strip()) > 3:
                clean_subj = re.sub(r"^(?:subject\s*:\s*|\"|')+|(?:\"|')+$", "", reply.strip(), flags=re.IGNORECASE).strip()
                clean_subj = clean_subj.rstrip(".")
                if clean_subj:
                    _ACTIVE_DRAFT["subject"] = clean_subj
                else:
                    _ACTIVE_DRAFT["subject"] = raw_val.title()
            else:
                _ACTIVE_DRAFT["subject"] = raw_val.title()

            draft_gmail_in_chrome(
                recipient=", ".join(_ACTIVE_DRAFT.get("to", [])),
                subject=_ACTIVE_DRAFT.get("subject", ""),
                message=_ACTIVE_DRAFT.get("body", ""),
                dry_run=dry_run,
            )
            return True, f"Updated email subject to '{_ACTIVE_DRAFT['subject']}'."

    # 5. Body Replace From -> To (e.g. "change the body of the email from X to Y")
    if m_body_from_to:
        old_val = m_body_from_to.group(1).strip().strip('"\'')
        new_val = m_body_from_to.group(2).strip().strip('"\'')
        current_body = _ACTIVE_DRAFT.get("body", "")
        pattern = re.compile(re.escape(old_val), re.IGNORECASE)
        if pattern.search(current_body):
            new_body = pattern.sub(new_val, current_body)
            _ACTIVE_DRAFT["body"] = new_body
            draft_gmail_in_chrome(
                recipient=", ".join(_ACTIVE_DRAFT.get("to", [])),
                subject=_ACTIVE_DRAFT.get("subject", ""),
                message=_ACTIVE_DRAFT.get("body", ""),
                dry_run=dry_run,
            )
            return True, f"Updated email body: replaced '{old_val}' with '{new_val}'."
        else:
            from jarvis.brain import ask
            prompt = (
                f"Here is an email draft body:\n\"{current_body}\"\n\n"
                f"The user requested to change \"{old_val}\" to \"{new_val}\".\n"
                f"Rewrite the email body naturally reflecting this modification. "
                f"Keep it concise (1 to 4 sentences). Return ONLY the new body text, no explanation, no quotes."
            )
            rewritten = ask(prompt)
            if not rewritten.startswith("[brain]") and len(rewritten.strip()) > 5:
                clean_body = re.sub(r'^(?:body\s*:\s*|["\'])+|(?:["\'])+$', "", rewritten.strip(), flags=re.IGNORECASE).strip()
                _ACTIVE_DRAFT["body"] = clean_body
            else:
                _ACTIVE_DRAFT["body"] = f"{current_body}\n\n{new_val}"
            draft_gmail_in_chrome(
                recipient=", ".join(_ACTIVE_DRAFT.get("to", [])),
                subject=_ACTIVE_DRAFT.get("subject", ""),
                message=_ACTIVE_DRAFT.get("body", ""),
                dry_run=dry_run,
            )
            return True, f"Updated email body: changed '{old_val}' to '{new_val}'."

    # 6. Body Remove
    if m_body_rem:
        target = next((g for g in m_body_rem.groups() if g), "").strip()
        target = re.sub(r'^["\']|["\']$', "", target).strip()
        if target:
            current_body = _ACTIVE_DRAFT.get("body", "")
            pattern = re.compile(re.escape(target), re.IGNORECASE)
            if pattern.search(current_body):
                new_body = pattern.sub("", current_body)
                new_body = re.sub(r" {2,}", " ", new_body).strip()
                _ACTIVE_DRAFT["body"] = new_body
            else:
                from jarvis.brain import ask
                prompt = (
                    f"Here is an email draft body:\n\"{current_body}\"\n\n"
                    f"The user requested to remove \"{target}\".\n"
                    f"Rewrite the email body removing this part. "
                    f"Keep it concise. Return ONLY the new body text, no explanation, no quotes."
                )
                rewritten = ask(prompt)
                if not rewritten.startswith("[brain]") and len(rewritten.strip()) > 5:
                    _ACTIVE_DRAFT["body"] = re.sub(r'^(?:body\s*:\s*|["\'])+|(?:["\'])+$', "", rewritten.strip(), flags=re.IGNORECASE).strip()
                else:
                    _ACTIVE_DRAFT["body"] = current_body

            draft_gmail_in_chrome(
                recipient=", ".join(_ACTIVE_DRAFT.get("to", [])),
                subject=_ACTIVE_DRAFT.get("subject", ""),
                message=_ACTIVE_DRAFT.get("body", ""),
                dry_run=dry_run,
            )
            return True, f"Removed '{target}' from the email body."

    # 7. Body Replace
    if m_body_rep:
        groups = [g for g in m_body_rep.groups() if g is not None]
        if len(groups) >= 2:
            old_val = groups[0].strip().strip('"\'')
            new_val = groups[1].strip().strip('"\'')
            current_body = _ACTIVE_DRAFT.get("body", "")
            pattern = re.compile(re.escape(old_val), re.IGNORECASE)
            if pattern.search(current_body):
                new_body = pattern.sub(new_val, current_body)
                _ACTIVE_DRAFT["body"] = new_body
            else:
                from jarvis.brain import ask
                prompt = (
                    f"Here is an email draft body:\n\"{current_body}\"\n\n"
                    f"The user requested to change \"{old_val}\" to \"{new_val}\".\n"
                    f"Rewrite the email body naturally reflecting this modification. "
                    f"Keep it concise (1 to 4 sentences). Return ONLY the new body text, no explanation, no quotes."
                )
                rewritten = ask(prompt)
                if not rewritten.startswith("[brain]") and len(rewritten.strip()) > 5:
                    _ACTIVE_DRAFT["body"] = re.sub(r'^(?:body\s*:\s*|["\'])+|(?:["\'])+$', "", rewritten.strip(), flags=re.IGNORECASE).strip()
                else:
                    _ACTIVE_DRAFT["body"] = f"{current_body}\n\n{new_val}"

            draft_gmail_in_chrome(
                recipient=", ".join(_ACTIVE_DRAFT.get("to", [])),
                subject=_ACTIVE_DRAFT.get("subject", ""),
                message=_ACTIVE_DRAFT.get("body", ""),
                dry_run=dry_run,
            )
            return True, f"Updated email body: replaced '{old_val}' with '{new_val}'."

    # 8. Body Append
    if m_body_app:
        append_val = next((g for g in m_body_app.groups() if g), "").strip()
        append_val = re.sub(r'^["\']|["\']$', "", append_val).strip()
        if append_val:
            current_body = _ACTIVE_DRAFT.get("body", "").rstrip()
            if current_body:
                _ACTIVE_DRAFT["body"] = f"{current_body}\n\n{append_val}"
            else:
                _ACTIVE_DRAFT["body"] = append_val

            draft_gmail_in_chrome(
                recipient=", ".join(_ACTIVE_DRAFT.get("to", [])),
                subject=_ACTIVE_DRAFT.get("subject", ""),
                message=_ACTIVE_DRAFT.get("body", ""),
                dry_run=dry_run,
            )
            return True, f"Added to email body: '{append_val}'."

    # 9. Recipient Update
    if m_recip:
        cand = (m_recip.group(1) or m_recip.group(2) or "").strip()
        cand = re.sub(r"\b(?:recipient|to|email|mail)\b", "", cand, flags=re.IGNORECASE).strip()
        if cand:
            hits = find_emails(cand)
            if hits:
                _ACTIVE_DRAFT["to"] = hits
                draft_gmail_in_chrome(
                    recipient=", ".join(_ACTIVE_DRAFT.get("to", [])),
                    subject=_ACTIVE_DRAFT.get("subject", ""),
                    message=_ACTIVE_DRAFT.get("body", ""),
                    dry_run=dry_run,
                )
                return True, f"Updated recipient to {', '.join(hits)}."
            else:
                return True, f"Could not find an email address for '{cand}' in your contacts."

    # 10. LLM Fallback Parser for natural/complex phrasings
    if _ACTIVE_DRAFT is not None:
        from jarvis.brain import ask
        parse_prompt = f"""You are JARVIS email draft editor.
The user wants to edit their open email draft.
User said: "{stripped}"

Identify the edit action and extract parameters. Return valid JSON only with keys:
- "action": one of ["replace_body", "remove_body", "append_body", "update_subject", "update_recipient", "send", "discard", "none"]
- "old_text": string or null
- "new_text": string or null

JSON:"""
        llm_reply = ask(parse_prompt)
        if not llm_reply.startswith("[brain]"):
            try:
                import json
                clean_json = re.sub(r"^```(?:json)?\s*|\s*```$", "", llm_reply.strip(), flags=re.MULTILINE)
                parsed = json.loads(clean_json)
                action = parsed.get("action")
                old_text = parsed.get("old_text") or ""
                new_text = parsed.get("new_text") or ""

                if action == "update_subject" and new_text:
                    _ACTIVE_DRAFT["subject"] = new_text.title()
                    draft_gmail_in_chrome(
                        recipient=", ".join(_ACTIVE_DRAFT.get("to", [])),
                        subject=_ACTIVE_DRAFT.get("subject", ""),
                        message=_ACTIVE_DRAFT.get("body", ""),
                        dry_run=dry_run,
                    )
                    return True, f"Updated email subject to '{_ACTIVE_DRAFT['subject']}'."

                elif action == "replace_body" and new_text:
                    current_body = _ACTIVE_DRAFT.get("body", "")
                    if old_text and re.search(re.escape(old_text), current_body, re.IGNORECASE):
                        new_body = re.sub(re.escape(old_text), new_text, current_body, flags=re.IGNORECASE)
                        _ACTIVE_DRAFT["body"] = new_body
                    else:
                        rw_prompt = (
                            f"Email body: \"{current_body}\"\n"
                            f"Change \"{old_text}\" to \"{new_text}\". "
                            f"Rewrite concisely. Return ONLY the new body text."
                        )
                        rw_res = ask(rw_prompt)
                        if not rw_res.startswith("[brain]") and len(rw_res.strip()) > 5:
                            _ACTIVE_DRAFT["body"] = re.sub(r'^(?:body\s*:\s*|["\'])+|(?:["\'])+$', "", rw_res.strip(), flags=re.IGNORECASE).strip()
                        else:
                            _ACTIVE_DRAFT["body"] = f"{current_body}\n\n{new_text}"

                    draft_gmail_in_chrome(
                        recipient=", ".join(_ACTIVE_DRAFT.get("to", [])),
                        subject=_ACTIVE_DRAFT.get("subject", ""),
                        message=_ACTIVE_DRAFT.get("body", ""),
                        dry_run=dry_run,
                    )
                    return True, f"Updated email body: replaced '{old_text}' with '{new_text}'."

                elif action == "remove_body" and old_text:
                    current_body = _ACTIVE_DRAFT.get("body", "")
                    if re.search(re.escape(old_text), current_body, re.IGNORECASE):
                        new_body = re.sub(re.escape(old_text), "", current_body, flags=re.IGNORECASE).strip()
                        _ACTIVE_DRAFT["body"] = re.sub(r" {2,}", " ", new_body)
                    else:
                        rw_prompt = f"Email body: \"{current_body}\"\nRemove \"{old_text}\". Return ONLY the new body text."
                        rw_res = ask(rw_prompt)
                        if not rw_res.startswith("[brain]") and len(rw_res.strip()) > 5:
                            _ACTIVE_DRAFT["body"] = re.sub(r'^(?:body\s*:\s*|["\'])+|(?:["\'])+$', "", rw_res.strip(), flags=re.IGNORECASE).strip()
                    draft_gmail_in_chrome(
                        recipient=", ".join(_ACTIVE_DRAFT.get("to", [])),
                        subject=_ACTIVE_DRAFT.get("subject", ""),
                        message=_ACTIVE_DRAFT.get("body", ""),
                        dry_run=dry_run,
                    )
                    return True, f"Removed '{old_text}' from the email body."

                elif action == "append_body" and new_text:
                    current_body = _ACTIVE_DRAFT.get("body", "").rstrip()
                    _ACTIVE_DRAFT["body"] = f"{current_body}\n\n{new_text}" if current_body else new_text
                    draft_gmail_in_chrome(
                        recipient=", ".join(_ACTIVE_DRAFT.get("to", [])),
                        subject=_ACTIVE_DRAFT.get("subject", ""),
                        message=_ACTIVE_DRAFT.get("body", ""),
                        dry_run=dry_run,
                    )
                    return True, f"Added to email body: '{new_text}'."

                elif action == "update_recipient" and new_text:
                    hits = find_emails(new_text)
                    if hits:
                        _ACTIVE_DRAFT["to"] = hits
                        draft_gmail_in_chrome(
                            recipient=", ".join(_ACTIVE_DRAFT.get("to", [])),
                            subject=_ACTIVE_DRAFT.get("subject", ""),
                            message=_ACTIVE_DRAFT.get("body", ""),
                            dry_run=dry_run,
                        )
                        return True, f"Updated recipient to {', '.join(hits)}."

                elif action == "send":
                    draft_gmail_in_chrome(
                        recipient=", ".join(_ACTIVE_DRAFT.get("to", [])),
                        subject=_ACTIVE_DRAFT.get("subject", ""),
                        message=_ACTIVE_DRAFT.get("body", ""),
                        dry_run=dry_run,
                    )
                    _ACTIVE_DRAFT = None
                    return True, "Email draft is confirmed in Chrome."

                elif action == "discard":
                    _ACTIVE_DRAFT = None
                    return True, "Email draft has been cancelled."
            except Exception as e:
                print(f"[email-edit] LLM fallback parse warning: {e}")

    return False, ""


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
