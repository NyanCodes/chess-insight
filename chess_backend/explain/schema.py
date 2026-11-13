"""The annotation taxonomy: the only contract between explain/ and i18n/.

Each key maps to the parameter names an annotation of that kind may carry.
No user-facing text lives here or anywhere in explain/; sentences are in
i18n/locales/*.json under "explain.<key>".
"""
from __future__ import annotations

KEYS: dict[str, tuple[str, ...]] = {
    # Opening theory (exact named-line prefixes from openings.py).
    "book_move": ("opening",),
    "left_book": ("san",),
    # Move quality against the engine's first choice.
    "best_move": (),
    "good_alternative": ("best",),
    "engine_preferred": ("best", "best_cp"),
    "eval_swing": ("before_cp", "after_cp"),
    # Material, from the played move plus the engine's reply line.
    "hung_piece": ("piece", "square", "captured_by", "cp"),
    "lost_material": ("amount",),
    "missed_capture": ("best", "gain"),
    "refutation": ("reply",),
    # Forced mates.
    "missed_mate": ("best", "mate_in"),
    "allowed_mate": ("mate_in", "reply"),
    "unclear_mate": (),
    # How the game ended.
    "terminal_checkmate": ("winner",),
    "terminal_stalemate": (),
    "terminal_draw": ("reason",),
}

# Parameters whose values are keys into the catalog, not text:
# param name -> (catalog prefix, allowed values).
ENUMS: dict[str, tuple[str, tuple[str, ...]]] = {
    "piece": ("piece", ("pawn", "knight", "bishop", "rook", "queen", "king")),
    "winner": ("side", ("white", "black")),
    "reason": ("draw_reason", ("insufficient_material", "threefold_repetition",
                               "fivefold_repetition", "fifty_moves", "seventyfive_moves")),
}


def catalog_key(annotation_key: str) -> str:
    return f"explain.{annotation_key}"


def enum_catalog_keys() -> set[str]:
    return {f"{prefix}.{value}" for prefix, values in ENUMS.values() for value in values}
