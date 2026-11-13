"""A deterministic stand-in for Stockfish: a one-ply material search that sees mate in
one. It makes analysis reproducible byte for byte, which a time-limited real engine is not."""
import threading

import chess
import chess.engine

VALUES = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9}


def _material(board: chess.Board, color: chess.Color) -> int:
    return sum(VALUES.get(p.piece_type, 0) * (1 if p.color == color else -1)
               for p in board.piece_map().values())


class FakeEngine:
    def __init__(self, gate: threading.Event | None = None):
        self.gate = gate
        self.calls = 0

    def analyse(self, board: chess.Board, limit, multipv: int = 1):
        if self.gate is not None:
            self.gate.wait(10)
        self.calls += 1
        mover, scored = board.turn, []
        for move in board.legal_moves:
            board.push(move)
            score = chess.engine.Mate(1) if board.is_checkmate() else chess.engine.Cp(100 * _material(board, mover))
            board.pop()
            scored.append((score.score(mate_score=100_000), move.uci(), score, move))
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [{"score": chess.engine.PovScore(score, mover), "pv": [move], "depth": 1, "multipv": i}
                for i, (_, _, score, move) in enumerate(scored[:multipv], 1)]

    def configure(self, *_):
        pass

    def close(self):
        pass
