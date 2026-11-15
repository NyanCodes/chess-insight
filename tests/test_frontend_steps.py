"""The step planner (web/static/stepplan.js) is pure logic, tested under Node when it is available."""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.step_fixtures import NAMED, build_fixture, moves_of

ROOT = Path(__file__).resolve().parents[1]


def test_named_awkward_games_are_legal_and_cover_every_kind():
    kinds = set()
    for name, (setup, text) in NAMED.items():
        assert list(moves_of(setup, text)), name                       # parse_san raises on illegal moves
        for board, move in moves_of(setup, text):
            kinds.add("castle" if board.is_castling(move) else "ep" if board.is_en_passant(move)
                      else "promo" if move.promotion else "capture" if board.is_capture(move) else "quiet")
    assert kinds == {"castle", "ep", "promo", "capture", "quiet"}


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is not installed")
def test_step_planner_under_node(tmp_path):
    fixture = tmp_path / "steps.json"
    fixture.write_text(json.dumps(build_fixture()))
    result = subprocess.run(["node", "--test", "tests/js/stepplan.test.mjs"], cwd=ROOT, text=True,
                            capture_output=True, env={**os.environ, "STEP_FIXTURES": str(fixture)}, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "fail 0" in result.stdout


STATIC = ROOT / "web" / "static"


def test_speed_menu_offers_the_documented_choices_with_200_selected():
    html = (STATIC / "index.html").read_text()
    speeds = (STATIC / "speed.js").read_text()
    assert 'id="speed"' in html and '<option value="200" selected>' in html
    assert "SPEEDS = [0, 120, 200, 300, 500]" in speeds and "DEFAULT_SPEED_MS = 200" in speeds
    for ms in (0, 120, 200, 300, 500):
        assert f'<option value="{ms}"' in html


def test_reduced_motion_is_honoured_in_css_and_in_the_board():
    css = (STATIC / "style.css").read_text()
    assert "@media (prefers-reduced-motion: reduce)" in css and "--anim-ms: 0ms !important" in css
    assert "prefers-reduced-motion: reduce" in (STATIC / "board.js").read_text()


def test_board_slides_ghost_copies_with_an_ease_out_and_the_vendored_library_is_not_edited():
    board = (STATIC / "board.js").read_text()
    assert "describeStep(request.step)" in board                    # what moves is read from the positions
    assert "cubic-bezier(0.22, 1, 0.36, 1)" in board                # strong ease-out, set by us
    assert "animationDuration: 0" in board                          # the library's own (fixed) easing is never used
    assert "setPosition(request.fen, true)" not in board and "movePiece(" not in board
    import subprocess
    changed = subprocess.run(["git", "diff", "--name-only", "HEAD", "--", "web/static/vendor"],
                             cwd=ROOT, text=True, capture_output=True).stdout.strip()
    assert changed == "", f"vendored library was modified: {changed}"


def test_the_cues_exist_in_markup_and_styles_and_survive_reduced_motion():
    css = (STATIC / "style.css").read_text()
    for needle in ("marker-lastmove-from", "marker-lastmove-to", "marker-check", ".cues .badge", "badge-blunder", "badge-book"):
        assert needle in css, needle
    assert 'id="check-glow"' in (STATIC / "index.html").read_text()
    start = css.index("@media (prefers-reduced-motion: reduce)")
    reduced = css[start:css.index("\n}\n", start)]
    assert "marker" not in reduced and "badge" not in reduced      # reduced motion must not hide the cues
    assert (STATIC / "markers.svg").read_text().count('id="markerSquare"') == 1
