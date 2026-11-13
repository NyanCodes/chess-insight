"""Turn structured annotations into sentences, formatting values per locale."""
from __future__ import annotations

from ..explain.schema import ENUMS, catalog_key
from .catalog import Catalog
from .numbers import format_number

# Parameters holding centipawns, shown as pawns. "signed" keeps the +/- sign.
PAWN_PARAMS = {"cp": False, "cp_loss": False, "before_cp": True, "after_cp": True,
               "best_cp": True}
COUNT_PARAMS = ("amount", "gain", "mate_in", "count", "plies", "number", "matched", "total",
                "index", "mate")


def format_params(params: dict, catalog: Catalog) -> dict:
    """Locale-format numbers and replace enum values with their catalog text."""
    out = {}
    for name, value in params.items():
        if name in ENUMS and value is not None:
            out[name] = catalog.t(f"{ENUMS[name][0]}.{value}")
        elif name in PAWN_PARAMS and value is not None:
            out[name] = format_number(value / 100, 2, locale=catalog.locale,
                                      signed=PAWN_PARAMS[name])
        elif name in COUNT_PARAMS and isinstance(value, (int, float)):
            out[name] = format_number(value, 0, locale=catalog.locale)
        else:
            out[name] = value
    return out


def render_annotation(annotation: dict, catalog: Catalog) -> str:
    params = annotation.get("params", {})
    return catalog.t(catalog_key(annotation["key"]), counts=params,
                     **format_params(params, catalog))


def say(catalog: Catalog, key: str, **params) -> str:
    """Render any catalog key; numbers and enum values are formatted per locale."""
    return catalog.t(key, counts=params, **format_params(params, catalog))


LIST_KEYS = frozenset({"list.pair", "list.start", "list.middle", "list.end"})


def join_list(items: list[str], catalog: Catalog) -> str:
    """CLDR-style list joining, with the patterns living in the catalog."""
    if len(items) < 2:
        return "".join(items)
    if len(items) == 2:
        return catalog.t("list.pair", first=items[0], second=items[1])
    text = catalog.t("list.end", first=items[-2], last=items[-1])
    for item in reversed(items[1:-2]):
        text = catalog.t("list.middle", first=item, rest=text)
    return catalog.t("list.start", first=items[0], rest=text)
