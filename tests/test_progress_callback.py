"""Other tools depend on the JSON output of analysis.py: the optional progress callback
must observe the analysis without ever changing a byte of it."""
import json
from pathlib import Path

import pytest

from chess_backend.analysis import AnalysisConfig, Analyzer
from chess_backend.inputs import parse_pgn
from tests.fake_engine import FakeEngine

PGN = ("[Event \"Mixed\"]\n\n1. e4 e5 2. Nf3 Nc6 3. Bc4 Nf6 4. Ng5 d5 5. exd5 Nxd5 6. Nxf7 Kxf7 "
       "7. Qf3+ Ke6 8. Nc3 Ncb4 *\n\n[Event \"Fool's Mate\"]\n\n1. f3 e5 2. g4 Qh4# 0-1\n")


def analyse(*, perspective="both", progress=None) -> str:
    games = parse_pgn(PGN)
    analyzer = Analyzer(Path("fake"), AnalysisConfig(seconds=0.05, perspective=perspective), engine=FakeEngine())
    out = [analyzer.analyze_game(game, number=i, **({"progress": progress} if progress else {}))
           for i, game in enumerate(games, 1)]
    return json.dumps(out, ensure_ascii=False, separators=(",", ":"))


@pytest.mark.parametrize("perspective", ["both", "white", "black"])
def test_output_is_byte_identical_with_and_without_a_progress_callback(perspective):
    seen = []
    plain = analyse(perspective=perspective)
    observed = analyse(perspective=perspective, progress=lambda ply, total: seen.append((ply, total)))
    assert plain == observed
    assert seen                                           # the callback really ran


def test_callback_reports_every_ply_even_when_the_perspective_hides_moves():
    seen = []
    analyse(perspective="white", progress=lambda ply, total: seen.append((ply, total)))
    first, second = 16, 4                                 # plies per game
    assert seen == [(i, first) for i in range(1, first + 1)] + [(i, second) for i in range(1, second + 1)]


def test_default_is_none_so_existing_callers_are_unchanged():
    import inspect
    assert inspect.signature(Analyzer.analyze_game).parameters["progress"].default is None


def test_a_game_without_moves_never_calls_back():
    seen = []
    analyzer = Analyzer(Path("fake"), AnalysisConfig(seconds=0.05), engine=FakeEngine())
    analyzer.analyze_game(parse_pgn("[Event \"empty\"]\n\n*\n")[0], progress=lambda *a: seen.append(a))
    assert seen == []
