"""Structured, language-free explanations of an analysed game.

    annotate_game(game) -> [{"ply", "side", "annotations": [{"key", "params"}]}]

Keys and parameters only: turning them into sentences is i18n's job.
"""
from __future__ import annotations

import chess

from ..openings import known_prefixes, opening_names
from .rules import CLASSIFIED, note, quality_notes, terminal_notes
from .schema import ENUMS, KEYS, catalog_key, enum_catalog_keys

__all__ = ["annotate_game", "KEYS", "ENUMS", "catalog_key", "enum_catalog_keys"]


def _start_board(headers: dict) -> chess.Board:
    if headers.get("SetUp") == "1" and headers.get("FEN"):
        return chess.Board(headers["FEN"])
    return chess.Board()


def book_run(game: dict) -> tuple[list[str], bool]:
    """(opening name per move, left_theory) for the unbroken run of known theory.

    A move is in theory while its line is a prefix of some named opening line;
    the name shown is the most specific one reached so far. The run also stops
    at the first move the engine flags (that error is reported on its own, not
    as "leaving book"). Only a standard start with a complete, contiguous move
    list can be matched; otherwise there is no book information (never guessed).
    """
    rows = game.get("moves", [])
    if not rows or _start_board(game.get("headers", {})).fen() != chess.STARTING_FEN \
            or any(row.get("ply") != i for i, row in enumerate(rows, 1)):
        return [], False
    moves = [row["played"] for row in rows]
    names, known = opening_names(moves), known_prefixes()
    run, current = [], None
    for i, row in enumerate(rows):
        if tuple(moves[:i + 1]) not in known:
            return run, bool(run)
        current = names[i] or current
        if current is None or row.get("classification") in CLASSIFIED:
            return run, False
        run.append(current)
    return run, False


def annotate_game(game: dict) -> list[dict]:
    rows = game.get("moves", [])
    board = _start_board(game.get("headers", {}))
    contiguous = all(row.get("ply") == i for i, row in enumerate(rows, 1))
    run, left_theory = book_run(game)
    out = []
    for i, row in enumerate(rows):
        nxt = rows[i + 1] if i + 1 < len(rows) else None
        before, move, after = None, None, None
        if contiguous and board is not None:
            try:
                before = board.copy(stack=False)
                move = (chess.Move.from_uci(row["played_uci"]) if row.get("played_uci")
                        else board.parse_san(row["played"]))
                board.push(move)
                after = board.copy(stack=False)
            except (ValueError, KeyError):
                board, before, move, after = None, None, None, None   # out of sync: stop replaying
        notes = []
        if i < len(run):
            notes.append(note("book_move", opening=run[i]))
        elif left_theory and i == len(run):
            notes.append(note("left_book", san=row.get("played")))
        notes += terminal_notes(row, after)
        notes += quality_notes(row, nxt, (before, move) if before is not None else None)
        out.append({"ply": row["ply"], "side": row["side"], "annotations": notes})
    return out
