"""
jarvis/skills/browser_control.py — Chrome Desktop Search, Link Clicking & Gmail Drafting.

This skill provides direct desktop browser control for Google Chrome on Windows:
1. Search in Chrome:
   - "open chrome and search for latest AI news"
   - "chrome par search karo weather in delhi"
   - "search python tutorials on chrome"
2. Search Result Link Clicking:
   - "click on the first link" / "open the first result" / "pehla link kholo"
   - "click on the second link" / "dusra result open karo"
   - "open the website" / "website kholo"
3. Gmail Mail Drafting in Chrome:
   - "open gmail and draft a mail to prof sharma saying project is ready"
   - "draft an email to mom saying I reached safely"
   - "gmail par mail draft karo dad ko that meeting is postponed"
   - Direct web compose URL:
     https://mail.google.com/mail/?view=cm&fs=1&to={email}&su={subject}&body={body}
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import threading
import urllib.parse
from typing import Any

# --- Browser & Session State ---------------------------------------------

_STATE: dict[str, Any] = {
    "last_query": "",
    "results": [],          # list of {"title": str, "url": str, "snippet": str}
    "active_site": None,    # e.g. "google", "gmail"
    "last_opened_url": None,
}

_ORDINALS_MAP: dict[str, int] = {
    "first": 0,
    "1st": 0,
    "one": 0,
    "pehla": 0,
    "pehli": 0,
    "pehle": 0,
    "second": 1,
    "2nd": 1,
    "two": 1,
    "dusra": 1,
    "dusri": 1,
    "dusre": 1,
    "third": 2,
    "3rd": 2,
    "three": 2,
    "teesra": 2,
    "teesri": 2,
    "teesre": 2,
    "fourth": 3,
    "4th": 3,
    "four": 3,
    "chautha": 3,
    "chauthe": 3,
    "fifth": 4,
    "5th": 4,
    "five": 4,
    "paanchva": 4,
}

KNOWN_SITES: dict[str, str] = {
    "gmail": "https://mail.google.com",
    "google": "https://www.google.com",
    "youtube": "https://www.youtube.com",
    "facebook": "https://www.facebook.com",
    "fb": "https://www.facebook.com",
    "instagram": "https://www.instagram.com",
    "twitter": "https://twitter.com",
    "x": "https://twitter.com",
    "github": "https://github.com",
    "whatsapp": "https://web.whatsapp.com",
    "reddit": "https://www.reddit.com",
    "netflix": "https://www.netflix.com",
    "wikipedia": "https://www.wikipedia.org",
    "wiki": "https://en.wikipedia.org",
    "chatgpt": "https://chat.openai.com",
}

SAFE_URL_SCHEMES = ("http://", "https://")


# --- Chrome Path Discovery -----------------------------------------------

def get_chrome_path() -> str | None:
    """Find the Chrome executable on Windows using Registry, standard paths, or PATH."""
    # 1. Windows Registry (HKCU / HKLM App Paths)
    try:
        import winreg
        for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            try:
                with winreg.OpenKey(
                    root,
                    r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe"
                ) as key:
                    val, _ = winreg.QueryValueEx(key, "")
                    if val and os.path.exists(val):
                        return val
            except OSError:
                pass
    except ImportError:
        pass

    # 2. Standard installation paths
    candidate_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%PROGRAMFILES%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%PROGRAMFILES(X86)%\Google\Chrome\Application\chrome.exe"),
    ]
    for p in candidate_paths:
        if os.path.exists(p):
            return p

    # 3. PATH resolution
    found = shutil.which("chrome") or shutil.which("chrome.exe")
    if found and os.path.exists(found):
        return found

    return None


def get_active_chrome_profile() -> str | None:
    """Find the currently active Chrome profile name (e.g. 'Profile 2' or 'Default') from Local State."""
    try:
        import json
        from pathlib import Path
        local_state_file = Path(os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data\Local State"))
        if local_state_file.exists():
            data = json.loads(local_state_file.read_text(encoding="utf-8"))
            active_profiles = data.get("profile", {}).get("last_active_profiles", [])
            if active_profiles and isinstance(active_profiles, list):
                return active_profiles[-1]
            last_used = data.get("profile", {}).get("last_used")
            if last_used:
                return last_used
    except Exception as exc:
        print(f"[browser_control] get_active_chrome_profile error: {exc}")
    return None


def is_safe_url(url: str) -> bool:
    """Check whether a URL is a safe HTTP/HTTPS URL."""
    if not url:
        return False
    low = url.lower().strip()
    return low.startswith(SAFE_URL_SCHEMES)


def get_desktop_startupinfo() -> subprocess.STARTUPINFO:
    """Create a STARTUPINFO struct targeting the interactive user desktop."""
    si = subprocess.STARTUPINFO()
    try:
        si.lpDesktop = r"WinSta0\Default"
    except Exception:
        pass
    return si


def launch_on_user_desktop(cmd_line: str) -> bool:
    """Execute command directly in the interactive user desktop session (WinSta0\\Default) via WMI.

    This ensures GUI windows (Chrome, Notepad, Calc) appear visibly on the user's active screen
    even when the Python server is running under a background task or isolated desktop.
    """
    if not cmd_line or not cmd_line.strip():
        return False
    cmd_clean = cmd_line.strip()

    # 1. Primary: WMI Win32_Process.Create via PowerShell
    try:
        ps_script = (
            f"$cmd = @'\n{cmd_clean}\n'@\n"
            f"$res = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{{CommandLine = $cmd}}\n"
            f"if ($res.ReturnValue -eq 0) {{ exit 0 }} else {{ exit $res.ReturnValue }}\n"
        )
        p = subprocess.run(
            ["powershell.exe", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps_script],
            capture_output=True,
            text=True,
            timeout=6,
        )
        if p.returncode == 0:
            return True
    except Exception as exc:
        print(f"[browser_control] WMI launch error: {exc}")

    # 2. Secondary: Switch thread desktop to WinSta0\\Default and ShellExecuteW
    try:
        import ctypes
        user32 = ctypes.windll.user32
        hdesk = user32.OpenDesktopW("Default", 0, False, 0x01FF)
        if hdesk:
            user32.SetThreadDesktop(hdesk)
        ret = ctypes.windll.shell32.ShellExecuteW(None, "open", cmd_clean, None, None, 1)
        if ret > 32:
            return True
    except Exception as exc:
        print(f"[browser_control] ShellExecuteW fallback error: {exc}")

    # 3. Tertiary: Direct subprocess.Popen with WinSta0\\Default startupinfo
    try:
        si = subprocess.STARTUPINFO()
        try:
            si.lpDesktop = r"WinSta0\Default"
        except Exception:
            pass
        subprocess.Popen(cmd_clean, startupinfo=si, shell=True)
        return True
    except Exception as exc:
        print(f"[browser_control] Popen fallback error: {exc}")

    return False


def open_url_in_chrome(url: str, dry_run: bool = False, new_window: bool = True) -> bool:
    """Open a URL in Google Chrome on the interactive user desktop in the foreground."""
    if not is_safe_url(url):
        print(f"[browser_control] refused unsafe url: {url!r}")
        return False

    _STATE["last_opened_url"] = url

    if dry_run:
        print(f"[browser_control][dry-run] would open in Chrome (new_window={new_window}): {url}")
        return True

    chrome_exe = get_chrome_path() or "chrome.exe"
    profile = get_active_chrome_profile()

    # 1. Primary: Launch directly into the user's active Chrome profile window (e.g. Profile 2)
    try:
        import ctypes
        if profile:
            params = f'--profile-directory="{profile}" "{url}"'
            ret = ctypes.windll.shell32.ShellExecuteW(None, "open", chrome_exe, params, None, 1)
            if ret > 32:
                return True
    except Exception as exc:
        print(f"[browser_control] ShellExecuteW profile launch error: {exc}")

    # 2. Secondary: Native Windows ShellExecuteW with direct URL
    try:
        import ctypes
        ret = ctypes.windll.shell32.ShellExecuteW(None, "open", chrome_exe, url, None, 1)
        if ret > 32:
            return True
        ret2 = ctypes.windll.shell32.ShellExecuteW(None, "open", "chrome.exe", url, None, 1)
        if ret2 > 32:
            return True
    except Exception as exc:
        print(f"[browser_control] ShellExecuteW chrome error: {exc}")

    # 3. Tertiary: Direct execution of Chrome executable with DETACHED_PROCESS
    if chrome_exe and os.path.exists(chrome_exe):
        try:
            DETACHED_PROCESS = 0x00000008
            args = [chrome_exe]
            if profile:
                args.append(f'--profile-directory={profile}')
            args.append(url)
            subprocess.Popen(args, shell=False, creationflags=DETACHED_PROCESS)
            return True
        except Exception as exc:
            print(f"[browser_control] Popen chrome_exe error: {exc}")

    # 4. Quaternary: Native os.startfile fallback
    try:
        os.startfile(url)
        return True
    except Exception as exc:
        print(f"[browser_control] os.startfile fallback: {exc}")

    return False


# --- Background Search Fetcher -------------------------------------------

def _fetch_search_results(query: str) -> list[dict[str, str]]:
    """Fetch top organic results to cache for link clicking (DDG -> Wikipedia -> Google Lucky)."""
    results: list[dict[str, str]] = []

    # 1. Try DuckDuckGo
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            raw = list(ddgs.text(query, max_results=5))
        for r in raw:
            href = r.get("href") or r.get("url") or ""
            title = r.get("title") or "Search Result"
            body = r.get("body") or ""
            if href and is_safe_url(href):
                results.append({
                    "title": title.strip(),
                    "url": href.strip(),
                    "snippet": body.strip(),
                })
    except Exception as exc:
        print(f"[browser_control] DDG fetch error: {exc}")

    # 2. Try Wikipedia OpenSearch API (reliable, fast JSON search)
    if not results:
        try:
            import json
            import urllib.request
            wiki_api = (
                f"https://en.wikipedia.org/w/api.php?action=opensearch&"
                f"search={urllib.parse.quote(query)}&limit=5&namespace=0&format=json"
            )
            req = urllib.request.Request(wiki_api, headers={"User-Agent": "JARVIS-Assistant/1.0"})
            with urllib.request.urlopen(req, timeout=4) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                titles = data[1] if len(data) > 1 else []
                snippets = data[2] if len(data) > 2 else []
                urls = data[3] if len(data) > 3 else []
                for t, s, u in zip(titles, snippets, urls):
                    if u and is_safe_url(u):
                        results.append({
                            "title": t.strip(),
                            "url": u.strip(),
                            "snippet": s.strip(),
                        })
        except Exception as exc:
            print(f"[browser_control] Wikipedia OpenSearch fallback error: {exc}")

    # 3. Fallback: Direct Google "I'm Feeling Lucky" redirect link
    if not results:
        lucky_url = f"https://www.google.com/search?btnI=1&q={urllib.parse.quote_plus(query)}"
        results.append({
            "title": f"Top result for {query}",
            "url": lucky_url,
            "snippet": f"Google top organic search destination for {query}",
        })

    return results


def _async_cache_results(query: str):
    def worker():
        res = _fetch_search_results(query)
        if res:
            _STATE["results"] = res
            print(f"[browser_control] cached {len(res)} results for {query!r}")
    threading.Thread(target=worker, daemon=True).start()


# --- Chrome Search Execution ---------------------------------------------

def clean_search_query(query: str) -> str:
    """Clean voice/natural language preambles and suffixes from a search query."""
    clean_q = query.strip()
    while True:
        prev = clean_q
        clean_q = re.sub(
            r"^(?:in|for|to|about|search\s+for|search\s+karo|search|dhundo|likho|type\s+karo|"
            r"par|pe|me|mein|usme|usmein|isme|ismein|uspar|ispar|"
            r"uske\s+search\s*bar\s*\b(?:mein|me)\b(?:\s+jakar)?|"
            r"search\s*bar\s*\b(?:mein|me)\b(?:\s+jakar)?)\s+",
            "",
            clean_q,
            flags=re.IGNORECASE,
        ).strip()
        clean_q = re.sub(
            r"\s+(?:search\s+karo|search|dhundo|kholo|chalao|likho|type\s+karo)$",
            "",
            clean_q,
            flags=re.IGNORECASE,
        ).strip()
        if clean_q == prev:
            break
    return clean_q


def execute_chrome_search(query: str, dry_run: bool = False) -> tuple[bool, str]:
    """Execute search in Chrome browser and cache organic links."""
    clean_q = clean_search_query(query)
    if not clean_q:
        return False, "What would you like me to search for on Chrome?"

    search_url = f"https://www.google.com/search?q={urllib.parse.quote_plus(clean_q)}"
    _STATE["last_query"] = clean_q
    _STATE["active_site"] = "google"

    open_url_in_chrome(search_url, dry_run=dry_run, new_window=True)

    if dry_run:
        _STATE["results"] = [
            {"title": f"Top result for {clean_q}", "url": f"https://en.wikipedia.org/wiki/{urllib.parse.quote(clean_q)}", "snippet": "Sample result"}
        ]
    else:
        _async_cache_results(clean_q)

    # Determine Hinglish vs English reply
    if any(w in (query + " " + clean_q).lower() for w in ("karo", "khol", "chalao", "dhundo", "likho", "bar", "usme", "usmein")):
        return True, f"Chrome me search kar raha hoon: {clean_q}."
    return True, f"Opening Chrome and searching for {clean_q}."


def search_and_click_result(
    query: str,
    target_spec: str = "first",
    dry_run: bool = False,
) -> tuple[bool, str]:
    """Execute search in Chrome and automatically open the target result link in the foreground."""
    clean_q = clean_search_query(query)
    if not clean_q:
        return False, "What would you like me to search for on Chrome?"

    spec_clean = (target_spec or "first").lower().strip()
    target_idx = 0
    for word, idx in _ORDINALS_MAP.items():
        if re.search(rf"\b{re.escape(word)}\b", spec_clean):
            target_idx = idx
            break

    # 1. Known top-level service shortcut
    q_low = clean_q.lower()
    if q_low in KNOWN_SITES and target_idx == 0:
        direct_url = KNOWN_SITES[q_low]
        _STATE["last_query"] = clean_q
        _STATE["active_site"] = q_low
        open_url_in_chrome(direct_url, dry_run=dry_run, new_window=True)
        if any(w in (query + " " + spec_clean).lower() for w in ("karo", "kholo", "chalao", "pehli", "pehla", "pahli", "pahla", "pehle", "pahle", "link")):
            return True, f"Chrome me {clean_q} search karke pehli link khol raha hoon."
        return True, f"Searching for {clean_q} on Chrome and opening the first result."

    # 2. Results fetch or dry-run mock
    if dry_run:
        results = [
            {"title": f"Top result for {clean_q}", "url": f"https://en.wikipedia.org/wiki/{urllib.parse.quote(clean_q)}", "snippet": "Sample result"}
        ]
    else:
        results = _fetch_search_results(clean_q)

    if not results:
        lucky_url = f"https://www.google.com/search?btnI=1&q={urllib.parse.quote_plus(clean_q)}"
        _STATE["last_query"] = clean_q
        open_url_in_chrome(lucky_url, dry_run=dry_run, new_window=True)
        if any(w in (query + " " + spec_clean).lower() for w in ("karo", "kholo", "chalao", "pehli", "pehla")):
            return True, f"Chrome me {clean_q} search karke top result khol raha hoon."
        return True, f"Searching for {clean_q} on Chrome and opening the top result."

    if target_idx >= len(results):
        target_idx = len(results) - 1

    selected = results[target_idx]
    title = selected.get("title", f"Result for {clean_q}")
    url = selected.get("url", "")
    if not url or not is_safe_url(url):
        url = f"https://www.google.com/search?q={urllib.parse.quote_plus(clean_q)}"

    _STATE["last_query"] = clean_q
    _STATE["results"] = results
    open_url_in_chrome(url, dry_run=dry_run, new_window=True)

    ordinal_names = ["first", "second", "third", "fourth", "fifth"]
    ord_en = ordinal_names[target_idx] if target_idx < len(ordinal_names) else f"number {target_idx+1}"
    ord_hi = "pehli" if target_idx == 0 else ("dusri" if target_idx == 1 else "teesri")

    if any(w in (query + " " + spec_clean).lower() for w in ("karo", "kholo", "chalao", "pehli", "pehla", "dusra", "dusri", "link")):
        return True, f"Chrome me {clean_q} search karke {ord_hi} link khol raha hoon: {title}."
    return True, f"Searching for {clean_q} on Chrome and opening the {ord_en} result: {title}."



# --- Search Result Link Clicking -----------------------------------------

def click_result_link(target_spec: str = "first", dry_run: bool = False) -> tuple[bool, str]:
    """Click/open a specific search result link in Chrome."""
    spec_clean = target_spec.lower().strip()

    # Determine index
    target_idx = 0
    matched_ordinal = False
    for word, idx in _ORDINALS_MAP.items():
        if re.search(rf"\b{re.escape(word)}\b", spec_clean):
            target_idx = idx
            matched_ordinal = True
            break

    # If results are not cached yet but we have last_query, do an inline fetch
    results = _STATE.get("results") or []
    if not results and _STATE.get("last_query"):
        results = _fetch_search_results(_STATE["last_query"])
        _STATE["results"] = results

    if not results:
        return True, (
            "I don't have any search results from Chrome yet. "
            "Please ask me to search on Chrome first."
        )

    # Check bounds
    if target_idx >= len(results):
        target_idx = len(results) - 1

    selected = results[target_idx]
    title = selected.get("title", "the website")
    url = selected.get("url", "")

    if not url or not is_safe_url(url):
        return True, "Sorry, the selected link address looks invalid."

    open_url_in_chrome(url, dry_run=dry_run)

    ordinal_names = ["first", "second", "third", "fourth", "fifth"]
    ord_name = ordinal_names[target_idx] if target_idx < len(ordinal_names) else f"number {target_idx + 1}"

    # Hinglish response if command had Hindi markers
    if any(w in spec_clean for w in ("pehla", "pehle", "dusra", "dusre", "teesra", "kholo", "click karo")):
        return True, f"{ord_name.capitalize()} link khol raha hoon: {title}."
    return True, f"Opening the {ord_name} result: {title}."


# --- Gmail Drafting in Chrome --------------------------------------------

def _resolve_recipient_email(recipient_name: str) -> str:
    """Find email for recipient_name from contacts.csv or return directly if valid email."""
    raw = recipient_name.strip()
    if "@" in raw:
        return raw

    try:
        from jarvis.skills.email import find_emails
        emails = find_emails(raw)
        if emails:
            return emails[0]
    except Exception as exc:
        print(f"[browser_control] contact resolution error: {exc}")

    return raw


def draft_gmail_in_chrome(
    recipient: str,
    message: str,
    subject: str | None = None,
    dry_run: bool = False
) -> tuple[bool, str]:
    """Create a Gmail web compose draft in Chrome with pre-filled To, Subject, and Body."""
    recip_clean = recipient.strip()
    msg_clean = message.strip()

    if not recip_clean:
        return True, "Who would you like me to draft the Gmail to?"

    to_email = _resolve_recipient_email(recip_clean)

    # Derive subject if not explicitly given
    if not subject:
        words = msg_clean.split()
        if len(words) <= 6:
            subject = msg_clean.capitalize()
        else:
            subject = " ".join(words[:6]).capitalize() + "..."
        if not subject:
            subject = "Quick Note"

    # Construct official Gmail Web Compose URL
    params = {
        "view": "cm",
        "fs": "1",
        "to": to_email,
        "su": subject,
        "body": msg_clean,
    }
    compose_url = f"https://mail.google.com/mail/?{urllib.parse.urlencode(params)}"

    _STATE["active_site"] = "gmail"
    open_url_in_chrome(compose_url, dry_run=dry_run)

    recipient_display = recip_clean if recip_clean != to_email else to_email
    return True, (
        f"Opened Gmail draft to {recipient_display} with subject '{subject}'. "
        "You can review and send it directly in Chrome."
    )


# --- Intent Parsing ------------------------------------------------------

# --- Intent Parsing ------------------------------------------------------

# Conversational retry prefix (e.g. "I said that open the chrome", "i told it to open the crome", "maine bola chrome kholo")
_RETRY_PREFIX = (
    r"(?:(?:i\s+said(?:\s+that)?|i\s+told(?:\s+(?:you|it))?(?:\s+to)?|"
    r"maine\s+kaha(?:\s+ki)?|maine\s+bola(?:\s+ki)?)\s+)?"
)

# 1. Plain Open Chrome (e.g. "Jarvis Chrome open karo", "open chrome", "open the chrome", "crome open karo", "chrome kholo")
_OPEN_CHROME_PLAIN_RE = re.compile(
    rf"^{_RETRY_PREFIX}(?:(?:hey\s+|ok\s+)?jarvis\s+|please\s+|pls\s+|kripya\s+|zara\s+)?"
    r"(?:(?:open|launch|start|kholo|chalao)\s+(?:the\s+)?(?:google\s+)?(?:chrome|crome|browser)(?:\s+(?:browser|app|application))?|"
    r"(?:google\s+)?(?:chrome|crome|browser)(?:\s+(?:browser|app|application))?\s+(?:open\s+karo|kholo|chalao|start\s+karo))$",
    re.IGNORECASE,
)

# 2. Open Chrome with search query (e.g. "Chrome open karo and search for AI", "Chrome kholo aur search karo latest news")
_CHROME_OPEN_WITH_SEARCH_RE = re.compile(
    rf"^{_RETRY_PREFIX}(?:(?:hey\s+|ok\s+)?jarvis\s+|please\s+|pls\s+|kripya\s+|zara\s+)?"
    r"(?:google\s+)?(?:chrome|crome|browser)\s+(?:open\s+karo|kholo|chalao)\s*(?:and|aur|,)?\s*(?:search\s*(?:for|karo)?|dhundo|find)?\s+(.+)$",
    re.IGNORECASE,
)

# 3. Compound: Search query AND Click/Open specific result link
_COMPOUND_SEARCH_CLICK_RE = re.compile(
    rf"^{_RETRY_PREFIX}(?:(?:hey\s+|ok\s+)?jarvis\s+|please\s+|pls\s+|kripya\s+|zara\s+)?"
    r"(?:(?:open|kholo|chalao)\s+(?:the\s+)?(?:google\s+)?(?:chrome|crome|browser)\s*(?:aur|and|,)?\s*)?"
    r"(?:(?:google\s+)?(?:chrome|crome|browser)\s+(?:open\s+karo|kholo|chalao)\s*(?:aur|and|,)?\s*)?"
    r"(?:"
    # Pattern A: uske search bar me [query] likho aur [ordinal] link click karo
    r"(?:(?:uske\s+)?search\s*bar\s+\b(?:mein|me)\b\s*(?:jakar)?\s*(.+?)\s*(?:likho|type\s+karo|search\s+karo|dal\s+do)"
    r"(?:\s*(?:aur|and|,)?\s*(?:jo\s+)?([a-z0-9]+)?\s*(?:link|result|website)\s*(?:hai)?\s*(?:use)?\s*(?:click\s*(?:kar\s+do|karo)?|kholo|open\s*(?:kar\s+do|karo)?))?)"
    r"|"
    # Pattern C: chrome me search karo [query] aur [ordinal] link kholo
    r"(?:(?:google\s+)?(?:chrome|crome|browser)\s+\b(?:par|pe|me|mein)\b\s*(?:search\s+karo\s+|dhundo\s+)?(.+?)\s*(?:aur|and|,)\s*(?:jo\s+)?([a-z0-9]+)?\s*(?:link|result|website)\s*(?:kholo|click\s+karo|open\s+karo))"
    r"|"
    # Pattern B: [query] (search karo) aur/and click on the [ordinal] link (that what it appear)
    r"(?:(?:search\s+(?:for\s+)?|open\s+)?(.+?)(?:\s+search\s+karo)?\s+(?:and|aur)\s+(?:jo\s+)?(?:click\s+(?:on\s+)?|open\s+)?(?:the\s+)?([a-z0-9]+)?\s*(?:link|result|website)(?:\s+hai)?(?:\s+use)?(?:\s+click\s*(?:kar\s+do|karo)?|\s+kholo|\s+open\s*(?:kar\s+do|karo)?)?(?:\s+that\s+.*)?)"
    r")$",
    re.IGNORECASE,
)

# 4. Search in Chrome
_CHROME_SEARCH_RE = re.compile(
    rf"^{_RETRY_PREFIX}(?:(?:hey\s+|ok\s+)?jarvis\s+|please\s+|pls\s+|kripya\s+|zara\s+)?"
    r"(?:open\s+(?:google\s+)?(?:chrome|crome|browser)\s+(?:and|aur)?\s*(?:search\s+(?:for)?|dhundo|find)?\s*(.+)|"
    r"(?:google\s+)?(?:chrome|crome|browser)\s+(?:par|pe|me|mein)\s*(?:search\s+(?:karo|kar\s+do)?|dhundo|kholo)?\s*(.+)|"
    r"search\s+(?:for\s+)?(.+?)\s+(?:on|in|par|pe|me|mein)\s+(?:google\s+)?(?:chrome|crome|browser)|"
    r"search\s+on\s+(?:google\s+)?(?:chrome|crome|browser)\s+(?:for\s+)?(.+))$",
    re.IGNORECASE,
)

# 5. Click Result Link
_LINK_CLICK_RE = re.compile(
    rf"^{_RETRY_PREFIX}(?:(?:hey\s+|ok\s+)?jarvis\s+|please\s+|pls\s+|kripya\s+|zara\s+)?"
    r"(?:click\s+(?:on\s+)?(?:the\s+)?([a-z0-9]+)?\s*(?:link|result|website)|"
    r"open\s+(?:the\s+)?([a-z0-9]+)?\s*(?:link|result|website)|"
    r"([a-z0-9]+)\s+(?:link|result|website)\s+(?:par\s+click\s+karo|kholo|open\s+karo)|"
    r"(?:link|result|website)\s+(?:par\s+click\s+karo|kholo|open\s+karo))$",
    re.IGNORECASE,
)

# 6. Gmail Drafting in Chrome
_GMAIL_DRAFT_RE = re.compile(
    rf"^{_RETRY_PREFIX}(?:(?:hey\s+|ok\s+)?jarvis\s+|please\s+|pls\s+|kripya\s+|zara\s+)?"
    r"(?:(?:open\s+gmail\s+(?:and|aur)?\s*)?"
    r"(?:draft\s+(?:an?\s+)?(?:email|mail)|compose\s+(?:an?\s+)?(?:email|mail)|mail\s+draft\s+karo|email\s+draft\s+karo)\s+"
    r"(?:to|for|ko)\s+([^,]+?)\s+(?:saying|that|about|ki|ke\s+baare\s+mein)\s+(.+)|"
    r"(?:open\s+gmail\s+(?:and|aur)?\s*draft\s+(?:an?\s+)?(?:email|mail)\s+(?:to|for|ko)\s+([^,]+?)))$",
    re.IGNORECASE,
)


def try_browser_control(text: str, dry_run: bool = False) -> tuple[bool, str]:
    """Detect and execute Chrome open, search, link clicking, and Gmail drafting.

    Returns:
        (handled, spoken_message)
    """
    if not text:
        return False, ""

    clean_text = text.strip()

    # A. Check Gmail draft intent
    gm = _GMAIL_DRAFT_RE.match(clean_text)
    if gm:
        recip = gm.group(1) or gm.group(3) or ""
        body = gm.group(2) or "Hello, please find the details attached."
        return draft_gmail_in_chrome(recip, body, dry_run=dry_run)

    # Contextual check: if current active site is gmail and user says "draft a mail to..."
    if _STATE.get("active_site") == "gmail" and re.search(r"\b(?:draft|compose)\b", clean_text, re.IGNORECASE):
        m_recip = re.search(r"\b(?:to|ko|for)\s+([a-zA-Z0-9_. -]+?)(?:\s+(?:saying|that|about|ki)\s+(.+)|$)", clean_text, re.IGNORECASE)
        if m_recip:
            recip = m_recip.group(1).strip()
            body = (m_recip.group(2) or "Hello, writing to follow up.").strip()
            return draft_gmail_in_chrome(recip, body, dry_run=dry_run)

    # B. Check Link clicking intent
    lm = _LINK_CLICK_RE.match(clean_text)
    if lm:
        target_spec = lm.group(1) or lm.group(2) or lm.group(3) or "first"
        return click_result_link(target_spec, dry_run=dry_run)

    # C. Check Compound Search & Click intent (e.g. "search python and click first link", "uske search bar me Gmail likho aur pehli link click kar do")
    cm = _COMPOUND_SEARCH_CLICK_RE.match(clean_text)
    if cm:
        groups = [g for g in cm.groups() if g is not None]
        query_val = groups[0].strip() if groups else ""
        target_spec_val = groups[1].strip() if len(groups) > 1 else None
        if query_val:
            if target_spec_val:
                return search_and_click_result(query_val, target_spec_val, dry_run=dry_run)
            return execute_chrome_search(query_val, dry_run=dry_run)

    # D. Check Chrome open with search query (e.g. "Chrome open karo and search for latest news")
    om = _CHROME_OPEN_WITH_SEARCH_RE.match(clean_text)
    if om:
        query = om.group(1).strip()
        query = re.sub(r"\s+(?:search\s+karo|search|dhundo|kholo|chalao)$", "", query, flags=re.IGNORECASE).strip()
        if query:
            return execute_chrome_search(query, dry_run=dry_run)

    # E. Check Chrome search intent
    sm = _CHROME_SEARCH_RE.match(clean_text)
    if sm:
        query = sm.group(1) or sm.group(2) or sm.group(3) or sm.group(4) or ""
        query = query.strip()
        query = re.sub(r"\s+(?:search\s+karo|search|dhundo|kholo|chalao)$", "", query, flags=re.IGNORECASE).strip()
        if query:
            return execute_chrome_search(query, dry_run=dry_run)

    # F. Check Plain Open Chrome intent (e.g. "Jarvis Chrome open karo", "open chrome", "crome open karo")
    op = _OPEN_CHROME_PLAIN_RE.match(clean_text)
    if op:
        open_url_in_chrome("https://www.google.com", dry_run=dry_run, new_window=True)
        if any(w in clean_text.lower() for w in ("karo", "kholo", "chalao")):
            return True, "Chrome khol raha hoon."
        return True, "Opening Chrome."

    return False, ""


def get_browser_state() -> dict[str, Any]:
    """Return a copy of the current browser session state."""
    return dict(_STATE)


def reset_browser_state() -> None:
    """Reset browser state (primarily for tests)."""
    _STATE["last_query"] = ""
    _STATE["results"] = []
    _STATE["active_site"] = None
    _STATE["last_opened_url"] = None
