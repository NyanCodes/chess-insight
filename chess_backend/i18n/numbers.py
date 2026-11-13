"""Locale-aware number formatting and CLDR plural categories, in one place."""
from __future__ import annotations

# A locale changes separators or digits by adding an entry here.
NUMBER_FORMATS = {
    "en": {"decimal": ".", "minus": "-", "plus": "+", "digits": "0123456789"},
}


def base_language(locale: str) -> str:
    return locale.replace("_", "-").split("-")[0].lower()


def format_number(value: float, decimals: int = 0, *, locale: str = "en",
                  signed: bool = False) -> str:
    fmt = NUMBER_FORMATS.get(base_language(locale), NUMBER_FORMATS["en"])
    text = f"{abs(value):.{decimals}f}".replace(".", fmt["decimal"])
    text = text.translate(str.maketrans("0123456789", fmt["digits"]))
    if value < 0 and float(f"{abs(value):.{decimals}f}") != 0:
        return fmt["minus"] + text
    return (fmt["plus"] + text) if signed else text


def _english(n: float) -> str:
    return "one" if n == 1 else "other"


# CLDR plural categories per language. English has one/other; Burmese has only
# other. A language not listed here is treated as having only "other".
PLURAL_RULES = {"en": _english, "my": lambda n: "other"}


def plural_category(language: str, count: float) -> str:
    return PLURAL_RULES.get(base_language(language), lambda n: "other")(count)
