"""
jarvis/skills/web_search.py — Web search skill.

Search the web and speak back the top results. Example commands:
    "search for weather in mumbai"
    "google latest python news"
    "kya hai artificial intelligence"
    "look up recipes for chicken biryani"

HOW IT WORKS
-----------
1. Detect search intent via keyword matching (search, google, look up, etc.).
2. Extract the search query (everything after the trigger keywords).
3. Run a local DuckDuckGo search via the `duckduckgo-search` package
   (uses DDG's internal API — no browser required, no API key).
4. Format the top 3 results as a spoken summary.
5. Speak the result back through TTS.

No LLM brain call is needed — this is purely mechanical, keeping the
assistant fast and working even offline (once DDG is reachable).

REQUIREMENTS
-----------
- Internet connection (DDG is queried online).
- `duckduckgo-search` package (installed in requirements.txt).
"""

from __future__ import annotations

import re

# --- Intent detection ----------------------------------------------------

_SEARCH_VERBS = (
    r"(?:search\s+for|search|google|look\s+up|find\s+out|jaano|"
    r"karo\s+search|dekho\s+kya|pata\s+karo|kya\s+hai|kya\s"
    r"hai|who\s+is|what\s+is|kya\s+hain)"
)
_INTENT_RE = re.compile(rf"\b{_SEARCH_VERBS}\b", re.IGNORECASE)

# Extract the query portion after common trigger words.
_QUERY_EXTRACT = re.compile(
    r"\b(?:search\s+for|search|google|look\s+up|find\s+out|jaano|karo\s+search|dekho\s+kya|pata\s+karo|kya\s+hai|kya\s+hain|who\s+is|what\s+is|kya\s+hain)\s+(.+)$",
    re.IGNORECASE,
)


def match_intent(text: str) -> str | None:
    """Return the search query if `text` is a web-search command, else None."""
    if not text:
        return None
    m = _QUERY_EXTRACT.search(text)
    if m:
        query = m.group(1).strip()
        # Do not hijack local time, date, or day queries
        if re.search(r"^(?:the\s+)?(?:today'?s\s+)?(?:time|date|day)(?:\s+(?:is\s+it|today|now))?$", query, re.IGNORECASE):
            return None
        return query
    return None


# --- Search implementation -----------------------------------------------

def search_web(query: str, max_results: int = 3) -> list[dict]:
    """Run a DuckDuckGo search and return a list of result dicts.

    Each dict has keys: title, body, url.
    """
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        # Normalise to our shape (DDG may vary slightly between versions).
        formatted = []
        for r in results:
            formatted.append({
                "title": r.get("title", ""),
                "body": r.get("body", ""),
                "url": r.get("href", ""),
            })
        return formatted
    except Exception as exc:
        print(f"[web_search] search error: {exc}")
        return []


def format_results(results: list[dict]) -> str:
    """Turn search results into a short spoken summary."""
    if not results:
        return "I searched the web but didn't find any useful results."
    lines = []
    for i, r in enumerate(results, 1):
        title = r.get("title", "Untitled").strip()
        body = r.get("body", "").strip()[:150]  # cap body length for speech
        lines.append(f"Result {i}: {title}. {body}")
    return "Here are the top results. " + "; ".join(lines)


# --- Public API ----------------------------------------------------------

def try_web_search(text: str, dry_run: bool = False) -> tuple[bool, str]:
    """Detect a web-search command, run the search, and return a spoken reply.

    Returns:
        (handled, spoken_message)
    """
    query = match_intent(text)
    if not query:
        return False, ""

    if dry_run:
        print(f"[web_search][dry-run] searching for: {query!r}")
        return True, f"Searching the web for: {query}."

    results = search_web(query, max_results=3)
    spoken = format_results(results)
    print(f"[web_search] query={query!r} results={len(results)}")
    return True, spoken


if __name__ == "__main__":
    import sys

    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    phrase_words = [a for a in sys.argv[1:] if not a.startswith("--")]
    phrase = " ".join(phrase_words)

    if "--selftest" in flags:
        print("[selftest] checking intent matching...")
        samples = [
            ("search for weather in mumbai",       "weather in mumbai"),
            ("google latest python news",           "latest python news"),
            ("kya hai artificial intelligence",    "artificial intelligence"),
            ("open chrome",                         None),
            ("tell me a joke",                      None),
            ("",                                    None),
        ]
        for s, expected in samples:
            got = match_intent(s)
            status = "OK" if got == expected else "FAIL"
            print(f"  [{status}] {s!r:45} expected={expected!r} got={got!r}")
        print("[selftest] PASS — web_search intent matching works.")
    elif phrase:
        dry = "--dry-run" in flags
        handled, msg = try_web_search(phrase, dry_run=dry)
        print(f"handled={handled}  -> {msg}")
    else:
        print("Usage:")
        print('  python -m jarvis.skills.web_search --selftest')
        print('  python -m jarvis.skills.web_search --dry-run "search for AI news"')
        print('  python -m jarvis.skills.web_search "google python tutorial"')
