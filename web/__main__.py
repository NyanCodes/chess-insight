"""Run the inspector:  .venv/bin/python -m web   ->  http://127.0.0.1:8765/"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import uvicorn

from .app import create_app


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Local web UI for the chess analyzer")
    parser.add_argument("--host", default=os.environ.get("CHESS_WEB_HOST", "127.0.0.1"),
                        help="bind address (default 127.0.0.1, localhost only; env CHESS_WEB_HOST)")
    parser.add_argument("--port", type=int, default=int(os.environ.get("CHESS_WEB_PORT", "8765")))
    parser.add_argument("--engine", type=Path, default=None, help="Stockfish binary (default: bundled or PATH)")
    args = parser.parse_args(argv)
    if args.host not in ("127.0.0.1", "localhost", "::1"):
        print(f"warning: binding {args.host}: this server has no authentication or rate limiting",
              file=sys.stderr)
    uvicorn.run(create_app(engine_path=args.engine), host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
