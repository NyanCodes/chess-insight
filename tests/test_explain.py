import chess

from chess_backend.explain import KEYS, annotate_game
from tests.helpers import EVEN, load_fixture, make_game

SCHOLAR = ["e4", "e5", "Bc4", "Nc6", "Qh5", "Nf6", "Qxf7#"]


def notes(game):
    return [{a["key"]: a["params"] for a in n["annotations"]} for n in annotate_game(game)]


def test_allowed_mate_is_correct_for_the_black_mover_and_names_the_engines_reply():
    game = make_game(SCHOLAR, overrides={
        6: {"classification": "blunder", "cp_loss": None, "best_move_san": "g6",
            "eval_before": {"cp_white": 30, "mate_white": None},
            "eval_after": {"cp_white": None, "mate_white": 1}},           # White mates
        7: {"best_move_san": "Qxf7#", "terminal_result": "1-0"}})
    found = notes(game)
    assert found[5]["allowed_mate"] == {"mate_in": 1, "reply": "Qxf7#"}
    # Black's engine score is -30 from Black's side: the sign flip must be applied.
    assert found[5]["engine_preferred"] == {"best": "g6", "best_cp": -30}
    assert found[6]["terminal_checkmate"] == {"winner": "white"}


def test_allowed_mate_for_the_white_mover_uses_the_opposite_mate_sign():
    game = make_game(["f3", "e5", "g4", "Qh4#"], overrides={
        3: {"classification": "blunder", "cp_loss": None, "best_move_san": "e3",
            "eval_after": {"cp_white": None, "mate_white": -1}},          # Black mates
        4: {"best_move_san": "Qh4#", "terminal_result": "0-1"}})
    found = notes(game)
    assert found[2]["allowed_mate"] == {"mate_in": 1, "reply": "Qh4#"}
    assert found[3]["terminal_checkmate"] == {"winner": "black"}


def test_missed_mate_and_the_mover_perspective_for_both_colours():
    white = make_game(["e4", "e5"], overrides={1: {
        "classification": "blunder", "cp_loss": None, "best_move_san": "Qh5",
        "best_move_uci": "d1h5", "eval_before": {"cp_white": None, "mate_white": 2}}})
    black = make_game(["e4", "e5"], overrides={2: {
        "classification": "blunder", "cp_loss": None, "best_move_san": "Qh4",
        "best_move_uci": "d8h4", "eval_before": {"cp_white": None, "mate_white": -2}}})         # Black mates in 2
    assert notes(white)[0]["missed_mate"] == {"best": "Qh5", "mate_in": 2}
    assert notes(black)[1]["missed_mate"] == {"best": "Qh4", "mate_in": 2}


def test_unclear_mate_is_reported_without_inventing_a_cause():
    game = make_game(["e4"], overrides={1: {"classification": "unclassified_mate", "cp_loss": None}})
    found = notes(game)[0]
    assert "unclear_mate" in found
    assert not {"allowed_mate", "missed_mate", "hung_piece", "engine_preferred"} & set(found)


def test_hung_piece_needs_the_moved_piece_to_be_taken_for_a_real_loss():
    game = make_game(["e4", "e5", "Nf3", "Nc6", "Nxe5", "Nxe5"], overrides={
        5: {"classification": "blunder", "cp_loss": 280, "best_move_san": "Bb5"},
        6: {"best_move_san": "Nxe5", "best_pv_san": "3... Nxe5"}})
    hung = notes(game)[4]["hung_piece"]
    assert hung == {"piece": "knight", "square": "e5", "captured_by": "Nxe5", "cp": 280}
    assert "lost_material" not in notes(game)[4]


def test_a_lost_pawn_is_lost_material_not_a_hung_piece():
    game = make_game(["e4", "d5", "Nc3", "dxe4"], overrides={
        3: {"classification": "inaccuracy", "cp_loss": 80, "best_move_san": "exd5"},
        4: {"best_move_san": "dxe4", "best_pv_san": "2... dxe4"}})
    found = notes(game)[2]
    assert found["lost_material"] == {"amount": 1} and "hung_piece" not in found


