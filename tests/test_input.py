import pytest

from chess_backend.inputs import InputError, parse_fen, parse_pgn

TWO_GAMES = '''[Event "Scholars"]
[Result "1-0"]

1. e4 e5 2. Bc4 Nc6 3. Qh5 Nf6?? 4. Qxf7# 1-0

[Event "Fools"]
[Result "0-1"]

1. f3 e5 2. g4 Qh4# 0-1
'''


def test_parse_multiple_complete_games():
    games = parse_pgn(TWO_GAMES)
    assert len(games) == 2
    assert [g.headers["Event"] for g in games] == ["Scholars", "Fools"]
    assert [len(list(g.mainline_moves())) for g in games] == [7, 4]
    assert games[1].end().board().is_checkmate()


def test_parse_pgn_rejects_illegal_san():
    with pytest.raises(InputError, match="game 1.*illegal|game 1.*invalid"):
        parse_pgn('1. e4 e5 2. Qh5 Qxe1 *')


def test_parse_pgn_rejects_empty():
    with pytest.raises(InputError, match="no games"):
        parse_pgn("  \n")


def test_parse_fen_rejects_invalid_king_configuration():
    with pytest.raises(InputError, match="invalid"):
        parse_fen("8/8/8/8/8/8/8/8 w - - 0 1")
