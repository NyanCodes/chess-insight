from pathlib import Path

import chess
import chess.engine
import pytest

from chess_backend.analysis import AnalysisConfig, Analyzer, EngineFailure
from chess_backend.cli import default_engine
from chess_backend.inputs import parse_pgn

ENGINE = default_engine()


def test_tactical_fen_finds_mate_in_one():
    board = chess.Board()
    for san in ("f3", "e5", "g4"):
        board.push_san(san)
    with Analyzer(ENGINE, AnalysisConfig(seconds=0.12, multipv=2)) as analyzer:
        result = analyzer.analyze_position(board)
    assert result["turn"] == "black"
    assert result["lines"][0]["best_move_san"] == "Qh4#"
    assert result["lines"][0]["evaluation"]["mate_white"] == -1


def test_two_games_include_all_moves_and_filter_white_critical_only():
    text = (Path(__file__).parent / "data/two_games.pgn").read_text()
    games = parse_pgn(text)
    with Analyzer(ENGINE, AnalysisConfig(seconds=0.03, multipv=1, perspective="white")) as analyzer:
        results = [analyzer.analyze_game(g, number=i) for i, g in enumerate(games, 1)]
    assert [r["ply_count"] for r in results] == [7, 4]
    assert all(m["side"] == "white" for r in results for m in r["moves"])
    assert results[0]["headers"]["Event"] == "Scholar's Mate"
    assert results[1]["headers"]["Event"] == "Fool's Mate"
    assert results[0]["moves"][-1]["played"] == "Qxf7#"
    assert all("classification" in m and "cp_loss" in m and "best_move_san" in m
               for r in results for m in r["moves"])


def test_full_twenty_ply_game_is_not_truncated():
    text = (Path(__file__).parent / "data/long_game.pgn").read_text()
    game = parse_pgn(text)[0]
    with Analyzer(ENGINE, AnalysisConfig(seconds=0.01, multipv=1)) as analyzer:
        report = analyzer.analyze_game(game)
    assert report["ply_count"] == 20
    assert len(report["moves"]) == 20
    assert report["moves"][0]["played"] == "e4"
    assert report["moves"][-1]["played"] == "Nbd7"


class CrashedEngine:
    def analyse(self, *args, **kwargs):
        raise chess.engine.EngineTerminatedError("test crash")


def test_engine_crash_is_wrapped_as_engine_failure():
    with Analyzer(ENGINE, AnalysisConfig(seconds=0.1), engine=CrashedEngine()) as analyzer:
        with pytest.raises(EngineFailure, match="terminated"):
            analyzer.analyze_position(chess.Board())


class TimeoutEngine:
    def analyse(self, *args, **kwargs):
        raise TimeoutError("slow engine")


def test_engine_timeout_is_wrapped_as_engine_failure():
    with Analyzer(ENGINE, AnalysisConfig(seconds=0.1), engine=TimeoutEngine()) as analyzer:
        with pytest.raises(EngineFailure, match="timed out"):
            analyzer.analyze_position(chess.Board())