def test_missed_capture_when_a_free_piece_was_left_on_the_board():
    fen = "4k3/8/8/3q4/8/8/8/3QK3 w - - 0 1"
    game = make_game(["Ke2", "Qxd1+"], fen=fen, overrides={
        1: {"classification": "blunder", "cp_loss": 900, "best_move_san": "Qxd5+",
            "best_pv_san": "1. Qxd5+ Ke7"},
        2: {"best_move_san": "Qxd1+", "best_pv_san": "1... Qxd1+ 2. Kxd1"}})
    assert notes(game)[0]["missed_capture"] == {"best": "Qxd5+", "gain": 9}


def test_without_the_opponents_row_material_rules_stay_silent():
    game = make_game(["e4", "e5", "Nf3", "Nc6", "Nxe5"], overrides={
        5: {"classification": "blunder", "cp_loss": 280, "best_move_san": "Bb5"}})
    found = notes(game)[4]
    assert set(found) == {"engine_preferred", "eval_swing"}      # nothing guessed


def test_filtered_rows_disable_replay_and_reply_but_keep_engine_facts():
    full = make_game(SCHOLAR, overrides={6: {
        "classification": "blunder", "cp_loss": None, "best_move_san": "g6",
        "eval_after": {"cp_white": None, "mate_white": 1}}})
    only_black = {**full, "moves": [r for r in full["moves"] if r["side"] == "black"]}
    found = notes(only_black)
    assert {"allowed_mate"} <= set(found[2])
    assert "reply" not in found[2]["allowed_mate"]              # the reply row was filtered out
    assert not any("book_move" in n or "left_book" in n for n in found)


def test_quality_notes_for_clean_moves():
    game = make_game(["e4", "e5"], overrides={2: {"best_move_san": "c5", "best_move_uci": "c7c5",
                                                  "cp_loss": 12}})
    found = notes(game)
    assert "best_move" in found[0] and found[1]["good_alternative"] == {"best": "c5"}


def test_stalemate_and_insufficient_material_endings():
    stalemate = make_game(["Qf7"], fen="7k/8/5QK1/8/8/8/8/8 w - - 0 1",
                          overrides={1: {"terminal_result": "1/2-1/2"}})
    assert chess.Board(stalemate["final_fen"]).is_stalemate()
    assert "terminal_stalemate" in notes(stalemate)[0]
    bare = make_game(["Kxa2"], fen="8/8/8/8/8/2k5/n7/K7 w - - 0 1",
                     overrides={1: {"terminal_result": "1/2-1/2"}})
    assert notes(bare)[0]["terminal_draw"] == {"reason": "insufficient_material"}


def test_book_run_stops_at_theory_exit_and_at_an_engine_flagged_move():
    two = load_fixture("two_games")["games"]
    scholar, fools = notes(two[0]), notes(two[1])
    assert [bool(n.get("book_move")) for n in scholar] == [True, True, True, True, False, False, False]
    assert "left_book" in scholar[4] and "left_book" not in scholar[5]
    assert not any("book_move" in n or "left_book" in n for n in fools)   # 1. f3 is flagged first


def test_main_line_moves_stay_in_book_even_without_their_own_name():
    ruy = notes(load_fixture("long_game")["games"][0])
    assert all("book_move" in n for n in ruy)            # 4. Ba4 has no exact name but is theory
    assert not any("left_book" in n for n in ruy)


def test_only_declared_keys_and_parameters_are_emitted():
    games = load_fixture("two_games")["games"] + load_fixture("long_game")["games"]
    for game in games:
        for note in annotate_game(game):
            for annotation in note["annotations"]:
                assert annotation["key"] in KEYS
                assert set(annotation["params"]) <= set(KEYS[annotation["key"]])
