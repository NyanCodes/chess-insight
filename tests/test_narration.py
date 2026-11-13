import copy

from chess_backend.narration import render_position, render_report
from tests.helpers import load_fixture, make_game, report_data

BLUNDER = {"classification": "blunder", "cp_loss": 300, "best_move_san": "d4",
           "eval_before": {"cp_white": 0, "mate_white": None},
           "eval_after": {"cp_white": -300, "mate_white": None}}


def story(data, **kwargs):
    return render_report(data, **kwargs)


# --- the real two-game fixture -------------------------------------------------

def test_two_games_read_as_coach_commentary_with_reasons():
    text = story(load_fixture("two_games"))
    assert "Game 1 — Scholar's Mate. White won by checkmate in 7 plies." in text
    assert "Both players followed known theory through 2... Nc6 (Bishop's Opening)." in text
    assert "White left book first with 3. Qh5." in text
    # The reason is stated, not just a label: the blunder allowed mate, and the engine disagreed.
    assert ("The game turned at 3... Nf6. It allowed mate in 1. The engine preferred g6, "
            "which keeps Black roughly level. White took the chance immediately with 4. Qxf7#.") in text
    assert "Game 2 — Fool's Mate. Black won by checkmate in 4 plies." in text
    assert "The game turned at 2. g4. It allowed mate in 1." in text
    assert text.endswith("Local Stockfish estimates, not official Chess.com grades.")


def test_story_is_prose_not_a_move_table_and_does_not_repeat_itself():
    text = story(load_fixture("two_games"))
    assert "Moves (local labels)" not in text and "Turning points:" not in text
    assert "The finish:" not in text and "Book ·" not in text
    for san in ("1. e4", "1... e5", "2. Bc4"):          # quiet moves are summarised, not listed
        assert text.count(san) <= 1
    assert text.count("4. Qxf7#") == 1 and text.count("2... Qh4#") == 1
    assert text.count("King's Pawn Game") == 0          # the one opening name is the latest, not a repeat


def test_opening_attribution_never_credits_one_side_with_the_others_move():
    text = story(load_fixture("two_games"))
    assert "answered" not in text and "continued" not in text
    assert "Black continued 2... Qh4#" not in text and "Black left book" not in text


def test_empty_pgn_headers_do_not_render_as_question_marks():
    text = story(load_fixture("two_games"))
    assert "?" not in text and "(White)" not in text
    named = load_fixture("two_games")
    named["games"][0]["headers"].update({"White": "Alice", "Black": "?"})
    assert "Alice (White) vs Unknown (Black)." in story(named)


def test_a_book_move_is_never_labelled_with_a_contradictory_grade():
    text = story(load_fixture("two_games"))
    assert "Book" not in text.replace("left book", "")
    assert "1 blunder and 1 inaccuracy" in text           # engine errors are still counted honestly


def test_long_game_reads_as_a_clean_theory_game():
    text = story(load_fixture("long_game"))
    assert text.startswith("Game 1 — Ruy Lopez sample. The game has no recorded result.")
    assert "Both players followed known theory through 10... Nbd7 (Ruy Lopez: Closed, Breyer Defense, Zaitsev Hybrid)." in text
    assert "Neither side made a significant error." in text
    assert "White: 10 of 10 moves were the engine's top choice." in text
    assert "left book" not in text and "The game turned" not in text


# --- the --player flag ---------------------------------------------------------

def test_player_flag_speaks_to_you_and_hides_the_opponents_tally():
    text = story(load_fixture("two_games"), player="black")
    assert "You played Black." in text
    assert "which keeps you roughly level" in text
    assert "You: 1 blunder." in text and "You: no errors." in text
    assert "White: no errors" not in text and "White: 1 blunder" not in text


def test_player_with_no_errors_gets_an_explicit_all_clear():
    text = story(load_fixture("long_game"), player="white")
    assert "You: no errors." in text and "You played White." in text


# --- robustness and limits -----------------------------------------------------

def test_setup_fen_uses_the_actual_move_number_and_skips_opening_lookup():
    fen = "rnbqkbnr/pppppppp/8/8/8/3P4/PPPP1PPP/RNBQKBNR b KQkq - 0 2"
    game = make_game(["e5", "Nf3"], fen=fen, overrides={1: BLUNDER | {"best_move_san": "c5"}})
    text = story(report_data(game), player="black")
    assert "The game turned at 2... e5." in text
    assert "theory" not in text and "left book" not in text


def test_mate_scores_never_become_fake_centipawns():
    game = make_game(["f3", "e5", "g4"], overrides={3: {
        "classification": "blunder", "cp_loss": None, "best_move_san": "e3",
        "eval_before": {"cp_white": 0, "mate_white": None},
        "eval_after": {"cp_white": None, "mate_white": -1}}})
    text = story(report_data(game), player="white")
    assert "allowed mate in 1" in text
    assert "cp" not in text and "centipawn" not in text


