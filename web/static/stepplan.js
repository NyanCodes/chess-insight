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

// `from` and `to` are the squares the piece travels along in the direction being played (for a
// step back they are the played move's squares swapped).
//   kind "move": slide the piece with movePiece(), then settle on the target position if a
//                promotion swap, a restored capture or a castling rook still has to change.
//   kind "diff": a plain position diff is exact (castling, en passant, a restored capture), so
//                let the library animate every changed square at once.
//   kind "snap": the data does not describe a legal single move; just show the target.
export function planStep({ fenFrom, fenTo, from, to }) {
  const a = parsePlacement(fenFrom), b = parsePlacement(fenTo);
  const source = squareIndex(from), target = squareIndex(to);
  const mover = a[source];
  if (!mover || source === target) return { kind: "snap" };

  const promotes = mover !== b[target];                       // the piece changes type on arrival
  if (promotes) {
    const pawnInvolved = mover[1] === "p" || (b[target] && b[target][1] === "p");
    return pawnInvolved ? { kind: "move", settle: true } : { kind: "snap" };
  }
  const slid = a.slice();
  slid[target] = mover;
  slid[source] = null;
  const leftover = slid.some((piece, i) => piece !== b[i]);
  if (!leftover) return { kind: "move", settle: false };      // quiet move or plain capture
  return isAmbiguous(a, b) ? { kind: "move", settle: true } : { kind: "diff" };
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
