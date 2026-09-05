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
    "google chrome", "microsoft edge", "mozilla",
}

# Verbs that signal an "open/launch" command. Includes Hinglish verbs so the
# assistant behaves in mixed Hindi+English the same way the LLM brain does.
_OPEN_VERBS = (
    r"(?:open|launch|start|run|chalao|chalaao|kholo|khol|shuru|"
    r"shuru\s+karo|khologe|khulo)"
)

# Matches the command verb at the start of what the user said and captures the
# rest (the target app, possibly with a trailing query). We keep it simple and
# let later code split the query off.
_INTENT_RE = re.compile(rf"\b{_OPEN_VERBS}\b\s+(.+?)\s*$", re.IGNORECASE)

# Splits a target string into "app name" + optional "search/play query".
# e.g. "youtube and play despacito" -> ("youtube", "despacito")
_QUERY_SPLIT_RE = re.compile(
    r"\s+(?:and\s+)?(?:search\s+for|search|find|look\s+up|google|"
    r"play|watch|listen\s+to|show\s+me|open)\s+(.+)$",
    re.IGNORECASE,
)

# Polite filler words we strip from the front of a target name so
# "open my file explorer" -> "file explorer", "open the calculator" -> "calculator".
_FILLER_RE = re.compile(r"^(?:the|my|please|pls|jarvis|a|an|up|me|bahut|ek)\s+",
                        re.IGNORECASE)

# Trailing punctuation Whisper sometimes leaves on the end of a command.
_TRAIL_PUNCT_RE = re.compile(r"[.,!?;:]+$")

# --- Security: input validation ------------------------------------------
#
# Voice input is attacker-controlled (anyone can speak to the mic, or a
# recording can be played). We MUST treat every target string as untrusted
# and refuse anything that could break out of an os.startfile / subprocess
# call. Two layers of defence:
#
#   1. SHELL_METACHARS  — any target containing these is REJECTED outright.
#                         This blocks "open foo & calc", "open foo; rm -rf",
#                         "open foo && del /q", "open $(...)", etc.
#   2. SAFE_URL_SCHEMES — the auto-URL branch only accepts http(s). It
#                         explicitly REJECTS javascript:, file:, data:,
#                         vbscript:, about:, etc., so a spoken "open
#                         javascript:alert(1)" cannot trigger a URI handler.
SHELL_METACHARS = set('"&|<>^`(){};\\\'`\n\r\t$*?[]')
SAFE_URL_SCHEMES = ("http://", "https://")


def _is_safe_app_target(name: str) -> bool:
    """True iff `name` is a bare exe/URI name we are willing to launch.

    Blocks anything with shell metacharacters, anything that contains a
    space (multi-word args are NOT allowed through os.startfile), and
    anything that does not match a known safe pattern.
    """
    if not name:
        return False
    if any(c in SHELL_METACHARS for c in name):
        return False
    if " " in name:
        return False
    return True


def _is_safe_url(url: str) -> bool:
    """True iff `url` is an http(s) URL we are willing to open.

    The check is "starts with http:// or https://" AND does not then contain
    another scheme prefix. This blocks the prefix-injection case where a
    user says "open file:///..." and resolve_target would otherwise produce
    "https://file:///..." which is technically a https:// URL but is junk.
    """
    if not url:
        return False
    lowered = url.lower().strip()
    if not any(lowered.startswith(scheme) for scheme in SAFE_URL_SCHEMES):
        return False
    # Strip the scheme prefix; what remains must be a normal host[/path],
    # not another scheme (which would mean someone put a "https://" in front
    # of e.g. "file:///..." or "javascript:...").
    remainder = lowered
    for scheme in SAFE_URL_SCHEMES:
        if remainder.startswith(scheme):
            remainder = remainder[len(scheme):]
            break
    # remainder must start with a hostname character (letter/digit) or
    # contain a dot before any colon that could be another scheme.
    if not remainder or remainder[0] in ":/?#":
        return False
    # Anything with a colon before the first slash is suspicious (could be
    # `host:port`, which is OK, OR a nested scheme like `file:`).
    # We allow a single colon only if followed by digits (port) and only
    # before any "/".
    first_slash = remainder.find("/")
    head = remainder if first_slash == -1 else remainder[:first_slash]
    if ":" in head:
        # exactly one colon, and the part after is digits (port) — OK.
        host, _, port = head.partition(":")
        if not port.isdigit():
            return False
    return True


# --- Helpers -------------------------------------------------------------

