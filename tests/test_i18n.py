import json

import pytest

from chess_backend.i18n import Catalog, catalog, format_number, join_list, numbers, plural_category, say


@pytest.fixture
def locales(tmp_path, monkeypatch):
    """A scratch locales directory with a base-language and a regional catalog."""
    (tmp_path / "en.json").write_text(json.dumps({
        "a": "english a", "b": "english b", "only_en": "english only",
        "n": {"_count": "k", "one": "{k} thing", "other": "{k} things"}}))
    (tmp_path / "pt.json").write_text(json.dumps({"a": "pt a", "b": "pt b"}))
    (tmp_path / "pt-BR.json").write_text(json.dumps({"a": "pt-BR a"}))
    (tmp_path / "my.json").write_text(json.dumps({"a": "my a"}))   # no plural entries at all
    monkeypatch.setattr(catalog, "LOCALES", tmp_path)
    catalog.load_locale.cache_clear()
    yield
    catalog.load_locale.cache_clear()


def test_fallback_goes_region_then_base_then_english_then_the_key(locales):
    c = Catalog("pt_br")
    assert c.t("a") == "pt-BR a"             # region wins
    assert c.t("b") == "pt b"                # base language
    assert c.t("only_en") == "english only"  # English
    assert c.t("nowhere") == "nowhere"       # the key itself


def test_plural_entries_use_the_rules_of_the_language_that_supplied_them(locales):
    assert Catalog("en").t("n", counts={"k": 1}, k="1") == "1 thing"
    assert Catalog("en").t("n", counts={"k": 2}, k="2") == "2 things"
    # Burmese has only "other", but this key falls back to English, so English rules apply.
    assert Catalog("my").t("n", counts={"k": 1}, k="1") == "1 thing"
    assert plural_category("my", 1) == "other" and plural_category("en", 1) == "one"


def test_a_plural_entry_that_only_defines_other_works_for_any_count(tmp_path, monkeypatch):
    (tmp_path / "en.json").write_text("{}")
    (tmp_path / "my.json").write_text(json.dumps({"n": {"_count": "k", "other": "{k} x"}}))
    monkeypatch.setattr(catalog, "LOCALES", tmp_path)
    catalog.load_locale.cache_clear()
    assert Catalog("my").t("n", counts={"k": 1}, k="1") == "1 x"
    catalog.load_locale.cache_clear()


def test_missing_placeholder_never_crashes_and_locale_names_cannot_escape(locales):
    assert Catalog("en").t("n", counts={"k": 2}) == "{k} things"
    assert Catalog("../secret").t("a") == "english a"


def test_numbers_go_through_one_helper_and_a_locale_can_change_separators(monkeypatch):
    assert format_number(0.4, 2, signed=True) == "+0.40"
    assert format_number(-1.256, 2) == "-1.26" and format_number(3) == "3"
    assert format_number(-0.001, 2) == "0.00"                        # no "-0.00"
    monkeypatch.setitem(numbers.NUMBER_FORMATS, "xx", {"decimal": ",", "minus": "−", "plus": "+",
                                                       "digits": "٠١٢٣٤٥٦٧٨٩"})
    assert format_number(-1.5, 1, locale="xx") == "−١,٥"


def test_say_formats_pawns_counts_and_enums_per_locale():
    c = Catalog("en")
    assert say(c, "explain.eval_swing", before_cp=22, after_cp=-72) == "The evaluation moved from +0.22 to -0.72."
    assert say(c, "explain.hung_piece", piece="knight", square="e5", captured_by="Nxe5") \
        == "It left the knight on e5 to be taken by Nxe5."
    assert say(c, "explain.lost_material", amount=1).endswith("1 point of material.")
    assert say(c, "explain.lost_material", amount=3).endswith("3 points of material.")


def test_list_joining_comes_from_catalog_patterns():
    c = Catalog("en")
    assert join_list([], c) == "" and join_list(["a"], c) == "a"
    assert join_list(["a", "b"], c) == "a and b"
    assert join_list(["a", "b", "c"], c) == "a, b, and c"
    assert join_list(["a", "b", "c", "d"], c) == "a, b, c, and d"
