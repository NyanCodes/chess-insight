"""Standalone JSON CLI for the local chess analyzer."""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import chess

from .analysis import AnalysisConfig, Analyzer, EngineFailure
from .classify import Thresholds
from .inputs import InputError, parse_fen, parse_pgn
from .limits import BusyError, job_slot

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENGINE = ROOT / "bin" / "stockfish-linux-x86-64-universal"

def default_engine() -> Path:
    """Use a local bundle if present, otherwise an installed Stockfish."""
    bundled = ROOT / "bin" / "stockfish-linux-x86-64-universal"
    return bundled if bundled.is_file() else Path(shutil.which("stockfish") or bundled)


def thresholds_arg(text: str) -> Thresholds:
    try:
        values = [int(part) for part in text.split(",")]
        if len(values) != 3:
            raise ValueError("need three values")
        return Thresholds(*values)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("thresholds must be increasing integers: inaccuracy,mistake,blunder") from exc


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Offline PGN/FEN analysis with local Stockfish; emits compact JSON")
    source = p.add_mutually_exclusive_group()
    source.add_argument("--fen", help="Full legal FEN position")
    source.add_argument("--pgn-file", type=Path, help="PGN file containing one or more games")
    source.add_argument("--pgn-text", help="PGN text containing one or more games")
    p.add_argument("--moves", nargs="*", default=[], help="SAN or UCI moves after FEN (or start position)")
    p.add_argument("--perspective", choices=("white", "black", "both"), default="both")
    p.add_argument("--seconds", type=float, default=2.0, help="Seconds per position, 0.01..20")
    p.add_argument("--multipv", type=int, default=2, help="Candidate variations per position, 1..5")
    p.add_argument("--pv-plies", type=int, default=8, help="Maximum plies per printed variation")
    p.add_argument("--thresholds", type=thresholds_arg, default=Thresholds(),
                   help="Local CP-loss bands: inaccuracy,mistake,blunder (default 50,100,250)")
    p.add_argument("--threads", type=int, default=2)
    p.add_argument("--hash-mb", type=int, default=256)
    p.add_argument("--max-jobs", type=int, default=1, help="Host-wide slot limit 1 or 2 (default 1)")
    p.add_argument("--queue-timeout", type=float, default=10.0)
    p.add_argument("--engine", type=Path, default=default_engine())
    return p


def emit(result: dict) -> None:
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        cfg = AnalysisConfig(seconds=args.seconds, multipv=args.multipv,
                             pv_plies=args.pv_plies, perspective=args.perspective,
                             threads=args.threads, hash_mb=args.hash_mb, thresholds=args.thresholds)
        if (args.pgn_file is not None or args.pgn_text is not None) and args.moves:
            raise InputError("--moves is only supported with --fen or the start position")
        if args.pgn_file is not None or args.pgn_text is not None:
            text = args.pgn_file.read_text(encoding="utf-8") if args.pgn_file else args.pgn_text
            games = parse_pgn(text)
            source = "pgn"
        else:
            board = parse_fen(args.fen) if args.fen else chess.Board()
            for raw in args.moves:
                try:
                    move = board.parse_uci(raw)
                except ValueError:
                    try:
                        move = board.parse_san(raw)
                    except ValueError as exc:
                        raise InputError(f"illegal move {raw!r}: {exc}") from exc
                board.push(move)
            source = "fen" if args.fen else "moves"
        with job_slot(ROOT / "data", max_jobs=args.max_jobs, queue_timeout=args.queue_timeout):
            with Analyzer(args.engine, cfg) as analyzer:
                if source == "pgn":
                    payload = {"games": [analyzer.analyze_game(game, number=i)
                                         for i, game in enumerate(games, 1)]}
                else:
                    payload = {"position": analyzer.analyze_position(board)}
        emit({"ok": True, "source": source, "engine": {"name": "Stockfish UCI",
              "threads": cfg.threads, "hash_mb": cfg.hash_mb, "seconds_per_position": cfg.seconds,
              "multipv": cfg.multipv}, "perspective": cfg.perspective,
              "thresholds_cp": cfg.thresholds.to_dict(), **payload})
        return 0
    except (InputError, ValueError, OSError, UnicodeError) as exc:
        emit({"ok": False, "error": {"type": "invalid_input", "message": str(exc)}})
        return 2
    except EngineFailure as exc:
        emit({"ok": False, "error": {"type": "engine_failure", "message": str(exc)}})
        return 3
    except BusyError as exc:
        emit({"ok": False, "error": {"type": "busy", "message": str(exc)}})
        return 4
