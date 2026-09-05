"""
jarvis/skills/open_app.py — "Open any app" skill (Phase 3).

This skill lets JARVIS open applications, websites, and run web searches by
voice, for example:

    "open chrome"
    "open notepad"
    "open youtube and play despacito"
    "open google and search for weather in mumbai"
    "kholo calculator"                       (Hinglish verb works too)
    "start spotify"

It works ENTIRELY OFFLINE — no internet call, no API key, no LLM needed.
It uses only the Python standard library (os.startfile + subprocess in
list form, NEVER shell=True). That makes it fast and a strong selling point
for the project review: not every skill has to go through the LLM brain.

WHY A SEPARATE SKILL (and why it runs BEFORE the brain)?
- Skills are small, single-purpose actions. The "open app" skill is purely
  mechanical (launch a program), so it does not need an LLM to understand it.
- main.py calls try_open_app() FIRST. If it recognises an "open X" command it
  opens the app and speaks a short confirmation, then SKIPS the brain entirely.
  This saves a network round-trip and means app-launching works even with no
  OPENROUTER_API_KEY set.

HOW IT WORKS (three steps):
1. match_intent(text)  — detect "open/launch/start/run/kholo/chalao ..." and
                         pull out the target app plus an optional
                         "search for / play ..." query.
2. resolve_target(name)— turn the spoken name into something Windows can
                         actually launch: a known app executable, a website
                         URL, or a site-specific search URL.
3. _shell_open(...)    — actually start it through the Windows shell.

HOW TO TEST (no apps actually launch):
    python -m jarvis.skills.open_app --selftest   # checks parsing logic
    python -m jarvis.skills.open_app --dry-run \
        "open youtube and play despacito"         # show what WOULD open
"""

from __future__ import annotations

import os
import re
import subprocess
import urllib.parse

# --- Configuration -------------------------------------------------------

# Known desktop applications: spoken name -> Windows command to launch.
# Keys are LOWER-CASE names/aliases the user might say (English + Hinglish).
# Values are the executable / command Windows can resolve from PATH or its
# "App Paths" registry (e.g. "chrome", "notepad", "calc", "code").
# URI schemes (ms-settings:, ms-photos:, ...) are also valid launch targets.
APPS: dict[str, str] = {
    # --- Browsers -------------------------------------------------------
    "chrome":        "chrome",
    "google chrome": "chrome",
    "crome":         "chrome",
    "google crome":  "chrome",
    "chromium":      "chrome",
    "edge":          "msedge",
    "microsoft edge": "msedge",
    "firefox":       "firefox",
    "mozilla":       "firefox",
    "brave":         "brave",
    "opera":         "opera",

    # --- Windows system apps -------------------------------------------
    "notepad":        "notepad",
    "calculator":     "calc",
    "calc":           "calc",
    "paint":          "mspaint",
    "command prompt": "cmd",
    "cmd":            "cmd",
    "terminal":       "wt",
    "powershell":     "powershell",
    "file explorer":  "explorer",
    "explorer":       "explorer",
    "settings":       "ms-settings:",
    "control panel":  "control",
    "task manager":   "taskmgr",
    "camera":         "microsoft.windows.camera:",
    "photos":         "ms-photos:",
    "snipping tool":  "snippingtool",
    "word":           "winword",
    "ms word":        "winword",
    "excel":          "excel",
    "ms excel":       "excel",
    "powerpoint":     "powerpnt",
    "ppt":            "powerpnt",
    "outlook":        "outlook",
    "store":          "ms-windows-store:",
    "calendar":       "outlookcal:",

    # --- Common desktop apps -------------------------------------------
    "vscode":          "code",
    "visual studio code": "code",
    "vs code":         "code",
    "spotify":         "spotify",
    "discord":         "discord",
    "telegram":        "telegram",
    "whatsapp":        "whatsapp",
    "zoom":            "zoom",
    "steam":           "steam",
    "obs":             "obs64",
    "notion":          "notion",
    "vs":              "devenv",
}

