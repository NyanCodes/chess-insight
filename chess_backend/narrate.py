"""Print the plain-language game story for the JSON CLI's output.

    python -m chess_backend --pgn-file game.pgn --seconds 0.3 --multipv 1 | python -m chess_backend.narrate
    python -m chess_backend.narrate --json-file analysis.json --player black --locale en
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .narration import render_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Turn PGN analysis JSON into a readable game story")
    parser.add_argument("--json-file", type=Path, help="analysis JSON file (default: read standard input)")
    parser.add_argument("--player", choices=("white", "black", "both"), default="both",
                        help="speak to this side as 'you' (default: both sides)")
    parser.add_argument("--locale", default="en", help="catalog language code (default en)")
    parser.add_argument("--max-chars", type=int, default=3500, help="length cap, 300..3900 (default 3500)")
    args = parser.parse_args(argv)
    try:
        text = args.json_file.read_text(encoding="utf-8") if args.json_file else sys.stdin.read()
        data = json.loads(text)
        if not data.get("ok"):
            message = data.get("error", {}).get("message", "the analysis failed")
            print(f"cannot narrate: {message}", file=sys.stderr)
            return 2
        print(render_report(data, player=args.player, max_chars=args.max_chars, locale=args.locale))
        return 0
    except (OSError, ValueError) as exc:          # unreadable file, bad JSON, FEN result, bad option
        print(f"cannot narrate: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
