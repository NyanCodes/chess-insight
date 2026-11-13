"""Plain-language coach commentary built from engine-grounded JSON, fitted to a character budget.

Every word the reader sees lives in i18n/locales/*.json. This module only
decides which sentences apply, using the structured annotations from explain/,
so another language is a new catalog file and no code change.
"""
from __future__ import annotations

import re

import chess

from .explain import annotate_game
from .i18n import Catalog, join_list, render_annotation, say

SIDES = ("white", "black")
RANK = {"inaccuracy": 1, "mistake": 2, "blunder": 3}
BANDS = ("winning", "better", "level", "worse", "losing")
SOUND_LOSS = 25          # cp: "a sound choice" is only claimed within this of the engine's best
# What explain/ can say about the turning move, most informative first.
PRIMARY = ("allowed_mate", "hung_piece", "lost_material", "missed_mate", "missed_capture",
           "refutation", "unclear_mate")
# Story-level catalog keys this module uses (checked against en.json by the tests).
NARRATION_KEYS = frozenset({
    "narr.heading", "narr.game_header", "narr.game_header_plain", "narr.outcome.checkmate",
    "narr.outcome.won", "narr.outcome.stalemate", "narr.outcome.draw", "narr.outcome.unknown",
    "narr.players", "narr.unknown_name", "narr.you_played", "narr.book.through",
    "narr.book.opened", "narr.left_book.sound", "narr.left_book.weak", "narr.left_book.plain",
    "narr.turn.lead", "narr.slip.lead", "narr.took_chance", "narr.passed", "narr.tally.none",
    "narr.tally.errors", "narr.accuracy", "narr.clean", "narr.trimmed", "narr.exceeds",
    "narr.disclaimer", "narr.position.title", "narr.position.fen", "narr.position.over",
    "narr.position.candidate", "narr.position.pv", "narr.position.advice",
    "narr.position.eval.mate", "narr.position.eval.over", "narr.position.eval.unavailable",
    "actor.you", "actor.white", "actor.black", "actor_mid.you", "actor_mid.white",
    "actor_mid.black",
    *(f"narr.preferred.{band}" for band in BANDS),
    *(f"narr.also.{label}" for label in RANK),
    *(f"narr.tally.{label}" for label in RANK),
})


def _safe(text, length=60) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()[:length]


def _name(headers: dict, key: str) -> str:
    value = _safe(headers.get(key, ""), 35)
    return "" if value == "?" else value


def _band(cp: int) -> str:
    return ("winning" if cp >= 300 else "better" if cp >= 75 else "level" if cp > -75
            else "worse" if cp > -300 else "losing")


def _start_offset(headers: dict) -> int:
    """Plies played before the first listed move (a PGN may start from a FEN)."""
    if headers.get("SetUp") == "1" and headers.get("FEN"):
        start = chess.Board(headers["FEN"])
        return (start.fullmove_number - 1) * 2 + (0 if start.turn else 1)
    return 0


def _notation(row: dict, offset: int) -> str:
    number = (row["ply"] + offset + 1) // 2
    return f"{number}{'.' if row['side'] == 'white' else '...'} {row['played']}"


def _actor(c: Catalog, side: str, player: str, *, mid: bool = False) -> str:
    return c.t(f"{'actor_mid' if mid else 'actor'}.{'you' if side == player else side}")


def _outcome(c: Catalog, game: dict) -> str:
    final = None
    try:
        final = chess.Board(game["final_fen"]) if game.get("final_fen") else None
    except ValueError:
        pass
    if final is not None and final.is_checkmate():
        winner = "black" if final.turn == chess.WHITE else "white"
        return say(c, "narr.outcome.checkmate", winner=winner, plies=game.get("ply_count", 0))
    if final is not None and final.is_stalemate():
        return say(c, "narr.outcome.stalemate")
    result = game.get("result")
    if result in ("1-0", "0-1"):
        return say(c, "narr.outcome.won", winner="white" if result == "1-0" else "black")
    return say(c, "narr.outcome.draw" if result == "1/2-1/2" else "narr.outcome.unknown")


