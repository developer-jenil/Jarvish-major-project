"""
jarvis/skills — small, single-purpose actions JARVIS can perform.

Skills are tried BEFORE the LLM brain in main.py, because many actions are
purely mechanical (open an app, send a message) and do not need an AI call.
This keeps the assistant fast and lets features work even with no API key.

Modules:
    open_app  — "open any app" skill (Phase 3, DONE). Offline; launches
                applications, websites, and web searches by voice.

Exported:
    try_open_app(text, dry_run=False) -> (handled, message)
"""

from .open_app import try_open_app

__all__ = ["try_open_app"]
