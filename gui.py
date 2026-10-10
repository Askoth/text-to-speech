#!/usr/bin/env python3
"""Shim → text_to_speech.gui:main"""

import sys

from src.text_to_speech.gui import main

if __name__ == "__main__":
    verbose = "--verbose" in sys.argv
    try:
        sys.exit(main(verbose=verbose))
    except Exception as e:
        print(f"GUI error: {e}", file=sys.stderr)
        sys.exit(1)
