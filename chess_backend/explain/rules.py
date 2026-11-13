"""Deterministic rules: one analysis row in, structured annotations out.

Only engine data and the replayed position are used. A rule that cannot be
supported (say, no reply line because the other side's moves were filtered
out) stays silent instead of guessing.
"""
from __future__ import annotations

import chess

from .engine_data import PIECE_NAMES, material_net, parse_pv, pov

CLASSIFIED = ("inaccuracy", "mistake", "blunder")
REPLY_PLIES = 4          # the opponent's line after the played move, looked at this deep
OWN_LINE_PLIES = 4       # the engine's best line, looked at this deep
MIN_HUNG_NET = 2         # points of material (minor piece or more) for a hung piece
DRAW_REASONS = {
    chess.Termination.INSUFFICIENT_MATERIAL: "insufficient_material",
    chess.Termination.THREEFOLD_REPETITION: "threefold_repetition",
    chess.Termination.FIVEFOLD_REPETITION: "fivefold_repetition",
    chess.Termination.FIFTY_MOVES: "fifty_moves",
    chess.Termination.SEVENTYFIVE_MOVES: "seventyfive_moves",
}


def note(key: str, **params) -> dict:
    return {"key": key, "params": {k: v for k, v in params.items() if v is not None}}


def _is_best(row: dict) -> bool:
    if row.get("played_uci") and row.get("best_move_uci"):
        return row["played_uci"] == row["best_move_uci"]
    return row.get("played") == row.get("best_move_san")


def _reply(row: dict, nxt: dict | None) -> dict | None:
    """The opponent's next row, if the data really contains it."""
    return nxt if nxt and nxt.get("ply") == row["ply"] + 1 else None


def terminal_notes(row: dict, board_after: chess.Board | None) -> list[dict]:
    if not row.get("terminal_result"):
        return []
    if str(row.get("played", "")).endswith("#"):
        return [note("terminal_checkmate", winner=row["side"])]
    if board_after is None:
        return []
    if board_after.is_stalemate():
        return [note("terminal_stalemate")]
    outcome = board_after.outcome(claim_draw=True)
    reason = DRAW_REASONS.get(outcome.termination) if outcome else None
    return [note("terminal_draw", reason=reason)] if reason else []


def mate_notes(row: dict, nxt: dict | None) -> list[dict]:
    side = row["side"]
    _, before_mate = pov(row.get("eval_before"), side)
    _, after_mate = pov(row.get("eval_after"), side)
    if before_mate is not None and before_mate > 0 and not _is_best(row) \
            and (after_mate is None or after_mate < 0):
        return [note("missed_mate", best=row.get("best_move_san"), mate_in=before_mate)]
    if after_mate is not None and after_mate < 0 and (before_mate is None or before_mate > 0):
        reply = _reply(row, nxt)
        return [note("allowed_mate", mate_in=-after_mate,
                     reply=reply.get("best_move_san") if reply else None)]
    return []


def material_notes(row: dict, nxt: dict | None, before: chess.Board,
                   move: chess.Move) -> list[dict]:
    """Material lost to the engine's reply line, or won by a capture that was missed."""
    reply = _reply(row, nxt)
    if reply is None:
        return []                      # no reply line in the data: say nothing
    mover = before.turn
    after = before.copy(stack=False)
    after.push(move)
    line = parse_pv(after, reply.get("best_pv_san"), REPLY_PLIES)
    played_net = material_net(before, [move], mover) + material_net(after, line, mover)
    if line and played_net <= -1:
        piece = before.piece_at(move.from_square)
        first = line[0]
        cp_loss = row.get("cp_loss")
        if (piece and piece.piece_type != chess.PAWN and after.is_capture(first)
                and first.to_square == move.to_square and played_net <= -MIN_HUNG_NET):
            return [note("hung_piece", piece=PIECE_NAMES[piece.piece_type],
                         square=chess.square_name(move.to_square),
                         captured_by=after.san(first), cp=cp_loss)]
        return [note("lost_material", amount=-played_net)]
    best = parse_pv(before, row.get("best_pv_san"), OWN_LINE_PLIES)
    if best and before.is_capture(best[0]):
        best_net = material_net(before, best, mover)
        if best_net >= 1 and best_net - played_net >= 1:
            return [note("missed_capture", best=row.get("best_move_san"), gain=best_net)]
    return []


def quality_notes(row: dict, nxt: dict | None, board: tuple | None) -> list[dict]:
    side, cls = row["side"], row.get("classification")
    before_cp, before_mate = pov(row.get("eval_before"), side)
    after_cp, after_mate = pov(row.get("eval_after"), side)
    if cls == "none":
        return [note("best_move")] if _is_best(row) else \
               [note("good_alternative", best=row.get("best_move_san"))]
    if cls == "unclassified_mate":
        return [note("unclear_mate")]     # mate distance changed: no cause can be claimed
    if cls not in CLASSIFIED:
        return []
    notes = mate_notes(row, nxt)
    if not notes and board is not None:
        notes = material_notes(row, nxt, *board)
    explained = bool(notes)
    reply = _reply(row, nxt)
    if not explained and cls in ("mistake", "blunder") and reply and reply.get("best_move_san"):
        notes.append(note("refutation", reply=reply["best_move_san"]))
        explained = True
    best_cp = before_cp if before_mate is None else None
    notes.append(note("engine_preferred", best=row.get("best_move_san"), best_cp=best_cp))
    if not explained and before_cp is not None and after_cp is not None:
        notes.append(note("eval_swing", before_cp=before_cp, after_cp=after_cp))
    return notes
