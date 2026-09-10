"""
jarvis/skills — small, single-purpose actions JARVIS can perform.

Skills are tried BEFORE the LLM brain in main.py, because many actions are
purely mechanical (open an app, send a message, search the web) and do not
need an AI call. This keeps the assistant fast and lets features work even
with no API key.

Modules:
    open_app   — "open any app" skill (Phase 3, DONE). Offline; launches
                 applications, websites, and web searches by voice.
    whatsapp   — WhatsApp messaging skill (Phase 3, DONE). Uses pywhatkit
                 to open WhatsApp Web with a pre-filled message.
    email      — Gmail email skill (Phase 3, DONE). Uses SMTP to send
                 emails via the user's Google App Password.
    web_search — Web search skill (Phase 4, DONE). Uses duckduckgo-search
                 to fetch top results and speak them back.

Exported:
    try_open_app(text, dry_run=False)      -> (handled, message)
    try_datetime(text, dry_run=False)      -> (handled, message)
    try_whatsapp(text, dry_run=False)      -> (handled, message)
    try_send_email(text, dry_run=False)    -> (handled, message)
    try_web_search(text, dry_run=False)    -> (handled, message)
"""

from .open_app import try_open_app
from .datetime_skill import try_datetime
from .whatsapp import try_whatsapp
from .email import try_send_email, try_edit_email_draft, get_active_draft, set_active_draft, clear_active_draft
from .web_search import try_web_search
from .browser_control import try_browser_control, get_chrome_path, open_url_in_chrome

__all__ = [
    "try_open_app",
    "try_datetime",
    "try_whatsapp",
    "try_send_email",
    "try_edit_email_draft",
    "get_active_draft",
    "set_active_draft",
    "clear_active_draft",
    "try_web_search",
    "try_browser_control",
    "get_chrome_path",
    "open_url_in_chrome",
]