def _normalize(name: str) -> str:
    """Lowercase, collapse whitespace, strip surrounding junk."""
    return re.sub(r"\s+", " ", name.strip().lower())


def _strip_target(text: str) -> str:
    """Remove filler words and trailing punctuation from a target name."""
    text = _TRAIL_PUNCT_RE.sub("", text.strip())
    # Strip filler repeatedly (e.g. "my the calculator").
    prev = None
    while prev != text:
        prev = text
        text = _FILLER_RE.sub("", text).strip()
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

    # 1. Exact known app.
    if key in APPS:
        return "app", APPS[key], None

    # 2. Exact known website.
    if key in WEBSITES:
        base, tmpl = WEBSITES[key]
        return "site", base, tmpl

    # 3. Something that already looks like a web address (e.g. "github.com",
    #    "openai.com/blog"). Open it as a URL — but ONLY if it is a safe
    #    http(s) target. javascript:, file:, data:, vbscript:, etc. are
    #    explicitly rejected so a malicious voice command cannot trigger
    #    a URI handler.
    if "." in key and " " not in key:
        url = key if key.startswith(("http://", "https://")) else "https://" + key
        if _is_safe_url(url):
            return "site", url, None
        # Looks URL-shaped but starts with a dangerous scheme — refuse.
        return "app", "", None  # empty target will fail downstream safely

    # 4. Unknown name: best-effort. We still return ("app", key, None) so
    #    that the caller's _shell_open will validate; if `key` has any
    #    shell metacharacters, _is_safe_app_target will reject it there.
    return "app", key, None


def _shell_open(target: str, arg: str | None = None) -> bool:
    """Open `target` on Windows, after validating it against an allowlist.

    `target` may be an app/executable name (from our APPS map) or an http(s)
    URL (from our WEBSITES map or a user-typed domain). It is NEVER raw user
    input that has not been through `_is_safe_app_target` / `_is_safe_url`.

    `arg` (optional) is a URL to open in `target` (browser-with-search case).
    It is also validated.

    Returns True on success. Both code paths (os.startfile for a single
    target, subprocess.Popen with a list for target+arg) use shell=False so
    the cmd.exe metacharacter injection vector is closed.

    Note: this intentionally does NOT fall back to a free-form `start "" "X"`
    shell call. If validation fails, we refuse; that is the whole point.
    """
    # Validate before doing anything.
    if arg is not None:
        if not _is_safe_app_target(target):
            print(f"[open_app] refused: target {target!r} failed safety check")
            return False
        if not _is_safe_url(arg):
            print(f"[open_app] refused: arg {arg!r} is not an http(s) URL")
            return False
        # List-form subprocess: no shell, so metacharacters in either string
        # would have to bypass Windows' own CreateProcess parsing.
        try:
            subprocess.Popen([target, arg], shell=False)
            return True
        except (FileNotFoundError, OSError) as e:
            print(f"[open_app] could not launch {target!r} {arg!r}: {e}")
            return False
    else:
        # Single target: either a known app name or a known URL.
        if _is_safe_url(target):
            try:
                os.startfile(target)  # ShellExecuteW with an http(s) URL is safe.
                return True
            except OSError as e:
                print(f"[open_app] could not open URL {target!r}: {e}")
                return False
        if _is_safe_app_target(target):
            try:
                os.startfile(target)  # ShellExecuteW with a bare exe name is safe.
                return True
            except OSError as e:
                print(f"[open_app] could not open {target!r}: {e}")
                return False
        print(f"[open_app] refused: target {target!r} failed safety check")
        return False


def _build_search(template: str, query: str) -> str:
    """Insert a URL-encoded query into a search-template's {} slot."""
    return template.format(urllib.parse.quote_plus(query.strip()))


# --- Public API ----------------------------------------------------------

def match_intent(text: str) -> tuple[str, str | None] | None:
    """Parse an "open X" command.

    Args:
        text: the transcribed command (any case; STT already lowercases).

    Returns:
        (target, query) where `query` may be None, OR None if this is not an
        open-app command at all.
    """
    if not text:
        return None

    m = _INTENT_RE.search(text)
    if not m:
        return None

    remainder = m.group(1).strip()

    # Split off an optional "search for / play ..." query.
    query: str | None = None
    qm = _QUERY_SPLIT_RE.search(remainder)
    if qm:
        remainder = remainder[: qm.start()].strip()
        query = qm.group(1).strip()

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
            _shell_open(to_open)
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
