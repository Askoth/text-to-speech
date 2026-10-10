"""text_to_speech package — CLI dispatcher."""

import sys

from .cli import validate


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint: text-to-speech <command>."""
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print("usage: text-to-speech <validate>", file=sys.stderr)
        return 1
    cmd = args[0]
    if cmd == "validate":
        return validate()
    print(f"unknown command: {cmd}", file=sys.stderr)
    return 1
