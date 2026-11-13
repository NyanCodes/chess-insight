"""Evaluate legal positions and whole games with a single Stockfish process."""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import chess
import chess.engine
import chess.pgn

from .classify import Thresholds, classify_loss


class EngineFailure(RuntimeError):
    """A Stockfish process did not produce a usable analysis."""


@dataclass(frozen=True)
class AnalysisConfig:
    seconds: float = 2.0
    multipv: int = 2
    pv_plies: int = 8
    perspective: str = "both"
    threads: int = 2
    hash_mb: int = 256
    thresholds: Thresholds = field(default_factory=Thresholds)

    def __post_init__(self):
        if not 0.01 <= self.seconds <= 20:
            raise ValueError("seconds must be 0.01..20 per position")
        if not 1 <= self.multipv <= 5 or not 1 <= self.pv_plies <= 30:
            raise ValueError("multipv must be 1..5 and pv_plies 1..30")
        if self.perspective not in ("both", "white", "black"):
            raise ValueError("perspective must be white, black, or both")
        if not 1 <= self.threads <= 4 or not 16 <= self.hash_mb <= 1024:
            raise ValueError("threads must be 1..4 and hash_mb 16..1024")


class Analyzer:
    def __init__(self, engine_path: Path, config: AnalysisConfig, *, engine=None):
        self.engine_path = Path(engine_path)
        self.config = config
        self.engine = engine
        self._owns_engine = engine is None

    def __enter__(self):
        if self._owns_engine:
            try:
                self.engine = chess.engine.SimpleEngine.popen_uci(
                    str(self.engine_path), timeout=max(5.0, self.config.seconds + 3.0))
                self.engine.configure({"Threads": self.config.threads, "Hash": self.config.hash_mb})
            except (OSError, TimeoutError, asyncio.TimeoutError, chess.engine.EngineError) as exc:
                if self.engine is not None:
                    self.engine.close()
                raise EngineFailure(f"cannot start/configure Stockfish: {exc}") from exc
        return self

    def __exit__(self, *_):
        if self._owns_engine and self.engine is not None:
            self.engine.close()

    def _analyse(self, board: chess.Board) -> tuple[dict, chess.engine.PovScore | None]:
        if board.is_game_over(claim_draw=True):
            return {"fen": board.fen(), "turn": "white" if board.turn else "black",
                    "result": board.outcome(claim_draw=True).result(), "lines": []}, None
        try:
            infos = self.engine.analyse(board, chess.engine.Limit(time=self.config.seconds),
                                        multipv=self.config.multipv)
        except (TimeoutError, asyncio.TimeoutError) as exc:
            raise EngineFailure(f"Stockfish analysis timed out: {exc}") from exc
        except (chess.engine.EngineTerminatedError, chess.engine.EngineError, OSError) as exc:
            raise EngineFailure(f"Stockfish terminated or failed: {exc}") from exc
        if isinstance(infos, dict):
            infos = [infos]
        if not infos or not infos[0].get("pv") or "score" not in infos[0]:
            raise EngineFailure("Stockfish returned no usable PV/score")
        lines = []
        for info in infos:
            pv = info.get("pv", [])[:self.config.pv_plies]
            if not pv or "score" not in info:
                continue
            white = info["score"].white()
            lines.append({"best_move_san": board.san(pv[0]), "best_move_uci": pv[0].uci(),
                          "pv_san": board.variation_san(pv), "evaluation": {
                              "cp_white": white.score(), "mate_white": white.mate()},
                          "depth": info.get("depth")})
        return {"fen": board.fen(), "turn": "white" if board.turn else "black",
                "result": None, "lines": lines}, infos[0]["score"]

    def analyze_position(self, board: chess.Board) -> dict:
        if not board.is_valid():
            raise ValueError("invalid chess position")
        result, _ = self._analyse(board)
        return result

    def analyze_game(self, game: chess.pgn.Game, *, number: int = 1,
                     progress: Callable[[int, int], None] | None = None) -> dict:
        """`progress(ply, total_plies)` is called after each ply; it never affects the result."""
        if game.errors:
            raise ValueError(f"game {number} invalid: {game.errors[0]}")
        board = game.board()
        moves = list(game.mainline_moves())
        rows = []
        if moves:
            before, best_score = self._analyse(board)
        for ply, move in enumerate(moves, 1):
            side = "white" if board.turn else "black"
            if best_score is None:
                raise ValueError(f"game {number} has moves after a terminal position")
            best = before["lines"][0]
            played = board.san(move)
            board.push(move)
            after, played_score = self._analyse(board)
            best_mate = best_score.pov(not board.turn).mate()
            if played_score is None:
                outcome = board.outcome(claim_draw=True)
                played_mate = (1 if outcome.winner == (not board.turn) else -1) if outcome.winner is not None else None
            else:
                played_mate = played_score.pov(not board.turn).mate()
            if move.uci() == best["best_move_uci"]:
                loss = 0 if best_mate is None and played_mate is None else None
                label = "none"
            else:
                best_cp = best_score.pov(not board.turn).score()
                played_cp = played_score.pov(not board.turn).score() if played_score else None
                loss = max(0, best_cp - played_cp) if best_cp is not None and played_cp is not None else None
                label = classify_loss(loss, self.config.thresholds,
                                      best_mate=best_mate, played_mate=played_mate)
            if self.config.perspective in ("both", side):
                rows.append({"ply": ply, "side": side, "played": played, "played_uci": move.uci(),
                             "best_move_san": best["best_move_san"],
                             "best_move_uci": best["best_move_uci"], "best_pv_san": best["pv_san"],
                             "eval_before": best["evaluation"],
                             "eval_after": after["lines"][0]["evaluation"] if after["lines"] else None,
                             "terminal_result": after["result"], "cp_loss": loss,
                             "classification": label})
            before, best_score = after, played_score
            if progress is not None:
                progress(ply, len(moves))
        return {"game": number, "headers": dict(game.headers), "ply_count": len(moves),
                "final_fen": board.fen(), "result": board.outcome(claim_draw=True).result()
                if board.outcome(claim_draw=True) else game.headers.get("Result", "*"),
                "moves": rows, "critical_plies": [row["ply"] for row in rows
                                                if row["classification"] in ("mistake", "blunder")]}