# Websites the user can name directly. Each entry is (base_url, search_template).
# If the user adds a "search for / play ..." query we open search_template
# (with the query URL-encoded into the {} slot); otherwise we open base_url.
WEBSITES: dict[str, tuple[str, str | None]] = {
    "youtube":   ("https://www.youtube.com",
                  "https://www.youtube.com/results?search_query={}"),
    "google":    ("https://www.google.com",
                  "https://www.google.com/search?q={}"),
    "gmail":     ("https://mail.google.com", None),
    "facebook":  ("https://www.facebook.com",
                  "https://www.facebook.com/search/top?q={}"),
    "fb":        ("https://www.facebook.com",
                  "https://www.facebook.com/search/top?q={}"),
    "instagram": ("https://www.instagram.com",
                  "https://www.instagram.com/explore/tags/{}/"),
    "twitter":   ("https://twitter.com",
                  "https://twitter.com/search?q={}"),
    "x":         ("https://twitter.com",
                  "https://twitter.com/search?q={}"),
    "linkedin":  ("https://www.linkedin.com",
                  "https://www.linkedin.com/search/results/all/?keywords={}"),
    "github":    ("https://github.com",
                  "https://github.com/search?q={}"),
    "reddit":    ("https://www.reddit.com",
                  "https://www.reddit.com/search/?q={}"),
    "netflix":   ("https://www.netflix.com", None),
    "amazon":    ("https://www.amazon.com",
                  "https://www.amazon.com/s?k={}"),
    "wikipedia": ("https://en.wikipedia.org",
                  "https://en.wikipedia.org/w/index.php?search={}"),
    "wiki":      ("https://en.wikipedia.org",
                  "https://en.wikipedia.org/w/index.php?search={}"),
    "chatgpt":   ("https://chat.openai.com", None),
    "bing":      ("https://www.bing.com",
                  "https://www.bing.com/search?q={}"),
    "maps":      ("https://www.google.com/maps",
                  "https://www.google.com/maps/search/?api=1&query={}"),
}

# Browsers we treat specially: if the user pairs a browser with a search
# query we launch that browser directly to the Google search URL (one clean
# action) instead of opening the browser empty + a separate tab.
BROWSERS: set[str] = {
    "chrome", "edge", "firefox", "brave", "opera", "chromium",
    "google chrome", "microsoft edge", "mozilla", "crome", "google crome",
}

# Verbs that signal an "open/launch" command. Includes English and Hinglish verbs
# at the beginning (prefix) or end (suffix) of a sentence.
_PREFIX_VERBS = (
    r"(?:open|launch|start|run|chalao|chalaao|chala\s+do|kholo|khol|khol\s+do|"
    r"khol\s+de|khol\s+dijiye|kholna|shuru\s+karo|shuru|khologe|khulo)"
)
_SUFFIX_VERBS = (
    r"(?:kholo|khol\s+do|khol\s+de|khol\s+dijiye|kholna|chalao|chalaao|chala\s+do|"
    r"open\s+karo|open\s+kar\s+do|open\s+kijiye|open\s+karna|open|"
    r"start\s+karo|start\s+kar\s+do|shuru\s+karo|launch\s+karo)"
)

# Matches prefix commands: e.g. "open notepad", "kholo calculator", "please open chrome"
_PREFIX_INTENT_RE = re.compile(
    rf"^(?:(?:hey\s+|ok\s+)?jarvis\s+|please\s+|pls\s+|can\s+you\s+|could\s+you\s+|kripya\s+|zara\s+)?\b{_PREFIX_VERBS}\b\s+(.+?)\s*$",
    re.IGNORECASE,
)

# Matches suffix commands: e.g. "notepad application kholo", "chrome chalao", "calculator open karo"
_SUFFIX_INTENT_RE = re.compile(
    rf"^(?:(?:hey\s+|ok\s+)?jarvis\s+|please\s+|pls\s+|kripya\s+|zara\s+|tum\s+|aap\s+)?(.+?)\s+(?:ko\s+|ka\s+|ki\s+)?\b{_SUFFIX_VERBS}\b\s*$",
    re.IGNORECASE,
)

