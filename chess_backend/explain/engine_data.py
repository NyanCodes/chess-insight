"""Helpers that read the analysis JSON and replay lines. Signs are the trap here:
cp_white/mate_white are always White-relative; cp_loss is mover-relative."""
from __future__ import annotations

import re

import chess

VALUES = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9}
PIECE_NAMES = {chess.PAWN: "pawn", chess.KNIGHT: "knight", chess.BISHOP: "bishop",
               chess.ROOK: "rook", chess.QUEEN: "queen", chess.KING: "king"}
_MOVE_NUMBER = re.compile(r"\d+\.(?:\.\.)?")


def pov(evaluation: dict | None, side: str) -> tuple[int | None, int | None]:
    """(cp, mate) from the mover's point of view; positive mate = the mover mates."""
    if not evaluation:
        return None, None
    sign = 1 if side == "white" else -1
    cp, mate = evaluation.get("cp_white"), evaluation.get("mate_white")
    return (None if cp is None else sign * cp), (None if mate is None else sign * mate)


def parse_pv(board: chess.Board, text: str | None, plies: int) -> list[chess.Move]:
    """Replay a variation_san string from `board`; stop quietly at anything unparsable."""
    moves, probe = [], board.copy(stack=False)
    for token in _MOVE_NUMBER.sub(" ", text or "").split()[:plies]:
        try:
            move = probe.parse_san(token)
        except ValueError:
            break
        moves.append(move)
        probe.push(move)
    return moves


def captured_value(board: chess.Board, move: chess.Move) -> int:
    if board.is_en_passant(move):
        return VALUES[chess.PAWN]
    piece = board.piece_at(move.to_square)
    return VALUES.get(piece.piece_type, 0) if piece else 0


def material_net(board: chess.Board, moves: list[chess.Move], mover: chess.Color) -> int:
    """Material the mover gains minus what the opponent gains while `moves` are played."""
    probe, net = board.copy(stack=False), 0
    for move in moves:
        value = captured_value(probe, move)
        net += value if probe.turn == mover else -value
        probe.push(move)
    return net
