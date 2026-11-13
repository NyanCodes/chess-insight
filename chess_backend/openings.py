"""Offline opening names from Lichess's CC0 chess-openings TSV dataset."""
from __future__ import annotations

import csv
import re
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).parent / "openings_data"


@lru_cache(maxsize=1)
def opening_lines() -> dict[tuple[str, ...], str]:
    lines: dict[tuple[str, ...], str] = {}
    for path in sorted(DATA.glob("*.tsv")):
        with path.open(encoding="utf-8", newline="") as stream:
            for row in csv.DictReader(stream, delimiter="\t"):
                # PGN move numbers are not part of the move identity.
                moves = tuple(re.sub(r"\b\d+\.(?:\.\.)?", "", row["pgn"]).split())
                if moves:
                    lines.setdefault(moves, row["name"])
    return lines


def opening_names(moves: list[str]) -> list[str | None]:
    """Name only exact known prefixes; never guess a title after a deviation."""
    database = opening_lines()
    return [database.get(tuple(moves[:i])) for i in range(1, len(moves) + 1)]


@lru_cache(maxsize=1)
def known_prefixes() -> frozenset[tuple[str, ...]]:
    """Every prefix of every named line: a move is still 'in theory' while its line
    is one of these, even when that exact prefix has no name of its own."""
    return frozenset(line[:i] for line in opening_lines() for i in range(1, len(line) + 1))