# Splits a target string into "app name" + optional "search/play query".
# e.g. "youtube and play despacito" -> ("youtube", "despacito")
# or "youtube par despacito" -> ("youtube", "despacito")
_QUERY_SPLIT_RE = re.compile(
    r"\s+(?:(?:and\s+|aur\s+|par\s+|pe\s+)?(?:search\s+for|search|find|look\s+up|google|"
    r"play|watch|listen\s+to|show\s+me|open|chalao|dikhau)|par|pe)\s+(.+)$",
    re.IGNORECASE,
)

# Filler words and descriptors to strip from target
_FILLER_LEADING_RE = re.compile(
    r"^(?:the|my|a|an|please|pls|jarvis|zara|kripya|meri|apna|apni|ek|tum|aap)\s+",
    re.IGNORECASE,
)
_FILLER_TRAILING_RE = re.compile(
    r"\s+(?:application|app|apps|software|program|browser|window|ko|ka|ki|wali|wale|wala|please|pls)$",
    re.IGNORECASE,
)

# Trailing punctuation Whisper sometimes leaves on the end of a command.
_TRAIL_PUNCT_RE = re.compile(r"[.,!?;:]+$")

# --- Security: input validation ------------------------------------------
SHELL_METACHARS = set('"&|<>^`(){};\\\'`\n\r\t$*?[]')
SAFE_URL_SCHEMES = ("http://", "https://")


def _is_safe_app_target(name: str) -> bool:
    """True iff `name` is a bare exe/URI name we are willing to launch."""
    if not name:
        return False
    if any(c in SHELL_METACHARS for c in name):
        return False
    if " " in name:
        return False
    return True


def _is_safe_url(url: str) -> bool:
    """True iff `url` is an http(s) URL we are willing to open."""
    if not url:
        return False
    lowered = url.lower().strip()
    if not any(lowered.startswith(scheme) for scheme in SAFE_URL_SCHEMES):
        return False
    remainder = lowered
    for scheme in SAFE_URL_SCHEMES:
        if remainder.startswith(scheme):
            remainder = remainder[len(scheme):]
            break
    if not remainder or remainder[0] in ":/?#":
        return False
    first_slash = remainder.find("/")
    head = remainder if first_slash == -1 else remainder[:first_slash]
    if ":" in head:
        host, _, port = head.partition(":")
        if not port.isdigit():
            return False
    return True


# --- Helpers -------------------------------------------------------------

def _normalize(name: str) -> str:
    """Lowercase, collapse whitespace, strip surrounding junk."""
    return re.sub(r"\s+", " ", name.strip().lower())


def _strip_target(text: str) -> str:
    """Remove filler words, descriptors, and trailing punctuation from a target name."""
    text = _TRAIL_PUNCT_RE.sub("", text.strip())
    prev = None
    while prev != text:
        prev = text
        text = _FILLER_LEADING_RE.sub("", text).strip()
        text = _FILLER_TRAILING_RE.sub("", text).strip()
    return text


