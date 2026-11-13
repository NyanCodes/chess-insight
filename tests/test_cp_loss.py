import chess
import chess.engine

from chess_backend.analysis import AnalysisConfig, Analyzer
from chess_backend.inputs import parse_pgn


class ScriptedEngine:
    def __init__(self):
        self.calls = []

    def analyse(self, board, *args, **kwargs):
        self.calls.append(tuple(move.uci() for move in board.move_stack))
        script = {
            (): (50, "d2d4"),
            ("e2e4",): (-200, "d7d5"),
            ("e2e4", "e7e5"): (100, "g1f3"),
        }
        cp, move = script[self.calls[-1]]
        return [{"score": chess.engine.PovScore(chess.engine.Cp(cp), chess.WHITE),
                 "pv": [chess.Move.from_uci(move)], "depth": 15}]


def test_cp_loss_uses_best_before_vs_played_after_from_movers_perspective():
    engine = ScriptedEngine()
    game = parse_pgn("1. e4 e5 *")[0]
    with Analyzer("not-used", AnalysisConfig(seconds=0.1), engine=engine) as analyzer:
        rows = analyzer.analyze_game(game)["moves"]
    assert rows[0]["cp_loss"] == 250
    assert rows[0]["classification"] == "blunder"
    assert rows[0]["best_move_san"] == "d4"
    assert rows[1]["cp_loss"] == 300
    assert rows[1]["classification"] == "blunder"
    assert rows[1]["best_move_san"] == "d5"
    assert len(engine.calls) == 3  # one engine analysis for each position, not twice per ply
