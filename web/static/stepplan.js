// Decide how to animate one ply between two positions. Pure logic: no DOM, no chessboard
// library, so it can be unit-tested under Node.
//
// Positions are FEN strings; only the piece-placement field matters. Pieces are named like
// the board library names them ("wn" = white knight, "bp" = black pawn).

const FILES = "abcdefgh";

export const placement = (fen) => String(fen).trim().split(/\s+/)[0];
export const squareIndex = (square) => FILES.indexOf(square[0]) + (square.charCodeAt(1) - 49) * 8;

// 64 entries, index 0 = a1, 7 = h1, 56 = a8.
export function parsePlacement(fen) {
  const squares = new Array(64).fill(null);
  placement(fen).split("/").forEach((row, i) => {
    let file = 0;
    for (const ch of row) {
      if (/\d/.test(ch)) { file += Number(ch); continue; }
      squares[(7 - i) * 8 + file] = (ch === ch.toUpperCase() ? "w" : "b") + ch.toLowerCase();
      file += 1;
    }
  });
  return squares;
}

// The board library animates a position change by pairing each piece that appeared with the
// nearest same-named piece that disappeared. With one candidate that is certain; with several
// it can pair the wrong two. Mirrors PositionsAnimation.seekChanges in the vendored library.
export function isAmbiguous(from, to) {
  const appeared = {}, disappeared = {};
  for (let i = 0; i < 64; i++) {
    if (from[i] === to[i]) continue;
    if (to[i]) appeared[to[i]] = (appeared[to[i]] || 0) + 1;
    if (from[i]) disappeared[from[i]] = (disappeared[from[i]] || 0) + 1;
  }
  return Object.keys(appeared).some((piece) =>
    disappeared[piece] && (appeared[piece] > 1 || disappeared[piece] > 1));
}

const squareName = (index) => FILES[index % 8] + (Math.floor(index / 8) + 1);

// Describe exactly what changes on the board during one ply, in the direction being played.
// `from` and `to` are the squares the moving piece travels along (for a step back they are the
// played move's squares swapped). Returns null when the data does not describe a single move.
//
//   slides:  pieces that travel (the mover, plus the rook when castling). `piece` is what is
//            drawn at the start, `endPiece` what stands there at the end (they differ on promotion).
//   vanish:  pieces that disappear (a capture, including en passant).
//   appear:  pieces that reappear (a capture being undone).
//   changed: every square whose contents differ, so the board can keep them hidden while the
//            animation draws them.
//
// The result is derived from the two positions alone, so it cannot pair the wrong pieces, which
// is what makes it safe for identical knights or rooks.
export function describeStep({ fenFrom, fenTo, from, to }) {
  const a = parsePlacement(fenFrom), b = parsePlacement(fenTo);
  const source = squareIndex(from), target = squareIndex(to);
  const mover = a[source];
  if (!mover || source === target) return null;

  const slides = [{ piece: mover, endPiece: b[target], from, to }];
  let vanish = [], appear = [];
  if (a[target]) vanish.push({ piece: a[target], square: to });          // captured where the mover lands
  if (b[source]) appear.push({ piece: b[source], square: from });        // restored where the mover left
  for (let i = 0; i < 64; i++) {
    if (i === source || i === target || a[i] === b[i]) continue;
    if (a[i]) vanish.push({ piece: a[i], square: squareName(i) });
    if (b[i]) appear.push({ piece: b[i], square: squareName(i) });
  }
  if (mover[1] === "k") {                                                 // castling: the rook travels too
    const gone = vanish.find((v) => v.piece === mover[0] + "r");
    const came = appear.find((v) => v.piece === mover[0] + "r");
    if (gone && came) {
      slides.push({ piece: gone.piece, endPiece: came.piece, from: gone.square, to: came.square });
      vanish = vanish.filter((v) => v !== gone);
      appear = appear.filter((v) => v !== came);
    }
  }
  const changed = [...new Set([...slides.flatMap((m) => [m.from, m.to]), ...vanish.map((v) => v.square), ...appear.map((v) => v.square)])];
  return { slides, vanish, appear, changed };
}

// Which single ply (if any) separates what the board shows from the position wanted?
// `position` numbers positions in a game: 0 is the start, n is the position after ply n.
export function stepBetween(rows, fromPosition, toPosition) {
  if (Math.abs(toPosition - fromPosition) !== 1) return null;
  const forward = toPosition > fromPosition;
  const row = rows.find((r) => r.ply === Math.min(fromPosition, toPosition) + 1);
  if (!row || !row.played_squares) return null;
  const { from, to } = row.played_squares;
  return forward
    ? { fenFrom: row.fen_before, fenTo: row.fen_after, from, to, ply: row.ply, reverse: false }
    : { fenFrom: row.fen_after, fenTo: row.fen_before, from: to, to: from, ply: row.ply, reverse: true };
}
