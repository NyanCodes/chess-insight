"""Games that exercise every awkward kind of move, as ground-truth fixtures for the front end."""
import random

import chess

NAMED = {
    "capture": (None, "1. e4 d5 2. exd5 Qxd5 3. Nc3 Qa5 4. Nf3 c6"),
    "castle-kingside": (None, "1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5 4. O-O Nf6 5. d3 O-O"),
    "castle-queenside": (None, "1. d4 d5 2. Nc3 Nc6 3. Bf4 Bf5 4. Qd2 Qd7 5. O-O-O O-O-O"),
    "en-passant": (None, "1. e4 a6 2. e5 d5 3. exd6 Nf6 4. a3 e5 5. b3 Bxd6"),
    "en-passant-black": (None, "1. a3 d5 2. a4 d4 3. e4 dxe3 4. fxe3 Nf6"),
    "promotion": (None, "1. a4 b5 2. axb5 Nc6 3. b6 Nb4 4. b7 Nd5 5. b8=Q+ Rxb8 6. h4 Ngf6"),
    "capture-promotion": (None, "1. h4 g5 2. hxg5 h6 3. gxh6 Nf6 4. h7 Rg8 5. hxg8=Q+ Nxg8 6. e4 e5"),
    "underpromotion": (None, "1. a4 b5 2. axb5 Nc6 3. b6 Nb4 4. b7 Nd5 5. b8=N Ngf6 6. Nc6 d6"),
    "two-knights": ("k7/8/8/8/8/8/8/1N3N1K w - - 0 1", "1. Nbd2 Kb8 2. Nfe3 Ka8 3. Ndc4 Kb8"),
    "two-rooks": ("7k/8/8/8/8/8/8/R3R1K1 w - - 0 1", "1. Rad1 Kh7 2. Re2 Kg6 3. Red2 Kh7"),
}
UNIQUE = lambda s: s.replace("Nd2-c4", "Nc4").replace("Rd1-c1", "Rc1")  # noqa: E731


def moves_of(setup, text):
    board = chess.Board(setup) if setup else chess.Board()
    for token in UNIQUE(text).split():
        if token.endswith(".") or token[0].isdigit() and "." in token:
            continue
        yield board, board.parse_san(token)
        board.push(board.parse_san(token))


def describe(board: chess.Board, move: chess.Move, game: str, ply: int) -> dict:
    kind = ("castle" if board.is_castling(move) else "ep" if board.is_en_passant(move)
            else "promo" if move.promotion else "capture" if board.is_capture(move) else "quiet")
    rook = None
    if kind == "castle":
        rank = chess.square_rank(move.from_square)
        kingside = chess.square_file(move.to_square) == 6
        rook = [chess.square_name(chess.square(7 if kingside else 0, rank)),
                chess.square_name(chess.square(5 if kingside else 3, rank))]
    captured = None
    if board.is_en_passant(move):
        sq = chess.square(chess.square_file(move.to_square), chess.square_rank(move.from_square))
        captured = [chess.square_name(sq), ("w" if board.turn == chess.BLACK else "b") + "p"]
    elif board.is_capture(move):
        piece = board.piece_at(move.to_square)
        captured = [chess.square_name(move.to_square), ("w" if piece.color else "b") + piece.symbol().lower()]
    mover = board.piece_at(move.from_square)
    san = board.san(move)
    before = board.fen()
    board.push(move)
    after = board.fen()
    king = board.king(board.turn)
    checked = board.is_check()
    board.pop()
    return {"game": game, "ply": ply, "san": san, "from": chess.square_name(move.from_square),
            "to": chess.square_name(move.to_square), "fen_before": before, "fen_after": after,
            "kind": kind, "rook": rook, "captured": captured,
            "mover": ("w" if mover.color else "b") + mover.symbol().lower(),
            "promotion": (("w" if mover.color else "b") + chess.piece_symbol(move.promotion)) if move.promotion else None,
            "check": checked, "king_after": chess.square_name(king) if king is not None else None}


def named_plies() -> list[dict]:
    out = []
    for name, (setup, text) in NAMED.items():
        for ply, (board, move) in enumerate(moves_of(setup, text), 1):
            out.append(describe(board.copy(), move, name, ply))
    return out


def random_games(seed=7, games=160, length=70):
    rng = random.Random(seed)
    plies, jumps = [], []
    for g in range(games):
        board = chess.Board()
        track = {sq: sq for sq in chess.SQUARES if board.piece_at(sq)}
        snapshots = [(board.fen(), dict(track))]
        for ply in range(1, length + 1):
            if board.is_game_over():
                break
            # prefer the awkward moves so promotions, castling and en passant show up often
            legal = list(board.legal_moves)
            awkward = [m for m in legal if board.is_castling(m) or board.is_en_passant(m) or m.promotion]
            move = rng.choice(awkward) if awkward and rng.random() < .6 else rng.choice(legal)
            plies.append(describe(board, move, f"random-{g}", ply))
            if board.is_castling(move):
                kingside = chess.square_file(move.to_square) == 6
                rank = chess.square_rank(move.from_square)
                r_from = chess.square(7 if kingside else 0, rank)
                r_to = chess.square(5 if kingside else 3, rank)
                track[r_to] = track.pop(r_from)
            if board.is_en_passant(move):
                track.pop(chess.square(chess.square_file(move.to_square), chess.square_rank(move.from_square)), None)
            track.pop(move.to_square, None)
            track[move.to_square] = track.pop(move.from_square)
            board.push(move)
            snapshots.append((board.fen(), dict(track)))
        for k in range(0, len(snapshots) - 4, 3):
            for span in (2, 3, 4):
                (fen_a, trk_a), (fen_b, trk_b) = snapshots[k], snapshots[k + span]
                a, b = chess.Board(fen_a), chess.Board(fen_b)
                true_moves = []
                for end_sq, origin in trk_b.items():
                    pa, pb = a.piece_at(origin), b.piece_at(end_sq)
                    if origin != end_sq and pa and pb and pa == pb:
                        true_moves.append(f"{origin}>{end_sq}")
                jumps.append({"from": fen_a, "to": fen_b, "true_moves": true_moves})
    return plies, jumps


def build_fixture() -> dict:
    plies, jumps = random_games()
    return {"plies": named_plies() + plies, "jumps": jumps}
