"""Transparent, configurable local centipawn-loss bands (not site accuracy scores)."""
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Thresholds:
    inaccuracy: int = 50
    mistake: int = 100
    blunder: int = 250

    def __post_init__(self):
        if not 0 < self.inaccuracy < self.mistake < self.blunder:
            raise ValueError("thresholds must be positive and strictly increasing")

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


def classify_loss(cp_loss: int | None, rules: Thresholds,
                  *, best_mate: int | None = None, played_mate: int | None = None) -> str:
    """Mate swings are not converted to fictitious centipawns."""
    if best_mate is not None or played_mate is not None:
        if best_mate == played_mate:
            return "none"
        if (best_mate is not None and best_mate > 0 and
                (played_mate is None or played_mate < 0)):
            return "blunder"
        if played_mate is not None and played_mate < 0 and (best_mate is None or best_mate > 0):
            return "blunder"
        return "unclassified_mate"
    if cp_loss is None or cp_loss < rules.inaccuracy:
        return "none"
    if cp_loss >= rules.blunder:
        return "blunder"
    if cp_loss >= rules.mistake:
        return "mistake"
    return "inaccuracy"
