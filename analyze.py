#!/usr/bin/env python3
"""Compatibility entry point for the standalone chess_backend CLI."""
from chess_backend.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
