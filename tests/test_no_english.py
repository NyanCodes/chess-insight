"""explain/ (and the narrator) must hold keys and parameters only: no user-facing English.
Every sentence lives in i18n/locales/*.json so a language is a catalog, not a code change."""
import ast
import re
from pathlib import Path

import pytest

from chess_backend import explain, i18n, narration

PACKAGE = Path(explain.__file__).parent
SCANNED = [*sorted(PACKAGE.glob("*.py")), Path(narration.__file__),
           Path(i18n.__file__).parent / "render.py"]
# PGN tag names are data keys, not text shown to anyone.
PGN_TAGS = {"Event", "White", "Black", "FEN", "SetUp"}
FORBIDDEN_CALLS = {"title", "capitalize"}


def english_like(text: str) -> bool:
    text = text.strip()
    return bool(re.search(r"[A-Za-z]{2,}[ ,;:!?]+[A-Za-z]{2,}", text) or re.fullmatch(r"[A-Z][a-z]{2,}", text))


def violations(source: str) -> list[str]:
    tree = ast.parse(source)
    skipped = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Raise):                      # programmer-error messages
            skipped |= {id(n) for n in ast.walk(node)}
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef)) and node.body \
                and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant):
            skipped.add(id(node.body[0].value))              # docstrings
    for node in ast.walk(tree):          # a PGN tag name is fine only as a lookup key
        if isinstance(node, ast.Call):
            func = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
            if func in ("get", "_name"):
                skipped |= {id(a) for a in node.args
                            if isinstance(a, ast.Constant) and a.value in PGN_TAGS}
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in skipped \
                and english_like(node.value):
            found.append(f"line {node.lineno}: {node.value!r}")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr in FORBIDDEN_CALLS:
            found.append(f"line {node.lineno}: .{node.func.attr}() builds English from a label")
    return found


@pytest.mark.parametrize("path", SCANNED, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_no_english_prose_in_code(path):
    assert violations(path.read_text(encoding="utf-8")) == []


def test_the_scanner_itself_catches_the_anti_patterns():
    assert violations("label = 'Book · ' + c.title()")
    assert violations("text = 'You lost ground'")
    assert violations("x = f'{who} allowed a forced mate'")
    assert violations("who = 'Black'")           # a PGN tag name as a label, not a lookup key
    assert violations("label = 'Blunder'")
    assert not violations("key = 'hung_piece'; fen = 'w KQkq - 0 1'; tag = headers.get('Event')")
    assert not violations('"""A docstring may be English."""\nraise ValueError("developer-facing text")')
