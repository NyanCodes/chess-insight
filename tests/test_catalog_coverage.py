"""The pair that keeps a future my.json from drifting: everything explain/ can emit
exists in en.json, and everything in en.json is reachable."""
import ast
import json
import re
from pathlib import Path

from chess_backend import explain, i18n, narration
from chess_backend.explain import KEYS, catalog_key, enum_catalog_keys
from chess_backend.i18n.render import LIST_KEYS

PACKAGE = Path(explain.__file__).parent
EN = json.loads((Path(i18n.__file__).parent / "locales/en.json").read_text(encoding="utf-8"))
PLACEHOLDER = re.compile(r"\{(\w+)\}")


def placeholders(entry) -> set[str]:
    texts = [v for k, v in entry.items() if k != "_count"] if isinstance(entry, dict) else [entry]
    return {name for text in texts for name in PLACEHOLDER.findall(text)}


def called_with_literal_first_arg(path: Path, names: set[str], skip: int = 0):
    """Yield (call, literal) for calls like note("key", ...) found by AST."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", None)
            args = node.args[skip:]
            if func in names and args and isinstance(args[0], ast.Constant) and isinstance(args[0].value, str):
                yield node, args[0].value


def test_every_key_explain_can_emit_exists_in_en_json():
    missing = [catalog_key(key) for key in KEYS if catalog_key(key) not in EN]
    missing += [key for key in enum_catalog_keys() if key not in EN]
    assert not missing, f"missing from en.json: {missing}"


def test_the_taxonomy_matches_what_the_rules_actually_emit():
    emitted = {literal for path in PACKAGE.glob("*.py")
               for _, literal in called_with_literal_first_arg(path, {"note"})}
    assert emitted == set(KEYS), f"declared but never emitted / emitted but undeclared: {emitted ^ set(KEYS)}"


def test_every_en_json_key_is_reachable():
    reachable = ({catalog_key(k) for k in KEYS} | enum_catalog_keys()
                 | narration.NARRATION_KEYS | set(LIST_KEYS))
    assert set(EN) - reachable == set(), f"unreachable in en.json: {sorted(set(EN) - reachable)}"
    assert reachable - set(EN) == set(), f"used but missing from en.json: {sorted(reachable - set(EN))}"


def test_every_catalog_key_literal_in_the_narrator_is_in_en_json():
    path = Path(narration.__file__)
    used = {literal for _, literal in called_with_literal_first_arg(path, {"say"}, skip=1)}
    used |= {literal for _, literal in called_with_literal_first_arg(path, {"t"})}
    assert used and used <= set(EN), f"unknown keys: {sorted(used - set(EN))}"


def test_explain_sentences_only_use_declared_parameters():
    for key, params in KEYS.items():
        entry = EN[catalog_key(key)]
        assert placeholders(entry) <= set(params), f"{key} uses undeclared placeholders"
        if isinstance(entry, dict):
            assert entry["_count"] in params


def test_narrator_supplies_every_placeholder_of_the_sentences_it_asks_for():
    path = Path(narration.__file__)
    for call, key in called_with_literal_first_arg(path, {"say"}, skip=1):
        given = {kw.arg for kw in call.keywords}
        assert placeholders(EN[key]) <= given, f"{key} needs {placeholders(EN[key]) - given}"


def test_entries_are_whole_sentences_or_well_formed_plurals():
    for key, entry in EN.items():
        if isinstance(entry, dict):
            assert "_count" in entry and "other" in entry, key
            assert set(entry) <= {"_count", "zero", "one", "two", "few", "many", "other"}, key
            assert entry["_count"] in placeholders({"x": entry["other"]}), key
        else:
            assert isinstance(entry, str) and entry.strip(), key
