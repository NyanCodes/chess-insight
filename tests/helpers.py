"""Builders for analysis-JSON rows without an engine."""
import json
from pathlib import Path

import chess

DATA = Path(__file__).parent / "data"
EVEN = {"cp_white": 0, "mate_white": None}


def load_fixture(name: str) -> dict:
    return json.loads((DATA / f"{name}_analysis.json").read_text())


def make_game(sans, *, fen=None, overrides=None, headers=None, number=1, result="*") -> dict:
    """Rows shaped like analysis.py output; `overrides` maps ply -> field changes."""
    board = chess.Board(fen) if fen else chess.Board()
    rows = []
    for ply, san in enumerate(sans, 1):
        move = board.parse_san(san)
        side = "white" if board.turn else "black"
        row = {"ply": ply, "side": side, "played": san, "played_uci": move.uci(),
               "best_move_san": san, "best_move_uci": move.uci(), "best_pv_san": "",
               "eval_before": dict(EVEN), "eval_after": dict(EVEN), "terminal_result": None,
               "cp_loss": 0, "classification": "none"}
        row.update((overrides or {}).get(ply, {}))
        board.push(move)
        rows.append(row)
    head = {**(headers or {}), **({"SetUp": "1", "FEN": fen} if fen else {})}
    return {"game": number, "headers": head, "ply_count": len(sans), "result": result,
            "final_fen": board.fen(), "moves": rows}


def report_data(*games) -> dict:
    return {"ok": True, "games": list(games)}