def _header(c: Catalog, game: dict, player: str) -> str:
    headers = game.get("headers", {})
    event = _safe(headers.get("Event", ""), 45)
    number = game.get("game", 1)
    parts = [say(c, "narr.game_header", number=number, event=event) if event not in ("", "?")
             else say(c, "narr.game_header_plain", number=number), _outcome(c, game)]
    white, black = _name(headers, "White"), _name(headers, "Black")
    if white or black:
        unknown = c.t("narr.unknown_name")
        parts.append(say(c, "narr.players", white=white or unknown, black=black or unknown))
    if player != "both":
        parts.append(say(c, "narr.you_played", side=c.t(f"side.{player}")))
    return " ".join(parts)


def _book(c: Catalog, rows: list[dict], notes: dict, player: str, offset: int) -> str:
    run = [r for r in rows if "book_move" in notes[r["ply"]]]
    left = next((r for r in rows if "left_book" in notes[r["ply"]]), None)
    parts = []
    if run:
        last, opening = run[-1], notes[run[-1]["ply"]]["book_move"]["opening"]
        if len(run) > 1:
            parts.append(say(c, "narr.book.through", move=_notation(last, offset), opening=opening))
        else:
            parts.append(say(c, "narr.book.opened", actor=_actor(c, last["side"], player),
                             move=_notation(last, offset), opening=opening))
    if left:
        loss = left.get("cp_loss")
        sound = left.get("classification") == "none" and (
            left.get("played") == left.get("best_move_san") or (loss is not None and loss <= SOUND_LOSS))
        label = ("narr.left_book.weak" if left.get("classification") in RANK else
                 "narr.left_book.sound" if sound else "narr.left_book.plain")
        parts.append(say(c, label, actor=_actor(c, left["side"], player), move=_notation(left, offset),
                         best=left.get("best_move_san", "")))
    return " ".join(parts)


def _severity(row: dict) -> tuple[int, int]:
    loss = row.get("cp_loss")
    return RANK[row["classification"]], 10 ** 6 if loss is None else loss   # mate swings rank highest


def _turning(c: Catalog, rows: list[dict], notes: dict, main: dict, player: str, offset: int) -> str:
    found = notes[main["ply"]]
    move = _notation(main, offset)
    parts = [say(c, "narr.slip.lead" if main["classification"] == "inaccuracy" else "narr.turn.lead",
                 move=move)]
    why = next((k for k in PRIMARY if k in found), "eval_swing" if "eval_swing" in found else None)
    if why:
        parts.append(render_annotation({"key": why, "params": found[why]}, c))
    preferred = found.get("engine_preferred")
    if preferred and "best_cp" in preferred:
        parts.append(say(c, f"narr.preferred.{_band(preferred['best_cp'])}", best=preferred["best"],
                         who=_actor(c, main["side"], player, mid=True)))
    elif preferred:
        parts.append(render_annotation({"key": "engine_preferred", "params": preferred}, c))
    nxt = next((r for r in rows if r["ply"] == main["ply"] + 1), None)
    if "allowed_mate" in found and nxt:
        actor, played = _actor(c, nxt["side"], player), _notation(nxt, offset)
        if nxt.get("played") == nxt.get("best_move_san"):
            parts.append(say(c, "narr.took_chance", actor=actor, move=played))
        elif nxt.get("classification") in RANK:
            parts.append(say(c, "narr.passed", actor=actor, move=played))
    return " ".join(parts)


def _tally(c: Catalog, rows: list[dict], player: str) -> str:
    parts = []
    for side in (SIDES if player == "both" else (player,)):
        counts = {label: sum(r["side"] == side and r.get("classification") == label for r in rows)
                  for label in RANK}
        items = [say(c, f"narr.tally.{label}", count=counts[label])
                 for label in ("blunder", "mistake", "inaccuracy") if counts[label]]
        actor = _actor(c, side, player)
        parts.append(say(c, "narr.tally.errors", actor=actor, items=join_list(items, c))
                     if items else say(c, "narr.tally.none", actor=actor))
    return " ".join(parts)


def _accuracy(c: Catalog, rows: list[dict], player: str) -> str:
    parts = []
    for side in (SIDES if player == "both" else (player,)):
        mine = [r for r in rows if r["side"] == side]
        if mine:
            matched = sum(r.get("played") == r.get("best_move_san") for r in mine)
            parts.append(say(c, "narr.accuracy", actor=_actor(c, side, player),
                             matched=matched, total=len(mine)))
    return " ".join(parts)


