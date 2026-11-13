"""Flat JSON catalogs with whole-sentence entries, named placeholders and plurals.

An entry is either a string or a plural object keyed by CLDR category:

    "explain.lost_material": {"_count": "amount",
                              "one": "It lost {amount} point of material.",
                              "other": "It lost {amount} points of material."}

Lookup falls back: requested locale -> its base language -> "en" -> the key.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from .numbers import base_language, plural_category

LOCALES = Path(__file__).parent / "locales"
DEFAULT_LOCALE = "en"


def normalize(locale: str) -> str:
    parts = locale.replace("_", "-").split("-")
    return "-".join([parts[0].lower()] + [p.upper() if len(p) == 2 else p.title() for p in parts[1:]])


@lru_cache(maxsize=None)
def load_locale(locale: str) -> dict:
    path = LOCALES / f"{normalize(locale)}.json"
    if "/" in locale or "\\" in locale or not path.is_file():
        return {}
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


class _Params(dict):
    def __missing__(self, name):          # never crash on a missing placeholder
        return "{" + name + "}"


def chain(locale: str) -> list[str]:
    wanted = normalize(locale)
    return list(dict.fromkeys([wanted, base_language(wanted), DEFAULT_LOCALE]))


class Catalog:
    def __init__(self, locale: str = DEFAULT_LOCALE):
        self.locale = normalize(locale)

    def lookup(self, key: str) -> tuple[object, str] | None:
        """The entry for `key` and the language it came from, via the fallback chain."""
        for locale in chain(self.locale):
            entry = load_locale(locale).get(key)
            if entry is not None:
                return entry, locale
        return None

    def t(self, key: str, counts: dict | None = None, **params) -> str:
        """Render `key`. `counts` holds raw numbers for plural entries (they pick
        the category); `params` are the already-formatted placeholder values."""
        found = self.lookup(key)
        if found is None:
            return key
        entry, source = found
        if isinstance(entry, dict):                       # plural entry
            name = entry.get("_count", "count")
            count = (counts or {}).get(name, params.get(name, 1))
            category = plural_category(source, count)
            entry = entry.get(category) or entry.get("other") or key
        return str(entry).format_map(_Params(params))
