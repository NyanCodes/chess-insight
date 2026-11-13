import json
import subprocess
import sys
from pathlib import Path

from chess_backend.cli import main, default_engine

ROOT = Path(__file__).resolve().parents[1]

def test_default_engine_uses_stockfish_on_path_when_bundle_absent(tmp_path, monkeypatch):
    import chess_backend.cli as cli
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    monkeypatch.setattr(cli.shutil, "which", lambda name: "/usr/local/bin/stockfish" if name == "stockfish" else None)
    assert default_engine() == Path("/usr/local/bin/stockfish")


def test_cli_multi_game_json_and_perspective(capsys):
    code = main(["--pgn-file", str(ROOT / "tests/data/two_games.pgn"),
                 "--seconds", "0.03", "--multipv", "1", "--perspective", "black",
                 "--thresholds", "40,90,180"])
    obj = json.loads(capsys.readouterr().out)
    assert code == 0 and obj["ok"] is True
    assert len(obj["games"]) == 2
    assert obj["thresholds_cp"] == {"inaccuracy": 40, "mistake": 90, "blunder": 180}
    assert all(row["side"] == "black" for game in obj["games"] for row in game["moves"])
    assert obj["engine"]["threads"] == 2 and obj["engine"]["hash_mb"] == 256


def test_cli_invalid_pgn_returns_structured_error(capsys):
    code = main(["--pgn-text", "1. e4 e5 2. Qh5 Qxe1 *"])
    obj = json.loads(capsys.readouterr().out)
    assert code == 2 and obj["ok"] is False
    assert obj["error"]["type"] == "invalid_input"


def test_cli_invalid_fen_returns_structured_error(capsys):
    code = main(["--fen", "8/8/8/8/8/8/8/8 w - - 0 1"])
    obj = json.loads(capsys.readouterr().out)
    assert code == 2 and obj["error"]["type"] == "invalid_input"


def test_missing_engine_returns_structured_error(capsys, tmp_path):
    code = main(["--fen", "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
                 "--engine", str(tmp_path / "no-engine")])
    obj = json.loads(capsys.readouterr().out)
    assert code == 3 and obj["error"]["type"] == "engine_failure"


def test_module_is_independent_cli_entry_point():
    proc = subprocess.run([sys.executable, "-m", "chess_backend", "--fen",
        "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        "--seconds", "0.03", "--multipv", "1"], cwd=ROOT, text=True,
        capture_output=True, timeout=20)
    assert proc.returncode == 0, proc.stderr
    obj = json.loads(proc.stdout)
    assert obj["position"]["lines"][0]["best_move_san"]


def test_legacy_analyze_py_is_backend_entry_point():
    proc = subprocess.run([sys.executable, "analyze.py", "--pgn-file",
        "tests/data/two_games.pgn", "--seconds", "0.03", "--multipv", "1"],
        cwd=ROOT, text=True, capture_output=True, timeout=30)
    assert proc.returncode == 0, proc.stderr
    assert len(json.loads(proc.stdout)["games"]) == 2
