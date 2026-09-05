"""
launch_ui.py — One-click launcher for the JARVIS Neural Dashboard.

Starts the Flask backend server and automatically opens the user's default
browser to the web interface.
"""

import os
import sys
import time
import webbrowser
import threading
from server import app


def open_browser(url: str, delay_sec: float = 1.2):
    time.sleep(delay_sec)
    print(f"[launcher] Opening browser at {url}")
    webbrowser.open(url)


def main():
    port = int(os.environ.get("PORT", 5000))
    url = f"http://localhost:{port}"

    print("=" * 60)
    print("  J.A.R.V.I.S. // Web Interface Launcher")
    print(f"  Interface URL: {url}")
    print("  Close this window or press Ctrl+C to terminate.")
    print("=" * 60)

    # Launch browser after a brief delay so server has bound port
    threading.Thread(target=open_browser, args=(url,), daemon=True).start()

    # Start Flask server
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
