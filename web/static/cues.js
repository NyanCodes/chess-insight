// What to show for "the move that was just played": the squares to tint, the badge on the
// destination square and the king in check. Pure data, no DOM, so it can be tested under Node.
import { parsePlacement, squareIndex } from "./stepplan.js";

const ERRORS = ["blunder", "mistake", "inaccuracy", "unclassified_mate"];
const BADGES = {
  blunder: { kind: "blunder", glyph: "??", label: "Blunder" },
  mistake: { kind: "mistake", glyph: "?", label: "Mistake" },
  inaccuracy: { kind: "inaccuracy", glyph: "?!", label: "Inaccuracy" },
  unclassified_mate: { kind: "mate", glyph: "!?", label: "Mate line, hard to judge" },
  book: { kind: "book", glyph: null, label: "Book move" },
  best: { kind: "best", glyph: "★", label: "Best move" },
  good: { kind: "good", glyph: "✓", label: "Good move" },
};

// Errors first (they are what the reader needs), then theory, then how close it was to the engine.
export function badgeFor(row) {
  if (!row) return null;
  if (ERRORS.includes(row.classification)) return BADGES[row.classification];
  const keys = new Set((row.annotations || []).map((a) => a.key));
  if (keys.has("book_move")) return BADGES.book;
  if (keys.has("best_move")) return BADGES.best;
  if (keys.has("good_alternative")) return BADGES.good;
  return null;
}

// Square of the king whose side is to move in `fen`, or null.
export function kingToMove(fen) {
  const [layout, turn] = String(fen).trim().split(/\s+/);
  const wanted = turn === "b" ? "bk" : "wk";
  const index = parsePlacement(layout).indexOf(wanted);
  return index < 0 ? null : "abcdefgh"[index % 8] + (Math.floor(index / 8) + 1);
}

export const givesCheck = (san) => /[+#]$/.test(String(san || ""));

// The cue for the position after `ply` plies of a game (0 is the start: nothing was just played).
export function cueAt(rows, ply) {
  if (!ply || ply < 1) return null;
  const row = rows.find((r) => r.ply === ply);
  if (!row || !row.played_squares) return null;
  return {
    ply: row.ply, side: row.side, san: row.san, number: row.number,
    from: row.played_squares.from, to: row.played_squares.to,
    badge: badgeFor(row),
    check: givesCheck(row.san) && row.fen_after ? kingToMove(row.fen_after) : null,
    classification: row.classification,
  };
}

export { squareIndex };