def test_multiple_errors_in_one_game_are_summarised_in_priority_order():
    sans = ["e4", "e5", "Nf3", "Nc6", "Bb5", "a6", "Ba4", "Nf6"]
    game = make_game(sans, overrides={
        3: BLUNDER, 5: {**BLUNDER, "classification": "mistake", "cp_loss": 120},
        6: {**BLUNDER, "classification": "inaccuracy", "cp_loss": 60}})
    text = story(report_data(game))
    assert text.index("The game turned at 2. Nf3.") < text.index("also made a mistake at 3. Bb5")
    assert "also made an inaccuracy at 3... a6" in text
    assert "White: 1 blunder and 1 mistake." in text


def test_report_respects_the_cap_and_says_when_detail_was_left_out():
    sans = ["Nf3", "Nf6", "Ng1", "Ng8"] * 3
    game = make_game(sans, overrides={i: BLUNDER for i in range(1, 9)})
    full = story(report_data(game))
    capped = story(report_data(game), max_chars=len(full) - 40)
    assert len(capped) <= len(full) - 40
    assert "left out to fit one message" in capped
    assert "The game turned at" in capped and capped.endswith("not official Chess.com grades.")


def test_three_games_each_get_a_summary_with_bounded_output():
    game = load_fixture("two_games")["games"][0]
    games = [{**copy.deepcopy(game), "game": i} for i in (1, 2, 3)]
    text = story(report_data(*games), max_chars=900)
    assert "3 games" in text
    assert all(f"Game {i} —" in text for i in (1, 2, 3))
    assert len(text) <= 900 and text.endswith("not official Chess.com grades.")


def test_a_too_small_budget_returns_the_overflow_message_not_a_cut_sentence():
    game = load_fixture("two_games")["games"][0]
    games = [{**copy.deepcopy(game), "game": i, "headers": {"Event": "E" * 40}} for i in (1, 2, 3)]
    text = story(report_data(*games), max_chars=300)
    assert len(text) <= 300
    assert text.endswith("not official Chess.com grades.") or "Full report is available" in text


def test_unknown_locale_falls_back_to_english():
    data = load_fixture("two_games")
    assert story(data, locale="xx") == story(data, locale="en") == story(data, locale="xx-YY")


def test_invalid_arguments_are_rejected():
    import pytest
    data = load_fixture("two_games")
    with pytest.raises(ValueError):
        story(data, player="green")
    with pytest.raises(ValueError):
        story(data, max_chars=100)
    with pytest.raises(ValueError):
        story({"ok": False})


def test_position_report_has_candidates_and_mate():
    data = {"ok": True, "position": {"turn": "black", "fen": "test", "result": None,
        "lines": [{"best_move_san": "Qh4#", "pv_san": "2...Qh4#",
                   "evaluation": {"cp_white": None, "mate_white": -1}}]}}
    text = render_position(data)
    assert "Black to move" in text
    assert "Qh4#" in text and "mate for Black in 1" in text


def test_every_assessment_reads_correctly_for_both_you_and_a_named_side():
    # "you" and "White" take different verb forms, so no sentence may agree with {who}.
    for cp, phrase in ((400, "clearly winning"), (150, "ahead"), (0, "roughly level"),
                       (-150, "slightly worse for"), (-400, "difficult for")):
        game = make_game(["e4", "e5"], overrides={1: BLUNDER | {
            "eval_before": {"cp_white": cp, "mate_white": None}, "best_move_san": "d4"}})
        for player, who in (("both", "White"), ("white", "you")):
            text = story(report_data(game), player=player)
            sentence = next(part for part in text.split(". ") if phrase in part)
            assert who in sentence
            assert "you stays" not in text and "you is" not in text and "you keeps" not in text


# --- the command-line wrapper ------------------------------------------------------

def run_narrate(monkeypatch, capsys, stdin_text, argv=()):
    import io
    from chess_backend import narrate
    monkeypatch.setattr("sys.stdin", io.StringIO(stdin_text))
    code = narrate.main(list(argv))
    out = capsys.readouterr()
    return code, out.out, out.err


def test_narrate_command_prints_the_story_from_piped_json(monkeypatch, capsys):
    import json
    code, out, _ = run_narrate(monkeypatch, capsys, json.dumps(load_fixture("two_games")), ["--player", "black"])
    assert code == 0 and "Game 1 — Scholar's Mate." in out and "You played Black." in out


def test_narrate_command_reports_failures_without_a_traceback(monkeypatch, capsys):
    import json
    code, out, err = run_narrate(monkeypatch, capsys, json.dumps({"ok": False, "error": {"message": "engine missing"}}))
    assert code == 2 and out == "" and "engine missing" in err
    code, _, err = run_narrate(monkeypatch, capsys, "not json")
    assert code == 2 and "cannot narrate" in err
    code, _, err = run_narrate(monkeypatch, capsys, json.dumps({"ok": True, "position": {}}))
    assert code == 2                                           # a FEN analysis has no game to narrate
