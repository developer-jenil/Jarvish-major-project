"""
jarvis/memory.py — Persistent conversation memory.

Stores the last few conversation turns so JARVIS can keep context *across*
restarts, not just within one session. Turn history lives in a small JSON
file under <project>/data/ (gitignored).

Design
------
- A module-level cache avoids re-reading the file on every turn.
- `load_history(limit)` returns the most recent `limit` turns (oldest first)
  so the same 6-turn sliding window used before is preserved.
- `append_turn(user, assistant)` adds a pair and trims to
  `MAX_HISTORY_TURNS`, then persists.
- Every function is safe to call when the data directory cannot be created
  or the file is corrupt — the assistant must never crash over memory.

Why a file and not sqlite? This project is a student major project and the
data is tiny (tens of turns). A readable JSON file is easier to explain in a
review and needs zero extra dependencies. sqlite would be overkill.
"""

from __future__ import annotations

import json
from pathlib import Path

# Sliding-window size preserved from the old in-memory list in main.py.
MAX_HISTORY_TURNS = 6

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DATA_DIR = _PROJECT_ROOT / "data"
_HISTORY_PATH = _DATA_DIR / "conversation_history.json"

# In-memory cache: loaded once on first access, updated on every append.
_cached: list[dict] | None = None
# Path override for tests (set via _use_store()).
_HISTORY_PATH_OVERRIDE: Path | None = None


def _store_path() -> Path:
    """The active history file path (overridable for tests)."""
    return _HISTORY_PATH_OVERRIDE if _HISTORY_PATH_OVERRIDE is not None else _HISTORY_PATH


def _use_store(path: Path) -> None:
    """Point the store at a specific file and reset the cache (for tests)."""
    global _cached, _HISTORY_PATH_OVERRIDE
    _HISTORY_PATH_OVERRIDE = path
    _cached = None


def _load_from_disk() -> list[dict]:
    """Read the history file, tolerating absent/corrupt data."""
    path = _store_path()
    try:
        if path.exists():
            raw = path.read_text(encoding="utf-8")
            data = json.loads(raw)
            if isinstance(data, list):
                turns = [
                    t for t in data
                    if isinstance(t, dict) and t.get("role") in ("user", "assistant")
                    and isinstance(t.get("content"), str)
                ]
                return turns[-MAX_HISTORY_TURNS:]
    except (OSError, ValueError) as exc:
        print(f"[memory] could not read {path.name}: {exc}")
    return []


def _save(turns: list[dict]) -> None:
    """Persist the turn list, silently tolerating write failures."""
    path = _store_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(turns, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError as exc:
        print(f"[memory] could not write {path.name}: {exc}")


def load_history(limit: int = MAX_HISTORY_TURNS) -> list[dict]:
    """Return the most recent `limit` turns (oldest first).

    Reads the file on the first call, then uses the cached copy.
    """
    global _cached
    if _cached is None:
        _cached = _load_from_disk()
    return _cached[-limit:]


def append_turn(user_text: str, assistant_text: str) -> None:
    """Record one user/assistant exchange and persist it.

    Maintains a sliding window of MAX_HISTORY_TURNS messages.
    """
    global _cached
    if _cached is None:
        _cached = _load_from_disk()
    _cached.append({"role": "user", "content": user_text})
    _cached.append({"role": "assistant", "content": assistant_text})
    _cached = _cached[-MAX_HISTORY_TURNS:]
    _save(_cached)


def clear_history() -> None:
    """Wipe the conversation history (memory reset)."""
    global _cached
    _cached = []
    _save(_cached)


if __name__ == "__main__":
    # Quick demo: append a couple of turns and show the window.
    import tempfile
    _use_store(Path(tempfile.mkdtemp()) / "history.json")
    append_turn("Hello Jarvis", "Namaste! How can I help?")
    append_turn("Open chrome", "Opening Chrome.")
    print("history loaded:", load_history())