def _game_units(c: Catalog, game: dict, player: str, *, single: bool) -> list[tuple[int, str]]:
    """(priority, text) in reading order; a higher priority number is dropped first."""
    rows = game.get("moves", [])
    notes = {n["ply"]: {a["key"]: a["params"] for a in n["annotations"]} for n in annotate_game(game)}
    offset = _start_offset(game.get("headers", {}))
    errors = [r for r in rows if r.get("classification") in RANK and player in ("both", r["side"])]
    main = max(errors, key=_severity, default=None)
    units = [(0, _header(c, game, player))]
    if book := _book(c, rows, notes, player, offset):
        units.append((3, book))
    if main:
        units.append((1, _turning(c, rows, notes, main, player, offset)))
        if single:
            others = sorted([r for r in errors if r is not main], key=_severity, reverse=True)[:2]
            for r in sorted(others, key=lambda r: r["ply"]):
                units.append((5, say(c, f"narr.also.{r['classification']}", actor=_actor(c, r["side"], player),
                                     move=_notation(r, offset), best=r.get("best_move_san", ""))))
    units.append((2, say(c, "narr.clean") if not errors and player == "both" else _tally(c, rows, player)))
    if accuracy := _accuracy(c, rows, player):
        units.append((4, accuracy))
    return units


def render_report(data: dict, *, player: str = "both", max_chars: int = 3500,
                  locale: str = "en") -> str:
    if not data.get("ok") or "games" not in data:
        raise ValueError("expected successful PGN analysis JSON")
    if player not in ("white", "black", "both"):
        raise ValueError("player must be white, black, or both")
    if not 300 <= max_chars <= 3900:
        raise ValueError("max_chars must be 300..3900")
    c = Catalog(locale)
    games = data["games"]
    heading = say(c, "narr.heading", count=len(games))
    footer = say(c, "narr.disclaimer")
    units = [[(prio, text) for prio, text in _game_units(c, g, player, single=len(games) == 1)]
             for g in games]

    def assemble(trimmed: bool) -> str:
        blocks = ["\n".join(text for _, text in game_units) for game_units in units]
        lines = ([heading] if len(games) > 1 else []) + ["\n\n".join(blocks)]
        return "\n\n".join(lines + ([say(c, "narr.trimmed")] if trimmed else []) + [footer])

    trimmed = False
    while len(assemble(trimmed)) > max_chars:
        droppable = [(prio, g, i) for g, game_units in enumerate(units)
                     for i, (prio, _) in enumerate(game_units) if prio > 0]
        if not droppable:
            return heading + "\n" + say(c, "narr.exceeds")
        _, g, i = max(droppable)
        del units[g][i]
        trimmed = True
    return assemble(trimmed)


def _eval(value: dict | None, c: Catalog) -> str:
    if value is None:
        return say(c, "narr.position.eval.over")
    mate = value.get("mate_white")
    if mate is not None:
        return say(c, "narr.position.eval.mate", side=c.t(f"side.{'white' if mate > 0 else 'black'}"),
                   mate=abs(mate))
    cp = value.get("cp_white")
    return f"{cp / 100:+.2f}" if cp is not None else say(c, "narr.position.eval.unavailable")


def render_position(data: dict, *, max_chars: int = 3500, locale: str = "en") -> str:
    if not data.get("ok") or "position" not in data:
        raise ValueError("expected successful position analysis JSON")
    c = Catalog(locale)
    position = data["position"]
    lines = [say(c, "narr.position.title", side=c.t(f"side.{position['turn']}")),
             say(c, "narr.position.fen", fen=_safe(position["fen"], 100))]
    if position.get("result"):
        lines.append(say(c, "narr.position.over", result=position["result"]))
    else:
        for idx, candidate in enumerate(position["lines"][:5], 1):
            lines.append(say(c, "narr.position.candidate", index=idx, move=candidate["best_move_san"],
                             evaluation=_eval(candidate["evaluation"], c)))
            lines.append(say(c, "narr.position.pv", pv=_safe(candidate["pv_san"], 120)))
        lines.append(say(c, "narr.position.advice"))
    return "\n".join(lines)[:max_chars]
