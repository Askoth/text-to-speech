#!/usr/bin/env python3
"""
app.py
Wrapper to maintain compatibility with the command: python app.py

The real code is in src/app.py
"""

if __name__ == "__main__":
    import os

    from src.app import app
    from src.config import check_prerequisites

    errors = check_prerequisites(mode="web")
    if errors:
        raise SystemExit(1)

    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    print("\n  TTS Reader Web UI")
    print("  http://localhost:5000\n")
    app.run(debug=debug, port=5000)
