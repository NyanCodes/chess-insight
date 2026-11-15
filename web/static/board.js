// cm-chessboard (MIT, vendored) with its arrows extension. The sprites are located relative
// to this module, so no absolute path or CDN is involved.
//
// Animation rules:
//  - Only a step of exactly one ply animates (the caller says so with `step`); anything else
//    snaps. The moving piece is driven from the known squares with movePiece(), never from a
//    guess about which piece changed.
//  - One worker applies requests one at a time and always takes the newest, so the board
//    follows rapid input instead of falling behind it.
import { Chessboard, COLOR, FEN } from "./vendor/cm-chessboard/src/Chessboard.js";
import { Arrows, ARROW_TYPE } from "./vendor/cm-chessboard/src/extensions/arrows/Arrows.js";
import { DEFAULT_SPEED_MS } from "./speed.js";
import { placement, planStep } from "./stepplan.js";

export const START = FEN.start;
const MIN_FAST_MS = 50;           // the shortest slide used while input arrives faster than a slide

export function createBoard(element, { speedMs = DEFAULT_SPEED_MS } = {}) {
  const board = new Chessboard(element, {
    position: FEN.start,
    assetsUrl: new URL("vendor/cm-chessboard/assets/", import.meta.url).href,
    style: { cssClass: "default", showCoordinates: true, animationDuration: speedMs },
    extensions: [{ class: Arrows }],
  });
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

  let speed = speedMs;            // the user's chosen slide time; 0 turns animation off
  let pending = null;             // newest request not yet applied
  let wantFlipped = false, flipped = false;
  let working = false;
  let lastRequestAt = -Infinity, requestGap = Infinity;

  const motionMs = () => (reducedMotion.matches || document.hidden ? 0 : speed);
  const busy = (on) => { if (on) element.dataset.animating = "true"; else delete element.dataset.animating; };

  function drawArrows(arrows, fadeMs) {
    board.removeArrows();
    for (const [type, squares] of arrows || []) {
      if (squares) board.addArrow(ARROW_TYPE[type], squares.from, squares.to);
    }
    const group = element.querySelector("g.arrows");
    if (!group) return;
    group.style.transition = "none";
    group.style.opacity = fadeMs > 0 ? "0" : "1";
    if (fadeMs > 0) {
      void group.getBoundingClientRect();                       // commit opacity 0 before fading in
      group.style.transition = `opacity ${fadeMs}ms ease-out`;
      group.style.opacity = "1";
    }
  }

  async function slide(step, ms) {
    const plan = planStep(step);
    board.props.style.animationDuration = ms;
    if (plan.kind === "diff") {
      await board.setPosition(step.fenTo, true);               // castling, en passant, restored capture
    } else if (plan.kind === "move") {
      await board.movePiece(step.from, step.to, true);         // captured piece fades as it is covered
      if (plan.settle) await board.setPosition(step.fenTo, false);   // promotion swap, restored pieces
    }
  }

  async function apply(request) {
    const ms = motionMs();
    board.removeArrows();                                      // they describe the old position
    let animated = false;
    if (request.step && ms > 0) {
      if (board.getPosition() !== placement(request.step.fenFrom)) {
        await board.setPosition(request.step.fenFrom, false);  // catch up, then animate the last ply
      }
      // Input arriving faster than a slide would take: shorten the slide so it can keep up.
      const effective = requestGap < ms ? Math.max(MIN_FAST_MS, Math.round(requestGap * 0.9)) : ms;
      await slide(request.step, effective);
      animated = true;
    }
    if (board.getPosition() !== placement(request.fen)) await board.setPosition(request.fen, false);
    if (!pending) drawArrows(request.arrows, animated ? Math.min(160, motionMs()) : 0);
  }

  async function turn() {
    flipped = wantFlipped;
    await board.setOrientation(flipped ? COLOR.black : COLOR.white, motionMs() > 0);
  }

  async function work() {
    working = true;
    busy(true);
    try {
      while (pending || wantFlipped !== flipped) {
        if (pending) {
          const request = pending;
          pending = null;
          await apply(request);
        } else {
          await turn();
        }
      }
    } catch (error) {
      console.error("board update failed", error);
    } finally {
      working = false;
      busy(false);
    }
  }

  return {
    // fen: the position to show. arrows: [[type, {from, to}], ...]. step: from stepBetween() when
    // the position is exactly one ply from the one shown before; omit it for anything else.
    show(fen, { arrows = [], step = null } = {}) {
      // Only input that lands while an update is still running counts as "faster than a slide".
      const now = performance.now();
      requestGap = working ? now - lastRequestAt : Infinity;
      lastRequestAt = now;
      pending = { fen, arrows, step };
      if (!working) work();
    },
    flip() {
      wantFlipped = !wantFlipped;
      if (!working) work();
    },
    setSpeed(ms) { speed = Math.max(0, Number(ms) || 0); },
    get speed() { return speed; },
  };
}