def resolve_target(name: str) -> tuple[str, str, str | None]:
    """Turn a spoken app/site name into a launchable descriptor.

    Returns (kind, value, search_template) where:
        kind == "app"   -> value is an executable/command to launch.
        kind == "site"  -> value is a URL to open; search_template (if any)
                           is used when a search/play query is present.
        search_template -> a str with a single {} slot, or None.
    """
    key = _normalize(name)

    # Security check: if key contains shell metacharacters, do NOT match against
    # known apps/websites (which would strip the malicious payload). Return key directly
    # so downstream _is_safe_app_target() or _is_safe_url() will reject it.
    if any(c in SHELL_METACHARS for c in key):
        return "app", key, None

    # 1. Exact known app.
    if key in APPS:
        return "app", APPS[key], None

    # 2. Exact known website.
    if key in WEBSITES:
        base, tmpl = WEBSITES[key]
        return "site", base, tmpl

    # 3. Substring word match in APPS (e.g. "notepad application" -> "notepad")
    for app_name, app_cmd in sorted(APPS.items(), key=lambda item: len(item[0]), reverse=True):
        if re.search(rf"\b{re.escape(app_name)}\b", key):
            return "app", app_cmd, None

    # 4. Substring word match in WEBSITES (e.g. "youtube video" -> "youtube")
    for site_name, (base, tmpl) in sorted(WEBSITES.items(), key=lambda item: len(item[0]), reverse=True):
        if re.search(rf"\b{re.escape(site_name)}\b", key):
            return "site", base, tmpl

    # 5. Something that already looks like a web address.
    if "." in key and " " not in key:
        url = key if key.startswith(("http://", "https://")) else "https://" + key
        if _is_safe_url(url):
            return "site", url, None
        return "app", "", None

    # 6. Unknown name: best-effort.
    return "app", key, None


def _shell_open(target: str, arg: str | None = None) -> bool:
    """Open `target` on Windows, after validating it against an allowlist."""
    if arg is not None:
        if not _is_safe_app_target(target):
            print(f"[open_app] refused: target {target!r} failed safety check")
            return False
        if not _is_safe_url(arg):
            print(f"[open_app] refused: arg {arg!r} is not an http(s) URL")
            return False
        cmd_target = target
        if target in ("chrome", "google chrome"):
            try:
                from jarvis.skills.browser_control import get_chrome_path
                cp = get_chrome_path()
                if cp:
                    cmd_target = cp
            except Exception:
                pass
        try:
            subprocess.Popen([cmd_target, arg], shell=False)
            return True
        except (FileNotFoundError, OSError) as e:
            print(f"[open_app] could not launch {cmd_target!r} {arg!r}: {e}")
            return False
    else:
        # Single target: either a known app name or a known URL.
        if _is_safe_url(target):
            try:
                os.startfile(target)
                return True
            except OSError as e:
                print(f"[open_app] could not open URL {target!r}: {e}")
                return False
        if _is_safe_app_target(target):
            if target in ("chrome", "google chrome", "crome", "google crome"):
                try:
                    from jarvis.skills.browser_control import open_url_in_chrome
                    return open_url_in_chrome("https://www.google.com")
                except Exception:
                    pass
            try:
                os.startfile(target)
                return True
            except OSError:
                pass
            # Fallback 1: try with .exe
            try:
                os.startfile(target + ".exe")
                return True
            except OSError:
                pass
            # Fallback 2: try URI scheme protocol (e.g. "calc:" or "whatsapp:")
            try:
                os.startfile(target + ":")
                return True
            except OSError:
                pass
            # Fallback 3: try subprocess list launch
            try:
                subprocess.Popen([target], shell=False)
                return True
            except (FileNotFoundError, OSError) as e:
                print(f"[open_app] could not open {target!r}: {e}")
                return False
        print(f"[open_app] refused: target {target!r} failed safety check")
        return False


def _build_search(template: str, query: str) -> str:
    """Insert a URL-encoded query into a search-template's {} slot."""
    return template.format(urllib.parse.quote_plus(query.strip()))


# --- Public API ----------------------------------------------------------

def match_intent(text: str) -> tuple[str, str | None] | None:
    """Parse an "open X" command. Supports English and Hinglish (prefix and suffix verbs).

    Args:
        text: the transcribed command (any case).

    Returns:
        (target, query) where `query` may be None, OR None if this is not an
        open-app command at all.
    """
    if not text:
        return None

    remainder = None
    m = _PREFIX_INTENT_RE.match(text)
    if m:
        remainder = m.group(1).strip()
    else:
        m2 = _SUFFIX_INTENT_RE.match(text)
        if m2:
            remainder = m2.group(1).strip()

    if not remainder:
        return None

    # Split off an optional "search for / play ..." query.
    query: str | None = None
    qm = _QUERY_SPLIT_RE.search(remainder)
    if qm:
        query = qm.group(1).strip()
        remainder = remainder[: qm.start()].strip()

    target = _strip_target(remainder)
    if not target:
        return None

    return target, query


