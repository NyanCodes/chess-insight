// Run by tests/test_frontend_steps.py (needs Node). Fixtures come from python-chess, so the
// expected moves are ground truth, and the board library's own diff routine is exercised.
import { readFileSync } from "node:fs";
import test from "node:test";
import assert from "node:assert/strict";

import { describeStep, isAmbiguous, parsePlacement, placement, squareIndex, stepBetween }
  from "../../web/static/stepplan.js";
import { badgeFor, cueAt, givesCheck, kingToMove } from "../../web/static/cues.js";
import { DEFAULT_SPEED_MS, SPEEDS, parseSavedSpeed } from "../../web/static/speed.js";
import { PositionsAnimation } from "../../web/static/vendor/cm-chessboard/src/view/PositionAnimationsQueue.js";

const fixtures = JSON.parse(readFileSync(process.env.STEP_FIXTURES, "utf8"));
const MOVE = 0;                                           // the library's CHANGE_TYPE.move

// Apply a description to the "from" position the way the board draws it; the result must be
// exactly the "to" position, and every piece that moved must be the right one.
function applyDescription(fenFrom, d) {
  const board = parsePlacement(fenFrom);
  for (const m of d.slides) board[squareIndex(m.from)] = null;
  for (const v of d.vanish) board[squareIndex(v.square)] = null;
  for (const m of d.slides) board[squareIndex(m.to)] = m.endPiece;
  for (const v of d.appear) board[squareIndex(v.square)] = v.piece;
  return board;
}

function check(ply, reverse) {
  const fenFrom = reverse ? ply.fen_after : ply.fen_before;
  const fenTo = reverse ? ply.fen_before : ply.fen_after;
  const [from, to] = reverse ? [ply.to, ply.from] : [ply.from, ply.to];
  const d = describeStep({ fenFrom, fenTo, from, to });
  const label = `${ply.game} ply ${ply.ply} ${ply.san} ${reverse ? "back" : "forward"}`;
  assert.ok(d, label);
  assert.deepEqual(applyDescription(fenFrom, d), parsePlacement(fenTo), `${label}: description does not reproduce the position`);
  // the mover is the piece that really moved
  assert.deepEqual([d.slides[0].from, d.slides[0].to], [from, to], label);
  assert.equal(d.slides[0].piece, reverse ? (ply.promotion ?? ply.mover) : ply.mover, `${label}: wrong mover`);
  assert.equal(d.slides[0].endPiece, reverse ? ply.mover : (ply.promotion ?? ply.mover), `${label}: wrong end piece`);
  // castling moves exactly one rook along with the king
  assert.equal(d.slides.length, ply.rook ? 2 : 1, label);
  if (ply.rook) {
    const [r1, r2] = ply.rook;
    assert.deepEqual([d.slides[1].from, d.slides[1].to], reverse ? [r2, r1] : [r1, r2], `${label}: wrong rook`);
  }
  // a capture vanishes forward and reappears backward, on the right square, and nothing else does
  const captured = ply.captured;
  assert.deepEqual(d.vanish.map((v) => [v.square, v.piece]), captured && !reverse ? [captured] : [], `${label}: vanish`);
  assert.deepEqual(d.appear.map((v) => [v.square, v.piece]), captured && reverse ? [captured] : [], `${label}: appear`);
  assert.equal(new Set(d.changed).size, d.changed.length);
  return d;
}

test("every ply of every fixture game is described correctly, forward and back", () => {
  const kinds = {};
  for (const ply of fixtures.plies) {
    for (const reverse of [false, true]) {
      const d = check(ply, reverse);
      const key = `${ply.kind}:${reverse ? "back" : "fwd"}`;
      kinds[key] = (kinds[key] || 0) + 1;
      assert.ok(d.changed.length >= 2 && d.changed.length <= 4, "a single ply touches 2 to 4 squares");
    }
  }
  console.log(JSON.stringify(kinds));
  assert.ok(fixtures.plies.length > 1000);
  for (const kind of ["castle", "ep", "promo", "capture", "quiet"]) assert.ok(kinds[`${kind}:fwd`] > 0, kind);
});

