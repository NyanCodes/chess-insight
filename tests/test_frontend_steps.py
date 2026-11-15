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