def try_open_app(text: str, dry_run: bool = False) -> tuple[bool, str]:
    """Detect an open-app command and act on it.

    Args:
        text: the transcribed command (already lowercased by STT, but we
              handle either case).
        dry_run: if True, do NOT actually launch anything — just return what
                 WOULD happen. Used by the self-test and for safe demos.

    Returns:
        (handled, message):
          handled == True  -> a spoken reply (short, English/Hinglish) is
                              ready; main.py should say it and skip the brain.
          handled == False -> this wasn't an open-app command; main.py should
                              fall through to the LLM brain as usual.
    """
    parsed = match_intent(text)
    if parsed is None:
        return False, ""

    target, query = parsed
    kind, value, tmpl = resolve_target(target)

    # Defence-in-depth: if resolve_target refused the target (returned an
    # empty value because the URL was dangerous), speak a friendly refusal
    # instead of trying to launch "".
    if not value:
        return True, f"Sorry, I cannot open {target}. The name or address looks unsafe."

    # --- Browser + search query: open that browser straight to Google. ---
    if query and target in BROWSERS and kind == "app":
        if target in ("chrome", "google chrome", "crome", "google crome"):
            try:
                from jarvis.skills.browser_control import execute_chrome_search
                return execute_chrome_search(query, dry_run=dry_run)
            except Exception as e:
                print(f"[open_app] browser_control fallback: {e}")
        url = "https://www.google.com/search?q=" + urllib.parse.quote_plus(query)
        if dry_run:
            print(f"[open_app][dry-run] would launch browser {value!r} -> {url}")
        else:
            _shell_open(value, arg=url)
        return True, f"Opening {target} and searching for {query}."

    # --- Regular app + search query: open the app AND a Google search. ---
    if query and kind == "app":
        if dry_run:
            print(f"[open_app][dry-run] would open app {value!r} "
                  f"+ google search for {query!r}")
        else:
            _shell_open(value)
            _shell_open("https://www.google.com/search?q="
                        + urllib.parse.quote_plus(query))
        return True, f"Opening {target} and searching for {query}."

    # --- Website (with optional search template). ----------------------
    if kind == "site":
        to_open = _build_search(tmpl, query) if (tmpl and query) else value
        if not _is_safe_url(to_open):
            return True, f"Sorry, I cannot open {target}. The address is not a safe http(s) URL."
        if dry_run:
            print(f"[open_app][dry-run] would open URL: {to_open}")
        else:
            try:
                from jarvis.skills.browser_control import _STATE
                _STATE["last_opened_url"] = to_open
            except Exception:
                pass
            _shell_open(to_open)
        if target == "gmail":
            try:
                from jarvis.skills.browser_control import _STATE
                _STATE["active_site"] = "gmail"
            except Exception:
                pass
        if query and tmpl:
            return True, f"Opening {target} and searching for {query}."
        return True, f"Opening {target}."

    # --- Plain app. -----------------------------------------------------
    if not _is_safe_app_target(value):
        return True, f"Sorry, I cannot open {target}. The name contains characters I will not run."
    if dry_run:
        print(f"[open_app][dry-run] would launch app: {value!r}")
        return True, f"Opening {target}."
    if not _shell_open(value):
        return True, f"Sorry, I could not find {target} on this computer."
    return True, f"Opening {target}."


