"""
jarvis/skills/datetime_skill.py — Offline Date, Time, and Day skill.

Provides instant, 100% accurate Windows system time and date reporting
in both English and natural conversational Hinglish.

Example queries handled:
    "what is the time"
    "what time is it"
    "time kya ho raha hai"
    "Maine poochha ki abhi time kya ho raha hai"
    "aaj kya tareekh hai"
    "what is today's date"
    "aaj kaun sa din hai"
    "what day is today"
"""

from __future__ import annotations

import datetime
import re

_TIME_EN_RE = re.compile(
    r"\b(?:what(?:\s+is|\s*'s)?\s+(?:the\s+)?time|what\s+time(?:\s+is\s+it)?|"
    r"tell\s+me\s+(?:the\s+)?time|current\s+time|time\s+please)\b",
    re.IGNORECASE,
)

_TIME_HI_RE = re.compile(
    r"(?:\btime\s+kya\b|\bkya\s+time\b|\bkitne\s+baje\b|\btime\s+batao\b|"
    r"\bkitna\s+baja\b|\bsamay\s+kya\b|\bwaqt\s+kya\b|"
    r"\btime\s+dekh\b|\bghadi\s+mein\b)",
    re.IGNORECASE,
)

_DATE_EN_RE = re.compile(
    r"\b(?:what(?:\s+is|\s*'s)?\s+(?:today'?s\s+)?date|what\s+date\s+is\s+it|"
    r"today'?s\s+date|current\s+date|tell\s+me\s+(?:the\s+)?date)\b",
    re.IGNORECASE,
)

_DATE_HI_RE = re.compile(
    r"(?:\baaj\s+kya\s+tareekh\b|\baaj\s+ki\s+date\b|\bkaun\s+si\s+date\b|"
    r"\bdate\s+batao\b|\btareekh\s+batao\b|\baaj\s+date\s+kya\b|\btareekh\s+kya\b)",
    re.IGNORECASE,
)

_DAY_EN_RE = re.compile(
    r"\b(?:what\s+day\s+is\s+(?:it|today)|which\s+day\s+is\s+today|what\s+is\s+the\s+day\s+today)\b",
    re.IGNORECASE,
)

_DAY_HI_RE = re.compile(
    r"(?:\baaj\s+kaun\s+sa\s+din\b|\baaj\s+kya\s+din\b|\bkaun\s+sa\s+vaar\b|\baaj\s+din\s+kaun\b)",
    re.IGNORECASE,
)

_HINGLISH_CLUES = re.compile(
    r"\b(?:kya|hai|hain|abhi|baje|baja|aaj|batao|tareekh|din|samay|waqt|maine|poochha|ki|ho\s+raha)\b",
    re.IGNORECASE,
)


def match_intent(text: str) -> str | None:
    """Detect if `text` is asking for time, date, or day.
    
    Returns 'time', 'date', 'day', or None.
    """
    if not text:
        return None
    cleaned = text.strip()

    if _TIME_EN_RE.search(cleaned) or _TIME_HI_RE.search(cleaned):
        return "time"
    if _DATE_EN_RE.search(cleaned) or _DATE_HI_RE.search(cleaned):
        return "date"
    if _DAY_EN_RE.search(cleaned) or _DAY_HI_RE.search(cleaned):
        return "day"
    return None


def get_time_string(is_hinglish: bool = False, now: datetime.datetime | None = None) -> str:
    """Format the current local time."""
    if now is None:
        now = datetime.datetime.now()
    hour = now.strftime("%I").lstrip("0") or "12"
    minute = now.strftime("%M")
    am_pm = now.strftime("%p")

    if is_hinglish:
        if 4 <= now.hour < 12:
            period = "subah"
        elif 12 <= now.hour < 16:
            period = "dopahar"
        elif 16 <= now.hour < 20:
            period = "shaam"
        else:
            period = "raat"
        return f"Abhi {period} ke {hour}:{minute} {am_pm} ho rahe hain."
    return f"The current time is {hour}:{minute} {am_pm}."


def get_date_string(is_hinglish: bool = False, now: datetime.datetime | None = None) -> str:
    """Format the current date."""
    if now is None:
        now = datetime.datetime.now()
    day_name = now.strftime("%A")
    day_num = now.strftime("%d").lstrip("0")
    month_name = now.strftime("%B")
    year = now.strftime("%Y")

    if is_hinglish:
        return f"Aaj {day_name}, {day_num} {month_name} {year} hai."
    return f"Today is {day_name}, {month_name} {day_num}, {year}."


def get_day_string(is_hinglish: bool = False, now: datetime.datetime | None = None) -> str:
    """Format today's day of week."""
    if now is None:
        now = datetime.datetime.now()
    day_name = now.strftime("%A")
    if is_hinglish:
        return f"Aaj {day_name} hai."
    return f"Today is {day_name}."


def try_datetime(text: str, dry_run: bool = False) -> tuple[bool, str]:
    """Detect and handle time/date queries.
    
    Returns:
        (handled, message)
    """
    intent = match_intent(text)
    if not intent:
        return False, ""

    is_hinglish = bool(_HINGLISH_CLUES.search(text))
    now = datetime.datetime.now()

    if intent == "time":
        msg = get_time_string(is_hinglish=is_hinglish, now=now)
    elif intent == "date":
        msg = get_date_string(is_hinglish=is_hinglish, now=now)
    else:  # day
        msg = get_day_string(is_hinglish=is_hinglish, now=now)

    return True, msg
