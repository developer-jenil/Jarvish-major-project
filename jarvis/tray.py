"""
jarvis/tray.py — System tray icon for JARVIS.

When the user runs JARVIS with the tray enabled (JARVIS_TRAY=1 env var,
or the --tray flag), the assistant runs in the background with a tray icon
instead of a visible console window. The tray menu lets the user:

    - See the CURRENT engine status (listening / processing / idle)
    - Stop the assistant (graceful exit)
    - Quit (same as stop)

The status is LIVE: `report_status()` may be called from any thread and the
tray menu text updates to match. main.py / cli.py call it at the start of
each loop phase.

Design decisions
----------------
- We use pystray, which creates a native OS tray icon. On Windows this
  is the little icon cluster near the clock; on Linux it uses GTK/AppIndicator.
- The icon is drawn programmatically with Pillow (no asset files needed).
- pystray starts its own event loop internally; we run the JARVIS main
  loop in a separate threading.Thread so both coexist.
- The tray stops itself when the JARVIS loop exits (normally or via
  Ctrl+C), so the user doesn't need to manually quit.
"""

from __future__ import annotations

import os
import threading

try:
    import pystray
except (ImportError, OSError):
    pystray = None

try:
    from PIL import Image, ImageDraw
except (ImportError, OSError):
    Image = None
    ImageDraw = None

# --- Live status ----------------------------------------------------------
# A thread-safe holder for the current assistant phase, so the tray menu can
# show what JARVIS is doing RIGHT NOW (e.g. "Listening for 'Hey Jarvis'",
# "Processing: open chrome", "Speaking"). main.py / cli.py call
# report_status() at the start of each phase; the tray menu updates to match.

# module-level shared state, guarded by a lock (status is small, lock is cheap)
_status = "Idle"
_status_lock = threading.Lock()


def is_tray_available() -> bool:
    """Return True if system tray support (pystray + Pillow) is installed and usable."""
    return pystray is not None and Image is not None


def report_status(phase: str) -> None:
    """Record the current assistant phase for the tray to display.

    Safe to call from any thread. This only affects the tray menu text; it
    never changes program behaviour.
    """
    global _status
    with _status_lock:
        _status = phase


def _get_status() -> str:
    with _status_lock:
        return _status


# --- Icon generation -----------------------------------------------------

def _make_icon(size: int = 64):
    """Draw a simple JARVIS-themed icon (cyan circle on dark background).

    Returns a RGBA PIL Image ready for pystray.
    """
    if Image is None or ImageDraw is None:
        return None
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx, cy = size // 2, size // 2
    r = size // 2 - 2

    # Dark background circle.
    draw.ellipse([cx - r, cy - r, cx + r, cy + r],
                 fill=(20, 25, 40, 255), outline=(0, 200, 220, 255), width=2)

    # Inner ring (JARVIS "eye").
    inner_r = r - 10
    draw.ellipse([cx - inner_r, cy - inner_r, cx + inner_r, cy + inner_r],
                 fill=(0, 180, 200, 180))

    # Pupil.
    pupil_r = inner_r // 3
    draw.ellipse([cx - pupil_r, cy - pupil_r, cx + pupil_r, cy + pupil_r],
                 fill=(10, 15, 30, 255))

    return img


# --- Menu callbacks ------------------------------------------------------

def _on_quit(icon: pystray.Icon, item: pystray.MenuItem):
    """Called when the user clicks Quit from the tray menu."""
    icon.stop()


def _on_stop(icon: pystray.Icon, item: pystray.MenuItem):
    """Called when the user clicks Stop from the tray menu."""
    icon.stop()


# --- Entry point ---------------------------------------------------------

def run_tray(main_fn, title: str = "JARVIS"):
    """Start JARVIS with a system tray icon.

    Args:
        main_fn:  A callable that runs the main assistant loop. It should
                  block until the assistant is stopped (e.g. via Ctrl+C).
                  We run it in a background thread.
        title:    Shown in the tray tooltip.

    The status menu item reflects the assistant's current phase (set via
    report_status() from the running loop).
    """
    if pystray is None or Image is None:
        print("[tray] pystray or Pillow not available in this environment; running in direct console mode.")
        main_fn()
        return

    def _status_item():
        # pystray renders the menu on demand; return the current status text.
        return f"Status: {_get_status()}"

    icon = pystray.Icon(
        "jarvis",
        title,
        _make_icon(),
        menu=pystray.Menu(
            pystray.MenuItem(_status_item, lambda i: None, enabled=False),
            pystray.MenuItem("Stop", _on_stop),
            pystray.MenuItem("Quit", _on_quit),
        ),
    )

    # Show the tray icon, then kick off the main loop in a thread.
    threading.Thread(target=main_fn, daemon=True).start()
    icon.run()


if __name__ == "__main__":
    # Quick sanity check: render the icon and save it.
    img = _make_icon()
    out = os.path.join(os.path.dirname(__file__), "..", "jarvis_icon.png")
    img.save(out)
    print(f"[tray] icon saved to {os.path.abspath(out)}")
