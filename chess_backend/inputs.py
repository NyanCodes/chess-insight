"""Strict enough PGN/FEN validation for reproducible analysis."""
from __future__ import annotations

import io

import chess
import chess.pgn


class InputError(ValueError):
    """Invalid user-supplied chess notation."""


def parse_fen(text: str) -> chess.Board:
    try:
        board = chess.Board(text)
    except ValueError as exc:
        raise InputError(f"invalid FEN: {exc}") from exc
    if not board.is_valid():
        raise InputError(f"invalid FEN position (status {board.status()})")
    return board


def parse_pgn(text: str) -> list[chess.pgn.Game]:
    stream = io.StringIO(text)
    games = []
    while game := chess.pgn.read_game(stream):
        number = len(games) + 1
        if game.errors:
            raise InputError(f"game {number} invalid or illegal move: {game.errors[0]}")
        if not game.end().board().is_valid():
            raise InputError(f"game {number} invalid final position")
        games.append(game)
    if not games:
        raise InputError("PGN contains no games")
    return games