if __name__ == "__main__":
    import sys

    argv = sys.argv[1:]
    # Pull out the leading flags; anything left is treated as the phrase.
    flags = {a for a in argv if a.startswith("--")}
    phrase_words = [a for a in argv if not a.startswith("--")]
    phrase = " ".join(phrase_words)

    if "--selftest" in flags:
        # CI-safe: no apps are launched. We only verify the parsing/resolve
        # logic returns sensible targets + queries for a handful of phrasings.
        samples = [
            "open chrome",
            "open notepad",
            "kholo calculator",
            "start spotify",
            "open youtube and play despacito",
            "open google and search for weather in mumbai",
            "open my file explorer",
            "open github.com",
            "tell me a joke",          # should NOT be handled
            # Security regression cases — each MUST be refused:
            "open chrome & calc & notepad",                 # shell metachars
            "open calc && del /f /q C:\\\\",                # cmd.exe injection
            "open javascript:alert(1)",                      # dangerous URL scheme
            "open file:///C:/Users/Asus/secrets.txt",        # file: scheme
        ]
        print("[selftest] checking intent parsing (dry-run)...")
        for s in samples:
            handled, msg = try_open_app(s, dry_run=True)
            parsed = match_intent(s)
            print(f"  {s!r:55} -> handled={handled} msg={msg!r} parsed={parsed}")
        # Assertions to fail loudly if the logic regresses.
        assert match_intent("open chrome") == ("chrome", None)
        assert match_intent("open youtube and play despacito") == (
            "youtube", "despacito")
        assert match_intent("open google and search for weather") == (
            "google", "weather")
        assert match_intent("tell me a joke") is None
        assert try_open_app("open notepad", dry_run=True)[0] is True
        assert try_open_app("what is the time", dry_run=True)[0] is False
        # Security: malicious commands are recognised as open-app intents
        # (so we control the reply) but the spoken message MUST be a refusal
        # — it must NOT contain "Opening" for these.
        for bad in [
            "open chrome & calc & notepad",
            "open calc && del /f /q C:\\\\",
            "open javascript:alert(1)",
            "open file:///C:/Users/Asus/secrets.txt",
        ]:
            handled, msg = try_open_app(bad, dry_run=True)
            assert handled, f"malicious command {bad!r} was NOT handled"
            assert "Opening" not in msg, (
                f"malicious command {bad!r} produced a launch message: {msg!r}")
        # Low-level safety: the helper must reject anything with metachars.
        assert _is_safe_app_target("chrome") is True
        assert _is_safe_app_target("chrome & calc") is False
        assert _is_safe_app_target("calc; rm -rf /") is False
        assert _is_safe_url("https://example.com") is True
        assert _is_safe_url("javascript:alert(1)") is False
        assert _is_safe_url("file:///C:/x") is False
        print("[selftest] PASS — open-app parsing + safety checks work.")

    elif "--dry-run" in flags:
        # Show what WOULD open, without launching anything.
        if not phrase:
            phrase = "open youtube and play despacito"
        handled, msg = try_open_app(phrase, dry_run=True)
        print(f"handled={handled}  message={msg!r}")

    elif "--run" in flags:
        # ACTUALLY launch the app. No mic, no STT, no brain, no TTS — this is
        # the stand-alone way to test JUST the open-app feature.
        if phrase:
            handled, msg = try_open_app(phrase, dry_run=False)
            print(f"[result] handled={handled}  -> {msg}")
        else:
            # No phrase given: enter an interactive loop. Type a command and
            # press Enter to open it; empty line or Ctrl+C to quit.
            print("Interactive open-app tester. Type a command, e.g.:")
            print('  open chrome')
            print('  open youtube and play despacito')
            print('  kholo calculator')
            print('(empty line or Ctrl+C to quit)\n')
            try:
                while True:
                    try:
                        line = input("jarvis> ").strip()
                    except EOFError:
                        break
                    if not line:
                        break
                    handled, msg = try_open_app(line, dry_run=False)
                    print(f"[result] handled={handled}  -> {msg}")
            except KeyboardInterrupt:
                print("\nbye.")

    else:
        print("Usage (test ONLY the open-app feature, no mic/STT/brain):")
        print("  python -m jarvis.skills.open_app --selftest")
        print('  python -m jarvis.skills.open_app --dry-run "open youtube and play despacito"')
        print('  python -m jarvis.skills.open_app --run "open chrome"')
        print("  python -m jarvis.skills.open_app --run        # interactive loop")