test("named awkward moves are described as intended", () => {
  const find = (game, san) => fixtures.plies.find((p) => p.game === game && p.san.replace(/[+#]$/, "") === san);
  const d = (p, reverse = false) => describeStep({
    fenFrom: reverse ? p.fen_after : p.fen_before, fenTo: reverse ? p.fen_before : p.fen_after,
    from: reverse ? p.to : p.from, to: reverse ? p.from : p.to });
  const exd5 = d(find("capture", "exd5"));
  assert.deepEqual([exd5.slides.length, exd5.vanish[0]], [1, { piece: "bp", square: "d5" }]);
  const castle = d(find("castle-kingside", "O-O"));
  assert.deepEqual(castle.slides.map((m) => [m.piece, m.from, m.to]), [["wk", "e1", "g1"], ["wr", "h1", "f1"]]);
  const queenside = d(find("castle-queenside", "O-O-O"), true);                                // undoing it
  assert.deepEqual(queenside.slides.map((m) => [m.piece, m.from, m.to]), [["wk", "c1", "e1"], ["wr", "d1", "a1"]]);
  const ep = d(find("en-passant", "exd6"));
  assert.deepEqual(ep.vanish, [{ piece: "bp", square: "d5" }]);                              // not the landing square
  const promo = d(find("promotion", "b8=Q"));
  assert.deepEqual([promo.slides[0].piece, promo.slides[0].endPiece], ["wp", "wq"]);
  const promoBack = d(find("promotion", "b8=Q"), true);
  assert.deepEqual([promoBack.slides[0].piece, promoBack.slides[0].endPiece], ["wq", "wp"]);
  const capPromo = d(find("capture-promotion", "hxg8=Q"));
  assert.deepEqual([capPromo.slides[0].endPiece, capPromo.vanish[0]], ["wq", { piece: "br", square: "g8" }]);
  const knights = d(find("two-knights", "Nbd2"));
  assert.deepEqual(knights.changed.sort(), ["b1", "d2"]);                                     // the other knight is untouched
  assert.equal(describeStep({ fenFrom: "8/8/8/8/8/8/8/8 w - - 0 1", fenTo: "8/8/8/8/8/8/8/8 w - - 0 1", from: "e2", to: "e4" }), null);
});

test("identical pieces: a plain diff over several plies is ambiguous, a single ply never is", () => {
  const ambiguous = fixtures.jumps.filter((j) => isAmbiguous(parsePlacement(j.from), parsePlacement(j.to)));
  assert.ok(ambiguous.length > 0, "expected some multi-ply diffs to be ambiguous");
  const singles = fixtures.plies.filter((p) => isAmbiguous(parsePlacement(p.fen_before), parsePlacement(p.fen_after)));
  assert.equal(singles.length, 0, "a single ply should never be ambiguous");
  // and it is not just theory: find a jump where the library pairs the wrong piece
  let wrong = 0;
  for (const j of fixtures.jumps) {
    const changes = PositionsAnimation.seekChanges(parsePlacement(j.from), parsePlacement(j.to));
    const slid = changes.filter((c) => c.type === MOVE).map((c) => `${c.atIndex}>${c.toIndex}`);
    if (slid.some((s) => !j.true_moves.includes(s))) wrong += 1;
  }
  console.log(`multi-ply jumps where the library's pairing slides a piece that did not make that move: ${wrong} of ${fixtures.jumps.length}`);
  assert.ok(wrong > 0);
});

test("stepBetween finds only adjacent plies that exist", () => {
  const rows = [{ ply: 1, played_squares: { from: "e2", to: "e4" }, fen_before: "A", fen_after: "B" },
                { ply: 3, played_squares: { from: "g1", to: "f3" }, fen_before: "C", fen_after: "D" }];
  assert.deepEqual(stepBetween(rows, 0, 1), { fenFrom: "A", fenTo: "B", from: "e2", to: "e4", ply: 1, reverse: false });
  assert.deepEqual(stepBetween(rows, 1, 0), { fenFrom: "B", fenTo: "A", from: "e4", to: "e2", ply: 1, reverse: true });
  assert.equal(stepBetween(rows, 1, 3), null);                    // two plies apart: snap
  assert.equal(stepBetween(rows, 1, 2), null);                    // ply 2 not in the (filtered) list
  assert.equal(stepBetween(rows, 2, 2), null);
});

test("placement ignores everything after the piece field", () => {
  assert.equal(placement("8/8/8/8/8/8/8/8 w - - 0 1"), "8/8/8/8/8/8/8/8");
  assert.equal(parsePlacement("r7/8/8/8/8/8/8/7K")[56], "br");
});

test("a remembered speed is read back safely: nothing saved must not mean 'off'", () => {
  assert.equal(parseSavedSpeed(null), DEFAULT_SPEED_MS);          // first visit (this was a real bug)
  assert.equal(parseSavedSpeed(undefined), DEFAULT_SPEED_MS);
  assert.equal(parseSavedSpeed(""), DEFAULT_SPEED_MS);
  assert.equal(parseSavedSpeed("abc"), DEFAULT_SPEED_MS);
  assert.equal(parseSavedSpeed("700"), DEFAULT_SPEED_MS);         // not one of the offered speeds
  assert.equal(parseSavedSpeed("180"), DEFAULT_SPEED_MS);         // an older release offered 180/90: they migrate to the new default
  assert.equal(parseSavedSpeed("0"), 0);                          // an explicit choice of Off is kept
  for (const ms of SPEEDS) assert.equal(parseSavedSpeed(String(ms)), ms);
  assert.equal(DEFAULT_SPEED_MS, 200);
});

test("the cue for a position: tinted squares, badge and the king in check", () => {
  for (const ply of fixtures.plies) {
    const row = { ply: 7, side: "white", san: ply.san, number: 4, played_squares: { from: ply.from, to: ply.to },
                  fen_after: ply.fen_after, classification: "none", annotations: [] };
    const cue = cueAt([row], 7);
    assert.equal(cue.check, ply.check ? ply.king_after : null, `${ply.game} ${ply.san}: check square`);
    assert.deepEqual([cue.from, cue.to], [ply.from, ply.to]);
    assert.equal(givesCheck(ply.san), ply.check);
    assert.equal(kingToMove(ply.fen_after), ply.king_after);
  }
  assert.equal(cueAt([], 3), null);
  assert.equal(cueAt([{ ply: 1, played_squares: { from: "e2", to: "e4" }, san: "e4" }], 0), null);   // the start: nothing just played
  assert.equal(cueAt([{ ply: 1, played_squares: null, san: "e4" }], 1), null);                      // no data for that ply
});

test("the badge prefers errors, then theory, then how close the move was to the engine's choice", () => {
  const note = (...keys) => ({ classification: "none", annotations: keys.map((key) => ({ key })) });
  assert.equal(badgeFor({ classification: "blunder", annotations: [{ key: "book_move" }] }).glyph, "??");
  assert.equal(badgeFor({ classification: "mistake", annotations: [] }).glyph, "?");
  assert.equal(badgeFor({ classification: "inaccuracy", annotations: [] }).glyph, "?!");
  assert.equal(badgeFor({ classification: "unclassified_mate", annotations: [] }).kind, "mate");
  assert.equal(badgeFor(note("book_move", "best_move")).kind, "book");
  assert.equal(badgeFor(note("best_move")).kind, "best");
  assert.equal(badgeFor(note("good_alternative")).kind, "good");
  assert.equal(badgeFor(note()), null);
  assert.equal(badgeFor(null), null);
});
