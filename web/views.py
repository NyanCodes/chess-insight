"""Shape analysis results for the UI: per-move rows with the explanation layer
shown three ways (rendered sentence, raw key/params, engine numbers) plus the board
data (FENs and arrow squares) the browser needs, since it has no chess engine of its own."""
from __future__ import annotations

import chess

from chess_backend.explain import annotate_game
from chess_backend.explain.engine_data import pov
from chess_backend.i18n import Catalog, render_annotation
from chess_backend.i18n.catalog import LOCALES, normalize
from chess_backend.i18n.numbers import base_language

NATIVE_NAMES = {"en": "English", "my": "မြန်မာ"}       # display names only; not catalog content


def available_locales() -> list[dict]:
    codes = sorted(p.stem for p in LOCALES.glob("*.json"))
    return [{"code": code, "name": NATIVE_NAMES.get(code, code)} for code in codes]


def is_known_locale(code: str) -> bool:
    """A locale is usable when its own catalog or its base language exists (en-GB -> en)."""
    if not code or len(code) > 20 or any(ch in code for ch in "/\\."):
        return False
    have = {item["code"] for item in available_locales()}
    return normalize(code) in have or base_language(code) in have


def _squares(uci: str | None) -> dict | None:
    try:
        move = chess.Move.from_uci(uci) if uci else None
    except ValueError:
        return None
    return {"from": chess.square_name(move.from_square), "to": chess.square_name(move.to_square)} if move else None


def _eval(value: dict | None, side: str) -> dict | None:
    if value is None:
        return None
    cp, mate = pov(value, side)
    return {"cp_white": value.get("cp_white"), "mate_white": value.get("mate_white"),
            "cp_mover": cp, "mate_mover": mate}


def build_annotations(result: dict, games: list, locale: str) -> dict:
    """`games` are the original python-chess games, replayed for FENs and arrows."""
    catalog = Catalog(locale)
    out = []
    for game_json, game in zip(result["games"], games):
        start = game.board()
        offset = (start.fullmove_number - 1) * 2 + (0 if start.turn else 1)
        fens = []                                     # fens[i] = (before, after) for ply i + 1
        board = start.copy()
        for move in game.mainline_moves():
            before = board.fen()
            board.push(move)
            fens.append((before, board.fen()))
        notes = {n["ply"]: n["annotations"] for n in annotate_game(game_json)}
        moves = []
        for row in game_json["moves"]:
            ply = row["ply"]
            before, after = fens[ply - 1] if 0 < ply <= len(fens) else (None, None)
            moves.append({
                "ply": ply, "side": row["side"], "number": (ply + offset + 1) // 2,
                "san": row["played"], "uci": row["played_uci"],
                "played_squares": _squares(row["played_uci"]),
                "best_move_san": row["best_move_san"], "best_move_uci": row["best_move_uci"],
                "best_squares": _squares(row["best_move_uci"]), "best_pv_san": row["best_pv_san"],
                "classification": row["classification"], "cp_loss": row["cp_loss"],
                "eval_before": _eval(row["eval_before"], row["side"]),
                "eval_after": _eval(row["eval_after"], row["side"]),
                "terminal_result": row["terminal_result"],
                "fen_before": before, "fen_after": after,
                "annotations": [{"key": a["key"], "params": a["params"],
                                 "text": render_annotation(a, catalog)} for a in notes.get(ply, [])],
            })
        out.append({"game": game_json["game"], "headers": game_json["headers"],
                    "result": game_json["result"], "ply_count": game_json["ply_count"],
                    "start_fen": start.fen(), "moves": moves})
    return {"locale": catalog.locale, "games": out}


def position_view(result: dict) -> dict:
    return {"fen": result["position"]["fen"], "turn": result["position"]["turn"],
            "result": result["position"].get("result"), "lines": result["position"]["lines"]}
