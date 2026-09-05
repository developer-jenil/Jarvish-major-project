"""Allow `python -m jarvis` to run the assistant.

This is the simplest possible shim — the real CLI lives in jarvis/cli.py.
"""

import sys

from jarvis.cli import main

if __name__ == "__main__":
    sys.exit(main())