// Run by tests/test_frontend_steps.py (needs Node). Fixtures come from python-chess, so the
// expected moves are ground truth, and the board library's own diff routine is exercised.
import { readFileSync } from "node:fs";
import test from "node:test";
import assert from "node:assert/strict";

import { isAmbiguous, parsePlacement, placement, planStep, squareIndex, stepBetween }
  from "../../web/static/stepplan.js";
import { DEFAULT_SPEED_MS, SPEEDS, parseSavedSpeed } from "../../web/static/speed.js";
import { PositionsAnimation } from "../../web/static/vendor/cm-chessboard/src/view/PositionAnimationsQueue.js";

const fixtures = JSON.parse(readFileSync(process.env.STEP_FIXTURES, "utf8"));
const MOVE = 0;                                           // the library's CHANGE_TYPE.move

function check(ply, reverse) {
  const fenFrom = reverse ? ply.fen_after : ply.fen_before;
  const fenTo = reverse ? ply.fen_before : ply.fen_after;
  const [from, to] = reverse ? [ply.to, ply.from] : [ply.from, ply.to];
  const plan = planStep({ fenFrom, fenTo, from, to });
  const label = `${ply.game} ply ${ply.ply} ${ply.san} ${reverse ? "back" : "forward"}`;
  assert.notEqual(plan.kind, "snap", label);
  if (plan.kind === "diff") {
    // What the library will really do with this diff: every piece it slides must be a piece
    // that really moved in this ply (the mover, plus the rook when castling).
    const changes = PositionsAnimation.seekChanges(parsePlacement(fenFrom), parsePlacement(fenTo));
    const slides = changes.filter((c) => c.type === MOVE);
    const allowed = new Set([`${squareIndex(from)}>${squareIndex(to)}`]);
    for (const [r1, r2] of ply.rook ? [[ply.rook[0], ply.rook[1]]] : []) {
      allowed.add(reverse ? `${squareIndex(r2)}>${squareIndex(r1)}` : `${squareIndex(r1)}>${squareIndex(r2)}`);
    }
    for (const s of slides) assert.ok(allowed.has(`${s.atIndex}>${s.toIndex}`), `${label}: unexpected slide ${s.atIndex}>${s.toIndex}`);
    assert.ok(slides.some((s) => `${s.atIndex}>${s.toIndex}` === `${squareIndex(from)}>${squareIndex(to)}`), `${label}: mover not slid`);
    if (ply.rook) assert.equal(slides.length, 2, `${label}: castling must slide king and rook`);
  }
  return plan;
}

test("every ply of every fixture game plans a correct animation, forward and back", () => {
  const kinds = {};
  for (const ply of fixtures.plies) {
    for (const reverse of [false, true]) {
      const plan = check(ply, reverse);
      const key = `${ply.kind}:${reverse ? "back" : "fwd"}:${plan.kind}${plan.settle ? "+settle" : ""}`;
      kinds[key] = (kinds[key] || 0) + 1;
    }
  }
  console.log(JSON.stringify(kinds, null, 1));
  assert.ok(fixtures.plies.length > 1000);
});

test("named awkward moves choose the intended strategy", () => {
  const find = (game, san) => fixtures.plies.find((p) => p.game === game && p.san === san);
  const plan = (p, reverse = false) => planStep({
    fenFrom: reverse ? p.fen_after : p.fen_before, fenTo: reverse ? p.fen_before : p.fen_after,
    from: reverse ? p.to : p.from, to: reverse ? p.from : p.to });
  assert.deepEqual(plan(find("capture", "exd5")), { kind: "move", settle: false });
  assert.deepEqual(plan(find("castle-kingside", "O-O")), { kind: "diff" });
  assert.deepEqual(plan(find("castle-queenside", "O-O-O")), { kind: "diff" });
  assert.deepEqual(plan(find("en-passant", "exd6")), { kind: "diff" });
  assert.deepEqual(plan(find("promotion", "b8=Q")), { kind: "move", settle: true });
  assert.deepEqual(plan(find("promotion", "b8=Q"), true), { kind: "move", settle: true });
  assert.deepEqual(plan(find("capture", "exd5"), true), { kind: "diff" });          // capture restored
  assert.deepEqual(plan(find("two-knights", "Nbd2")), { kind: "move", settle: false });
  assert.deepEqual(plan(find("two-rooks", "Rad1")), { kind: "move", settle: false });
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
  assert.equal(parseSavedSpeed("0"), 0);                          // an explicit choice of Off is kept
  for (const ms of SPEEDS) assert.equal(parseSavedSpeed(String(ms)), ms);
  assert.equal(DEFAULT_SPEED_MS, 180);
});
